#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
"""Zelftest voor het BACnet ReadPropertyMultiple-pad (T-030).

Geen hardware en geen pytest: deze test speelt een toestel met 331 objecten
(device + 330 analog inputs) op 127.0.0.1:47808. Bewezen wordt:

* RPM vraagt in blokken van 32 en levert dezelfde punten met ≥ 90% minder
  UDP-verzoeken dan het losse ReadProperty-pad;
* een toestel dat RPM weigert (error/reject/abort) valt automatisch terug en
  levert exact dezelfde 331 rijen;
* een error-result voor één eigenschap maakt alleen dát punt ok=false, zonder
  herkansing;
* een volledig weggevallen RPM-antwoord wordt één keer herkanst;
* budgetten zijn begrensd (0/negatief/rommel → standaard) en een verstrijkend
  budget geeft deelpunten + warning (points) of JSON (EDE), nooit een half zip;
* de object-list-cache laat pagina 2 niet opnieuw inventariseren.

    python3 tests/bacnet_rpm_test.py
"""

from __future__ import annotations

import json
import os
import socket
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bacnet                                              # noqa: E402

DEVICE = 1234
AI_COUNT = 330
OBJECTS = AI_COUNT + 1
def _free_client_port() -> int:
    """Eigen BIND-poort per run; de dummy houdt 47808 (BACnet/IP)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
    finally:
        probe.close()


FAKE_PORT = bacnet.BACNET_PORT
CLIENT_PORT = _free_client_port()

FAILED: list[str] = []


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"  {name}: ok")
    except Exception as exc:                        # noqa: BLE001 — testrunner
        FAILED.append(name)
        print(f"  {name}: FOUT — {type(exc).__name__}: {exc}")


# --------------------------------------------------------------------- dummy
class FakeDevice(threading.Thread):
    """BACnet/IP-toestel met ``ai_count`` analog inputs en RPM-aan/uit.

    ``rpm_mode``   "on" | "error" | "reject" | "abort" | "silent" | "too_long" —
                   wat 0x0E terugkrijgt ("too_long": eerste RPM-verzoek krijgt
                   segmentation-not-supported, daarna normaal).
    ``whole_mode`` "full" (hele object-list in één antwoord) of "short"
                   (eerste 100 ids, zoals een APDU-grens doet).
    ``drop_first_rpm``  laat het eerste RPM-verzoek volledig vallen (UDP-verlies).
    ``partial_error``   instance waarvan present-value een error-result wordt.
    ``delay``           seconden wachten per antwoord (voor budget-scenario's).
    """

    def __init__(self, ip: str = "127.0.0.1", port: int = FAKE_PORT,
                 device: int = DEVICE, ai_count: int = AI_COUNT,
                 rpm_mode: str = "on", whole_mode: str = "full",
                 drop_first_rpm: bool = False, partial_error: int | None = None,
                 delay: float = 0.0):
        super().__init__(daemon=True)
        self.device = device
        self.rpm_mode = rpm_mode
        self.whole_mode = whole_mode
        self.drop_first_rpm = drop_first_rpm
        self.partial_error = partial_error
        self.delay = max(0.0, delay)
        self.order = [(8, device)] + [(0, i) for i in range(1, ai_count + 1)]
        self.props: dict[tuple[int, int], dict] = {
            (8, device): {77: f"FlexPoll-{len(self.order)}", 70: "Testbank",
                          120: 999, 121: 8, 44: 2},
        }
        for i in range(1, ai_count + 1):
            self.props[(0, i)] = {77: f"AI {i}", 28: f"Test AI {i}",
                                  85: float(i), 117: 62}
        self.requests = 0            # alle confirmed requests
        self.rpm_requests = 0
        self.loose_reads = 0
        self.inventory_reads = 0     # leesacties op property 76
        self.dropped_rpm = 0
        self.specs_seen: list[list[tuple[tuple[int, int], list[int]]]] = []
        self._stop_evt = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            self.sock.bind((ip, port))
        except OSError as exc:
            self.sock.close()
            raise RuntimeError(
                f"kan {ip}:{port} niet binden ({exc}) — stop een testslave of "
                f"simulator op 47808") from None
        self.sock.settimeout(0.05)

    # -- zenden -------------------------------------------------------------
    def _send(self, src, npdu: bytes) -> None:
        if self.delay:
            time.sleep(self.delay)
        packet = bytes([0x81, bacnet.BVLC_ORIGINAL_UNICAST]) \
            + struct.pack(">H", len(npdu) + 4) + npdu
        try:
            self.sock.sendto(packet, src)
        except OSError:
            pass

    @staticmethod
    def _enc(obj: tuple[int, int], prop: int, value) -> bytes:
        t = obj[0]
        if prop in (77, 28, 70):
            return bacnet._app_str(value)
        if prop == 85 and t in (3, 4, 8):
            return bacnet._app_bool(bool(value))
        if prop in (85, 117) and t in (0, 1, 2):
            return bacnet._app_real(float(value)) if prop == 85 else bacnet._app_enum(int(value))
        if prop == 85 and t in (5, 13, 14, 19):
            return bacnet._app_enum(int(value))
        return bacnet._app_uint(int(value))

    def _ack(self, src, inv: int, obj, prop: int, body: bytes) -> None:
        head = bytes([0x30, inv, 0x0C]) \
            + bacnet._ctx(0, struct.pack(">I", (obj[0] << 22) | obj[1])) \
            + bacnet._ctx(1, bacnet._uint_bytes(prop))
        self._send(src, bytes([0x01, 0x00]) + head + b"\x3e" + body + b"\x3f")

    def _error(self, src, inv: int, cls: int, code: int, service: int = 0x0C) -> None:
        err = bytes([0x50, inv, service]) \
            + bacnet._ctx(2, bacnet._uint_bytes(cls)) + bacnet._ctx(3, bacnet._uint_bytes(code))
        self._send(src, bytes([0x01, 0x00]) + err)

    def _rpm_ack(self, src, inv: int, results) -> None:
        body = bytes([0x30, inv, bacnet.SERVICE_RPM]) + b"\x0e"
        for obj, entries in results:
            body += bacnet._ctx(0, struct.pack(">I", (obj[0] << 22) | obj[1]))
            body += b"\x1e"
            for prop, value, err in entries:
                body += bacnet._ctx(2, bacnet._uint_bytes(prop)) + b"\x3e"
                if err is not None:
                    body += b"\x5e" + bacnet._ctx(0, bacnet._uint_bytes(err[0])) \
                        + bacnet._ctx(1, bacnet._uint_bytes(err[1])) + b"\x5f"
                else:
                    body += b"\x4e" + self._enc(obj, prop, value) + b"\x4f"
                body += b"\x3f"
            body += b"\x1f"
        body += b"\x0f"
        self._send(src, bytes([0x01, 0x00]) + body)

    # -- verwerken ----------------------------------------------------------
    def _serve_read_property(self, src, inv: int, apdu: bytes) -> None:
        tag, cls, ln, i = bacnet._read_tag(apdu, 4)
        oid = int.from_bytes(apdu[i:i + ln], "big")
        obj = (oid >> 22, oid & 0x3FFFFF)
        tag, cls, ln, j = bacnet._read_tag(apdu, i + ln)
        prop = int.from_bytes(apdu[j:j + ln], "big")
        i = j + ln
        index = None
        if i < len(apdu):
            tag, cls, ln, j = bacnet._read_tag(apdu, i)
            index = int.from_bytes(apdu[j:j + ln], "big")

        if prop == bacnet.PROP_OBJECT_LIST:
            self.inventory_reads += 1
        props = self.props.get(obj)
        if props is None or (prop != bacnet.PROP_OBJECT_LIST and prop not in props):
            self._error(src, inv, 1, 31)                    # object / unknown-object
            return
        if prop == bacnet.PROP_OBJECT_LIST:
            if index is None:
                ids = self.order if self.whole_mode == "full" else self.order[:100]
                body = b"".join(bytes([0xC4]) + struct.pack(">I", (t << 22) | inst)
                                for t, inst in ids)
            elif index == 0:
                body = bacnet._app_uint(len(self.order))
            elif 1 <= index <= len(self.order):
                t, inst = self.order[index - 1]
                body = bytes([0xC4]) + struct.pack(">I", (t << 22) | inst)
            else:
                self._error(src, inv, 2, 42)                # property / invalid-array-index
                return
        else:
            body = self._enc(obj, prop, props[prop])
        self._ack(src, inv, obj, prop, body)

    @staticmethod
    def _parse_rpm(apdu: bytes):
        i = 4
        # listOfReadAccessSpecs is tag [0] in een RPM-request (0x0E). Een client
        # die hier 0x1E stuurt, stuurt een ongeldig verzoek: niet accepteren.
        if apdu[i] != 0x0E:
            raise ValueError("RPM-request zonder listOfReadAccessSpecs")
        i += 1
        specs = []
        while i < len(apdu) and apdu[i] != 0x1F:
            tag, cls, ln, i = bacnet._read_tag(apdu, i)
            oid = int.from_bytes(apdu[i:i + 4], "big")
            i += 4
            if apdu[i] != 0x1E:
                raise ValueError("RPM-request zonder property-lijst")
            i += 1
            props = []
            while i < len(apdu) and apdu[i] != 0x1F:
                tag, cls, ln, i = bacnet._read_tag(apdu, i)
                props.append(int.from_bytes(apdu[i:i + ln], "big"))
                i += ln
            i += 1
            specs.append(((oid >> 22, oid & 0x3FFFFF), props))
        return specs

    def _serve_rpm(self, src, inv: int, apdu: bytes) -> None:
        self.rpm_requests += 1
        if len(apdu) <= 4 or apdu[4] != 0x0E:
            # Strenge dummy: de body moet met tag [0] openen. Een afwijkende
            # encoding wordt geweigerd, niet stilletjes aanvaard.
            self._send(src, bytes([0x01, 0x00, 0x60, inv, 0x09]))      # unrecognized-service
            return
        if self.rpm_mode == "silent":
            return                          # niets terug: een dood toestel
        if self.rpm_mode == "too_long":
            # Eerste RPM-verzoek: antwoord past niet in één APDU (segmentation
            # not supported, code 54). Een halveren van het blok moet helpen.
            if self.rpm_requests == 1:
                self._error(src, inv, 7, 54, service=bacnet.SERVICE_RPM)
                return
        if self.rpm_mode == "error":
            self._error(src, inv, 5, 45, service=bacnet.SERVICE_RPM)   # services / optional
            return
        if self.rpm_mode == "reject":
            self._send(src, bytes([0x01, 0x00, 0x60, inv, 0x09]))      # unrecognized-service
            return
        if self.rpm_mode == "abort":
            self._send(src, bytes([0x01, 0x00, 0x71, inv, 0x08]))      # server + reply-time
            return
        if self.drop_first_rpm and self.rpm_requests == 1:
            self.dropped_rpm += 1
            return                          # antwoord kwijt: UDP-verlies
        specs = self._parse_rpm(apdu)
        self.specs_seen.append(specs)
        results = []
        for obj, props in specs:
            available = self.props.get(obj)
            entries = []
            for prop in props:
                if available is None or (prop != bacnet.PROP_OBJECT_LIST and prop not in available):
                    entries.append((prop, None, (1, 31)))              # unknown-object
                    continue
                if prop == bacnet.PROP_PRESENT_VALUE and obj == (0, self.partial_error):
                    entries.append((prop, None, (2, 32)))              # unknown-property
                    continue
                entries.append((prop, available[prop], None))
            results.append((obj, entries))
        self._rpm_ack(src, inv, results)

    def _serve_apdu(self, apdu: bytes, src) -> None:
        if len(apdu) < 8 or apdu[0] != 0x00:                # geen Confirmed-Request
            return
        inv, service = apdu[2], apdu[3]
        self.requests += 1
        if self.rpm_mode == "silent":
            return                          # dood toestel: ook losse leesacties stil
        if service == 0x0C:
            self.loose_reads += 1
            self._serve_read_property(src, inv, apdu)
        elif service == bacnet.SERVICE_RPM:
            self._serve_rpm(src, inv, apdu)
        else:
            self._send(src, bytes([0x01, 0x00, 0x60, inv, 0x09]))

    def run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                data, src = self.sock.recvfrom(4096)
            except (socket.timeout, OSError):
                continue
            if len(data) < 6 or data[0] != 0x81:
                continue
            if data[1] not in (bacnet.BVLC_ORIGINAL_UNICAST, bacnet.BVLC_ORIGINAL_BROADCAST):
                continue
            offset = bacnet._npdu_apdu_offset(data[4:])
            if offset is None:
                continue
            try:
                self._serve_apdu(data[4:][offset:], src)
            except ValueError as exc:
                print("dummy-fout:", exc, file=sys.stderr, flush=True)

    def stop(self) -> None:
        self._stop_evt.set()
        self.join(timeout=2.0)
        try:
            self.sock.close()
        except OSError:
            pass


def start(**kwargs) -> FakeDevice:
    dev = FakeDevice(**kwargs)
    dev.start()
    return dev


def client(timeout: float = 0.5) -> bacnet.BacnetClient:
    return bacnet.BacnetClient(bind_ip="127.0.0.1", port=CLIENT_PORT,
                               timeout=timeout, delay=0.0)


def with_fake(fn, **kwargs):
    dev = start(**kwargs)
    c = client()
    try:
        return fn(dev, c)
    finally:
        c.close()
        dev.stop()


def _app():
    """App-instantie zonder poll-thread: alleen wat bn_points/bn_ede nodig heeft."""
    import app as app_mod

    a = app_mod.App.__new__(app_mod.App)
    a.lock = threading.RLock()
    a._bn = None
    a.config = {"bacnet": {}}
    a._bn_obj_cache = {}
    return a


def with_app(fn, **kwargs):
    dev = start(**kwargs)
    os.environ["FLEXPOLL_BACNET_PORT"] = str(CLIENT_PORT)
    a = _app()
    try:
        c = a.bacnet_client()
        c.timeout, c.delay = 0.5, 0.0
        return fn(dev, a)
    finally:
        if a._bn is not None:
            a._bn.close()
        dev.stop()


def _http_app(a):
    """Echte HTTP-server bovenop deze App: (httpd, basis-url).

    AC-2/AC-6/AC-11 vragen de wandkloktijd om de *route*, niet om de
    client-aanroep: json-parsing, handler en serialisatie horen in het bewijs.
    """
    import app as app_mod

    app_mod.Handler.app = a
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_mod.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _stop_http(httpd) -> None:
    import app as app_mod

    httpd.shutdown()
    httpd.server_close()
    app_mod.Handler.app = None                          # type: ignore[assignment]


def _post_points(base: str, body: dict, timeout: float = 20) -> tuple[int, dict]:
    req = urllib.request.Request(
        base + "/api/bacnet/points", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.status, json.loads(res.read().decode("utf-8"))


def all_keys():
    return [(8, DEVICE)] + [(0, i) for i in range(1, AI_COUNT + 1)]


def filled(points) -> int:
    return sum(1 for p in points if p["value"] is not None)


# ----------------------------------------------------------------- scenario's
def test_request_shape_and_split_replies() -> None:
    """Blokken van ≤32 objecten; korte array wordt per index aangevuld."""

    def run(dev, c):
        objs = c.objects("127.0.0.1", DEVICE)
        details = c.read_points("127.0.0.1", [(o["type"], o["inst"]) for o in objs])
        assert len(details) == OBJECTS, len(details)
        assert len(dev.specs_seen) == 11, len(dev.specs_seen)
        sizes = [len(s) for s in dev.specs_seen]
        assert all(n <= bacnet.RPM_BLOCK for n in sizes), sizes
        assert all(n >= 25 for n in sizes[:-1]), sizes
        assert sizes[-1] == OBJECTS - 10 * bacnet.RPM_BLOCK, sizes[-1]
        first_obj, first_props = [s for s in dev.specs_seen[0] if s[0] == (8, DEVICE)][0]
        assert first_props == [bacnet.PROP_OBJECT_NAME], first_props
        ai_spec = [s for s in dev.specs_seen[0] if s[0] == (0, 1)][0]
        assert ai_spec[1] == [bacnet.PROP_OBJECT_NAME, bacnet.PROP_PRESENT_VALUE,
                              bacnet.PROP_UNITS], ai_spec
        assert details[(0, 1)]["value"] == 1.0
        assert details[(0, 1)]["unit"] == 62
        assert details[(8, DEVICE)]["name"].startswith("FlexPoll-")
    with_fake(run, whole_mode="short")


def test_speed_and_request_reduction() -> None:
    """331 punten via POST < 5 s en ≥90% minder verzoeken dan het losse pad."""
    def rpm_run(dev, a):
        httpd, base = _http_app(a)
        try:
            began = time.monotonic()
            status, d = _post_points(base, {"ip": "127.0.0.1", "device": DEVICE})
            elapsed = time.monotonic() - began
        finally:
            _stop_http(httpd)
        assert status == 200, status
        assert len(d["points"]) == OBJECTS, len(d["points"])
        assert all(p["value"] is not None for p in d["points"][1:]), "niet alle waarden"
        return elapsed, dev.requests

    rpm_time, rpm_requests = with_app(rpm_run, whole_mode="full")

    def loose_run(dev, a):
        a.bacnet_client().rpm_supported = False         # referentie: oud los pad
        httpd, base = _http_app(a)
        try:
            status, d = _post_points(base, {"ip": "127.0.0.1", "device": DEVICE})
        finally:
            _stop_http(httpd)
        assert status == 200 and len(d["points"]) == OBJECTS, len(d["points"])
        return dev.requests

    loose_requests = with_app(loose_run, whole_mode="full")
    assert rpm_time <= 5.0, f"RPM-pad duurde {rpm_time:.2f} s"
    assert rpm_requests <= loose_requests * 0.1, \
        f"{rpm_requests} vs {loose_requests} verzoeken — reductie te klein"
    assert rpm_requests == 13, rpm_requests                # 2 inventaris + 11 blokken


def test_split_on_too_long_response() -> None:
    """Een te groot RPM-antwoord halveert het blok; daarna weer volle blokken."""
    def run(dev, c):
        objs = c.objects("127.0.0.1", DEVICE)
        details = c.read_points("127.0.0.1", [(o["type"], o["inst"]) for o in objs])
        assert len(details) == OBJECTS, len(details)
        ai_keys = [k for k in all_keys() if k[0] == 0]
        assert all(details[k]["value_read"] for k in ai_keys), "niet alle waarden"
        sizes = [len(s) for s in dev.specs_seen]
        assert sizes[0] == bacnet.RPM_BLOCK // 2, sizes[:3]
        assert all(n == bacnet.RPM_BLOCK for n in sizes[1:-1]), sizes
        assert sizes[-1] == OBJECTS - bacnet.RPM_BLOCK // 2 - len(sizes[1:-1]) * bacnet.RPM_BLOCK, sizes
        assert dev.rpm_requests == 12, dev.rpm_requests    # 11 blokken + 1 afgekeurd
    with_fake(run, rpm_mode="too_long")


def test_rpm_support_is_per_device() -> None:
    """Eén niet-RPM-toestel zet het snelle pad voor een ander IP niet uit."""
    bad = start(rpm_mode="error")
    good = start(ip="127.0.0.2")
    os.environ["FLEXPOLL_BACNET_PORT"] = str(CLIENT_PORT)
    a = _app()
    try:
        c = a.bacnet_client()
        c.timeout, c.delay = 0.5, 0.0
        first = a.bn_points("127.0.0.1", DEVICE)
        assert len(first["points"]) == OBJECTS, len(first["points"])
        assert all(p["ok"] for p in first["points"] if p["type"] == 0)
        assert bad.rpm_requests == 1, bad.rpm_requests
        assert ("127.0.0.1", bacnet.BACNET_PORT) in c.rpm_unsupported
        second = a.bn_points("127.0.0.2", DEVICE)
        assert len(second["points"]) == OBJECTS, len(second["points"])
        assert all(p["ok"] for p in second["points"] if p["type"] == 0)
        assert good.rpm_requests >= 10, good.rpm_requests
        assert good.loose_reads <= 2, f"{good.loose_reads} losse leesacties"
        assert ("127.0.0.2", bacnet.BACNET_PORT) not in c.rpm_unsupported
    finally:
        if a._bn is not None:
            a._bn.close()
        bad.stop()
        good.stop()


def test_fallback_error_pdu() -> None:
    """Error/reject/abort op 0x0E: terugval op losse reads, 331 gevulde rijen."""
    def run(dev, a):
        d = a.bn_points("127.0.0.1", DEVICE)
        assert len(d["points"]) == OBJECTS, len(d["points"])
        assert d["complete"] is True and d["partial"] is False, d["warning"]
        ai = [p for p in d["points"] if p["type"] == 0]
        assert len(ai) == AI_COUNT and all(p["ok"] for p in ai), \
            [p for p in ai if not p["ok"]][:3]
        assert ai[0]["name"] == "AI 1" and ai[0]["value"] == 1.0, ai[0]
        assert ai[0]["unit"] == "°C", ai[0]
        assert ("127.0.0.1", bacnet.BACNET_PORT) in a._bn.rpm_unsupported
        assert dev.rpm_requests == 1, dev.rpm_requests

    for mode in ("error", "reject", "abort"):
        with_app(run, rpm_mode=mode)


def test_partial_error_result() -> None:
    """Eén error-result geeft alleen dat punt ok=false; geen herkansing."""
    def run(dev, a):
        d = a.bn_points("127.0.0.1", DEVICE)
        assert len(d["points"]) == OBJECTS, len(d["points"])
        target = [p for p in d["points"] if p["type"] == 0 and p["inst"] == 5]
        assert len(target) == 1, target
        assert target[0]["ok"] is False, target[0]
        assert "unknown-property" in (target[0]["error"] or ""), target[0]["error"]
        neighbours = [p for p in d["points"]
                      if p["type"] == 0 and p["inst"] in (4, 6)]
        assert all(p["ok"] and p["value"] is not None for p in neighbours), neighbours
        assert dev.rpm_requests == 11, f"{dev.rpm_requests} — error-result herkanst?"
    with_app(run, partial_error=5)


def test_timeout_retry_once() -> None:
    """Een volledig weggevallen RPM-antwoord wordt precies één keer herkanst."""
    def run(dev, c):
        objs = c.objects("127.0.0.1", DEVICE)
        details = c.read_points("127.0.0.1", [(o["type"], o["inst"]) for o in objs],
                                timeout=0.2)
        assert len(details) == OBJECTS, len(details)
        assert dev.dropped_rpm == 1, dev.dropped_rpm
        assert dev.rpm_requests == 12, dev.rpm_requests       # 11 blokken + 1 herkansing
        assert c.last_points_partial is False
        assert details[(0, 330)]["value"] == 330.0
    with_fake(run, drop_first_rpm=True)


def test_reject_abort_not_retried() -> None:
    """Reject en Abort zijn definitief: één verzoek, dan meteen terugval."""
    def run(dev, c):
        try:
            c.read_points("127.0.0.1", all_keys(), timeout=0.2)
        except bacnet.BacnetError as exc:                   # mag, maar liever niet
            raise AssertionError(f"onverwachte fout zonder terugval: {exc}") from None
        assert dev.rpm_requests == 1, dev.rpm_requests
        assert c.rpm_supported is True                     # geen clientbrede uitschakeling
        assert ("127.0.0.1", bacnet.BACNET_PORT) in c.rpm_unsupported
        assert dev.loose_reads >= AI_COUNT, dev.loose_reads

    for mode in ("reject", "abort"):
        with_fake(run, rpm_mode=mode)


def test_budget_defaults() -> None:
    """0/negatief/onparseerbaar schakelt de begrenzing niet uit."""
    import app as app_mod

    assert app_mod.BACNET_POINTS_BUDGET == 120.0
    assert app_mod.BACNET_EDE_BUDGET == 300.0
    for bad in (None, "", 0, 0.0, -5, "rommel", float("nan"), float("inf")):
        assert app_mod._bacnet_budget(bad, 120.0) == 120.0, bad
        assert app_mod._bacnet_budget(bad, 300.0) == 300.0, bad
    assert app_mod._bacnet_budget("45", 120.0) == 45.0
    assert app_mod._bacnet_budget(2.5, 120.0) == 2.5


def test_budget_expiry_partial() -> None:
    """Verstrijkt het budget: HTTP 200 met deelpunten, partial=true en warning."""
    import app as app_mod

    def run(dev, a):
        app_mod.Handler.app = a
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_mod.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{httpd.server_address[1]}/api/bacnet/points",
                data=json.dumps({"ip": "127.0.0.1", "device": DEVICE,
                                 "budget": 0.35}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=15) as res:
                assert res.status == 200, res.status
                d = json.loads(res.read().decode("utf-8"))
        finally:
            httpd.shutdown()
            app_mod.Handler.app = None                          # type: ignore[assignment]
        assert d["partial"] is True, d
        assert "tijdsbudget" in d["warning"], d["warning"]
        assert 0 < filled(d["points"]) < OBJECTS, filled(d["points"])
        # B1: een punt zonder waarde is niet geslaagd. Het budget mag geen
        # rijen met ok=True en value=None achterlaten.
        for p in d["points"]:
            if p["type"] in bacnet.PV_OBJECT_TYPES and p["value"] is None:
                assert p["ok"] is False, p
                assert p["error"] == "tijdsbudget bereikt", p
    with_app(run, delay=0.04)


def test_budget_expiry_ede_json() -> None:
    """EDE met verstrijken budget: JSON-fout, nooit een half zip-bestand."""
    import app as app_mod

    def run(dev, a):
        app_mod.Handler.app = a
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_mod.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            url = (f"http://127.0.0.1:{httpd.server_address[1]}/api/bacnet/ede.zip"
                   f"?ip=127.0.0.1&device={DEVICE}&budget=0.05")
            try:
                urllib.request.urlopen(url, timeout=15)
            except urllib.error.HTTPError as exc:
                assert exc.code == 502, exc.code
                assert exc.headers.get("Content-Type", "").startswith("application/json"), \
                    exc.headers.get("Content-Type")
                body = json.loads(exc.read().decode("utf-8"))
                assert "budget" in body.get("error", ""), body
            else:
                raise AssertionError("verstreken budget gaf een zip in plaats van JSON")
        finally:
            httpd.shutdown()
            app_mod.Handler.app = None                          # type: ignore[assignment]
    with_app(run, delay=0.04)


def test_object_list_cache() -> None:
    """Pagina 2 hergebruikt de object-list; TTL-verval leest opnieuw."""
    import app as app_mod

    def run(dev, a):
        first = a.bn_points("127.0.0.1", DEVICE, limit=100, offset=0)
        assert len(first["points"]) == 100, len(first["points"])
        inventory = dev.inventory_reads
        assert inventory >= 1, inventory
        second = a.bn_points("127.0.0.1", DEVICE, limit=100, offset=100)
        assert len(second["points"]) == 100, len(second["points"])
        assert dev.inventory_reads == inventory, \
            f"{dev.inventory_reads - inventory} extra inventarisatie-leesacties"
        assert second["points"][0]["inst"] == 100, second["points"][0]
        assert second["points"][-1]["inst"] == 199, second["points"][-1]
        assert second["total"] == OBJECTS and second["complete"] is True
        old_ttl = app_mod.BACNET_OBJECT_CACHE_TTL
        app_mod.BACNET_OBJECT_CACHE_TTL = 0
        try:
            a.bn_points("127.0.0.1", DEVICE, limit=100, offset=200)
            assert dev.inventory_reads > inventory, "vervallen cache niet opnieuw gelezen"
        finally:
            app_mod.BACNET_OBJECT_CACHE_TTL = old_ttl
    with_app(run)


def test_silent_device_bounded() -> None:
    """Een stil toestel eindigt binnen budget+2 s met een nette JSON-fout."""
    def run(dev, a):
        httpd, base = _http_app(a)
        began = time.monotonic()
        try:
            try:
                status, _body = _post_points(
                    base, {"ip": "127.0.0.1", "device": DEVICE, "budget": 1.0},
                    timeout=20)
            except urllib.error.HTTPError as exc:
                status = exc.code
                ctype = exc.headers.get("Content-Type", "")
                body = json.loads(exc.read().decode("utf-8"))
            else:
                raise AssertionError(f"stil toestel gaf HTTP {status} in plaats van 502")
            elapsed = time.monotonic() - began
        finally:
            _stop_http(httpd)
        assert status == 502, status
        assert ctype.startswith("application/json"), ctype
        assert body.get("error"), body
        assert elapsed <= 1.0 + 2.0, f"{elapsed:.2f} s bij budget 1.0"

    with_app(run, rpm_mode="silent")


def test_rpm_encoding_is_standard() -> None:
    """Gouden bytes: de RPM-request-body, onafhankelijk van de client.

    listOfReadAccessSpecs is tag [0] (0x0E); per object volgt objectIdentifier
    [0] en listOfPropertyReferences [1] (0x1E). Beide lijsten sluiten met 0x1F.
    """
    body = bacnet.encode_rpm([(8, 1234, [77])])
    assert body.hex() == "0e0c020004d21e094d1f1f", body.hex()


if __name__ == "__main__":
    import fcntl

    _lock = open("/tmp/flexpoll-bacnet-rpm-test.lock", "w")
    fcntl.flock(_lock, fcntl.LOCK_EX)      # 47808 is één per machine: geen parallelle runs
    print("BACnet RPM zelftest (331 objecten)")
    try:
        check("RPM vraagt in blokken van ≤32", test_request_shape_and_split_replies)
        check("RPM-encoding is standaardconform", test_rpm_encoding_is_standard)
        check("RPM is snel en vraagt ≥90% minder", test_speed_and_request_reduction)
        check("te groot antwoord halveert het blok", test_split_on_too_long_response)
        check("RPM-ondersteuning is per toestel", test_rpm_support_is_per_device)
        check("terugval bij error/reject/abort", test_fallback_error_pdu)
        check("één error-result raakt één punt", test_partial_error_result)
        check("weggevallen antwoord één keer herkanst", test_timeout_retry_once)
        check("reject/abort niet herkanst", test_reject_abort_not_retried)
        check("budget standaard bij 0/negatief/rommel", test_budget_defaults)
        check("budgetverloop geeft deelpunten", test_budget_expiry_partial)
        check("EDE-budgetverloop is JSON", test_budget_expiry_ede_json)
        check("object-list-cache voor pagina 2", test_object_list_cache)
        check("stil toestel begrensd", test_silent_device_bounded)
    except RuntimeError as exc:
        FAILED.append(str(exc))
        print(f"  FOUT — {exc}")

    if FAILED:
        print(f"MISLUKT: {', '.join(FAILED)}")
        sys.exit(1)
    print("geslaagd")
