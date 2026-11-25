#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
"""Zelftest voor BACnet-punten: álles lezen, niets stil afkappen, pagineren.

Geen hardware en geen pytest: deze test speelt zelf een toestel met 331 objecten
(device + 330 analog inputs) op 127.0.0.1. Drie fouten die op de bank onzichtbaar
zijn en hier wel:

* een **80/400-plafond**: de client leverde 80 rijen terwijl het toestel er 330
  had, en de EDE-export kapte op 400 af;
* **geen herkansing per leesactie**: één verloren UDP-antwoord kostte een punt
  (of, erger, de rest van de lijst — de oude lus stopte bij de eerste fout);
* een **te korte object-list**: het toestel zendt de array in één APDU, maar 330
  ids passen daar niet in. Wat binnenkwam werd als "de lijst" beschouwd.

De dummy laat deterministisch 1 op de 10 antwoorden vallen (teller-based, geen
random) en heeft een modus met één permanent onleesbare index. Het toestel
luistert op 127.0.0.1:47808 — de vaste BACnet/IP-poort, want ``objects()`` leest
het toestel op die poort; de client zelf bindt op een eigen poort zodat een
slave of simulator op de bank de uitslag niet bepaalt.

    python3 tests/bacnet_points_test.py            # alle scenario's
    python3 tests/bacnet_points_test.py --serve 47808   # dummy voor curl/app
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
import zipfile
import io
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bacnet                                              # noqa: E402

DEVICE = 1234
VENDOR = 999
AI_COUNT = 330
OBJECTS = AI_COUNT + 1                      # device-object + 330 AI's
# De client leest een toestel op de vaste BACnet/IP-poort; de dummy moet daar dus
# luisteren. Unicast naar 127.0.0.1 valt op deze socket toe, ook als er op de
# bank een slave op 0.0.0.0:47808 luistert.
FAKE_PORT = bacnet.BACNET_PORT
CLIENT_PORT = 47961
HTTP_PORT = 47898

FAILED: list[str] = []


def check(name: str, fn) -> None:
    """Draai één scenario. Elke assertie hier bewijst een criterium: geen skips."""
    try:
        fn()
        print(f"  {name}: ok")
    except Exception as exc:                        # noqa: BLE001 — testrunner
        FAILED.append(name)
        print(f"  {name}: FOUT — {type(exc).__name__}: {exc}")


# --------------------------------------------------------------------- dummy
class FakeDevice(threading.Thread):
    """BACnet/IP-toestel met ``ai_count`` analog inputs, op één UDP-poort.

    ``mode``        "normal" of "flaky" (1 op ``drop_every`` antwoorden weg).
    ``whole_mode``  wat een leesactie op de héle object-list (geen index) geeft:
                    "short" = de eerste 100 ids (zoals een APDU-grens doet),
                    "full"  = alles, "error" = segmentation-not-supported.
    ``fail_index``  index op de object-list dat permanent een error geeft.
    """

    def __init__(self, ip: str = "127.0.0.1", port: int = FAKE_PORT,
                 device: int = DEVICE, ai_count: int = AI_COUNT, mode: str = "normal",
                 drop_every: int = 10, whole_mode: str = "short",
                 fail_index: int | None = None):
        super().__init__(daemon=True)
        self.device = device
        self.mode = mode
        self.drop_every = max(2, int(drop_every))
        self.whole_mode = whole_mode
        self.fail_index = fail_index
        self.order = [(8, device)] + [(0, i) for i in range(1, ai_count + 1)]
        self.props: dict[tuple[int, int], dict] = {
            (8, device): {77: f"FlexPoll-{len(self.order)}", 70: "Testbank",
                          120: VENDOR, 121: 8, 44: 2},
        }
        for i in range(1, ai_count + 1):
            self.props[(0, i)] = {77: f"AI {i}", 28: f"Test AI {i}", 85: float(i), 117: 62}
        self.requests = 0
        self.dropped = 0
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
        packet = bytes([0x81, bacnet.BVLC_ORIGINAL_UNICAST]) \
            + struct.pack(">H", len(npdu) + 4) + npdu
        try:
            self.sock.sendto(packet, src)
        except OSError:
            pass

    def _ack(self, src, inv: int, obj: tuple[int, int], prop: int,
             body: bytes, index: int | None) -> None:
        head = bytes([0x30, inv, 0x0C]) \
            + bacnet._ctx(0, struct.pack(">I", (obj[0] << 22) | obj[1])) \
            + bacnet._ctx(1, bytes([prop]))
        if index is not None:
            head += bacnet._ctx(2, bacnet._uint_bytes(index))
        self._send(src, bytes([0x01, 0x00]) + head + b"\x3e" + body + b"\x3f")

    def _error(self, src, inv: int, code: int) -> None:
        err = bytes([0x50, inv, 0x0C]) \
            + bacnet._ctx(2, bacnet._app_enum(0)) + bacnet._ctx(3, bacnet._app_enum(code))
        self._send(src, bytes([0x01, 0x00]) + err)

    # -- verwerken ----------------------------------------------------------
    def _serve_apdu(self, apdu: bytes, src) -> None:
        if len(apdu) < 8 or apdu[0] != 0x00:                # geen Confirmed-Request
            return
        inv, service = apdu[2], apdu[3]
        if service != 0x0C:                                 # alleen ReadProperty
            self._send(src, bytes([0x01, 0x00, 0x60, inv, 0x09]))
            return
        self.requests += 1
        if self.mode == "flaky" and self.requests % self.drop_every == 0:
            self.dropped += 1
            return                          # antwoord kwijt: precies het UDP-probleem
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

        props = self.props.get(obj)
        if props is None or (prop != bacnet.PROP_OBJECT_LIST and prop not in props):
            self._error(src, inv, 31)                       # unknown-object
            return
        if prop == bacnet.PROP_OBJECT_LIST:
            if index is None:
                if self.whole_mode == "error":
                    self._error(src, inv, 54)               # segmentation-not-supported
                    return
                ids = self.order if self.whole_mode == "full" else self.order[:100]
                body = b"".join(bytes([0xC4]) + struct.pack(">I", (t << 22) | inst)
                                for t, inst in ids)
            elif index == 0:
                body = bacnet._app_uint(len(self.order))
            elif index == self.fail_index:
                self._error(src, inv, 31)                   # permanent onleesbaar
                return
            elif 1 <= index <= len(self.order):
                t, inst = self.order[index - 1]
                body = bytes([0xC4]) + struct.pack(">I", (t << 22) | inst)
            else:
                self._error(src, inv, 42)                   # invalid-array-index
                return
            self._ack(src, inv, obj, prop, body, index)
            return

        if prop in (77, 28, 70):
            body = bacnet._app_str(props[prop])
        elif prop in (85, 117) and obj[0] in (0, 1, 2):
            body = bacnet._app_real(float(props[prop]))
        elif prop == 85 and obj[0] in (3, 4, 8):
            body = bacnet._app_bool(bool(props[prop]))
        else:
            body = bacnet._app_uint(int(props[prop]))
        self._ack(src, inv, obj, prop, body, index)

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
            self._serve_apdu(data[4:][offset:], src)

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


def client(timeout: float = 0.08) -> bacnet.BacnetClient:
    """Client op een eigen poort; zendt (zoals de app) naar BACnet/IP 47808."""
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


def with_app(fn, **kwargs):
    """Zoals with_fake, maar de client is die van de App (FLEXPOLL_BACNET_PORT).

    Geen tweede socket op dezelfde poort: de App-client bindt op CLIENT_PORT en
    moet dus de enige zijn, anders belandt het antwoord bij de verkeerde socket.
    """
    dev = start(**kwargs)
    os.environ["FLEXPOLL_BACNET_PORT"] = str(CLIENT_PORT)
    a = _app()
    try:
        c = a.bacnet_client()
        c.timeout, c.delay = 0.08, 0.0
        return fn(dev, a)
    finally:
        if a._bn is not None:
            a._bn.close()
        dev.stop()


# ----------------------------------------------------------------- scenario's
def test_objects_complete() -> None:
    """Te korte array (100 van 331) wordt per index aangevuld: 331 objecten."""
    def run(dev, c):
        objs = c.objects("127.0.0.1", DEVICE)
        assert len(objs) == OBJECTS, f"{len(objs)} objecten, verwacht {OBJECTS}"
        assert objs[0]["type"] == 8 and objs[0]["inst"] == DEVICE, objs[0]
        assert [o["inst"] for o in objs[1:]] == list(range(1, AI_COUNT + 1)), \
            "niet alle analog inputs, of in de verkeerde volgorde"
        assert c.last_objects_complete is True, c.last_objects_warning
        assert c.last_objects_warning == "", c.last_objects_warning
        assert c.last_objects_missing == [], c.last_objects_missing
    with_fake(run)


def test_objects_flaky() -> None:
    """1 op 10 verloren antwoorden kost geen object (herkansing per leesactie)."""
    def run(dev, c):
        objs = c.objects("127.0.0.1", DEVICE)
        assert dev.dropped > 0, "dummy heeft niets laten vallen — scenario niet getest"
        assert len(objs) == OBJECTS, f"{len(objs)} objecten met weggevallen antwoorden"
        assert c.last_objects_complete is True, c.last_objects_warning
    with_fake(run, mode="flaky")


def test_objects_never_truncates_on_error() -> None:
    """Eén permanent onleesbare index: 330 van 331, expliciet onvolledig gemeld."""
    def run(dev, c):
        objs = c.objects("127.0.0.1", DEVICE)
        assert len(objs) == OBJECTS - 1, f"{len(objs)} objecten, verwacht {OBJECTS - 1}"
        assert c.last_objects_complete is False, "tekort niet gemarkeerd"
        assert "7" in c.last_objects_warning, c.last_objects_warning
        assert c.last_objects_missing == [7], c.last_objects_missing
    with_fake(run, whole_mode="error", fail_index=7)


def test_error_is_not_retried() -> None:
    """Een error-PDU is definitief: geen drie pogingen, meteen de echte reden."""
    def run(dev, c):
        try:
            c.read_property("127.0.0.1", 8, DEVICE, bacnet.PROP_OBJECT_LIST, 7)
        except bacnet.BacnetServerError as exc:
            assert "weigert" in str(exc), exc
        else:
            raise AssertionError("error-PDU als succes gelezen")
        assert dev.requests == 1, f"{dev.requests} pogingen voor één error-antwoord"
    with_fake(run, whole_mode="error", fail_index=7)


def _app():
    """App-instantie zonder poll-thread: alleen wat bn_points nodig heeft."""
    import app as app_mod

    a = app_mod.App.__new__(app_mod.App)
    a.lock = threading.RLock()
    a._bn = None
    a.config = {"bacnet": {}}
    return a


def test_bn_points_all() -> None:
    """Zonder limit: alle 331 punten, total=331, complete, elk AI-punt ok."""
    def run(dev, a):
        d = a.bn_points("127.0.0.1", DEVICE)
        assert set(d) >= {"ip", "device", "points", "total", "offset", "complete",
                          "partial", "warning"}, sorted(d)
        assert d["ip"] == "127.0.0.1" and d["device"] == DEVICE
        assert len(d["points"]) == OBJECTS, len(d["points"])
        assert d["total"] == OBJECTS, d["total"]
        assert d["complete"] is True and d["partial"] is False, d
        assert d["warning"] == "", d["warning"]
        ai = [p for p in d["points"] if p["type"] == 0]
        assert len(ai) == AI_COUNT, len(ai)
        assert all(p["ok"] for p in ai), [p for p in ai if not p["ok"]][:3]
        assert ai[0]["name"] == "AI 1" and ai[0]["value"] == 1.0, ai[0]
    with_app(run)


def test_bn_points_pagination() -> None:
    """limit/offset als paginering; total blijft het totaal van het toestel."""
    def run(dev, a):
        first = a.bn_points("127.0.0.1", DEVICE, limit=100, offset=0)
        assert len(first["points"]) == 100, len(first["points"])
        assert first["total"] == OBJECTS, first["total"]
        assert first["offset"] == 0 and first["limit"] == 100
        last = a.bn_points("127.0.0.1", DEVICE, limit=100, offset=300)
        assert len(last["points"]) == OBJECTS - 300, len(last["points"])
        assert last["total"] == OBJECTS, last["total"]
        assert last["points"][-1]["type"] == 0 and last["points"][-1]["inst"] == AI_COUNT
    with_app(run)


def test_bn_points_flaky() -> None:
    """Ook met 1 op 10 weggevallen antwoorden: 331 rijen, alle AI-punten ok."""
    def run(dev, a):
        d = a.bn_points("127.0.0.1", DEVICE)
        assert dev.dropped > 0, "dummy heeft niets laten vallen — scenario niet getest"
        assert len(d["points"]) == OBJECTS, len(d["points"])
        assert d["complete"] is True, d["warning"]
        assert all(p["ok"] for p in d["points"]), \
            [p for p in d["points"] if not p["ok"]][:3]
    with_app(run, mode="flaky")


def test_ede_package_complete() -> None:
    """EDE-export bevat alle 331 datapunten, ook bij weggevallen antwoorden."""
    def run(dev, c):
        pack = c.ede_package("127.0.0.1", DEVICE, project="T029")
        assert pack["objects"] == OBJECTS, pack["objects"]
        assert len(pack["files"]) == 4, list(pack["files"])
        name = [n for n in pack["files"] if n.endswith("_EDE.csv")][0]
        text = pack["files"][name].decode("utf-8-sig")
        rows = [ln for ln in text.splitlines()
                if ln and not ln.startswith(("#", "PROJECT_NAME", "VERSION",
                                             "TIMESTAMP", "AUTHOR"))]
        assert len(rows) == OBJECTS, f"{len(rows)} EDE-rijen, verwacht {OBJECTS}"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for fn, data in pack["files"].items():
                zf.writestr(fn, data)
        assert len(zipfile.ZipFile(io.BytesIO(buf.getvalue())).namelist()) == 4
    with_fake(run, mode="flaky")


def test_ede_refuses_incomplete() -> None:
    """Een onvolledige object-list geeft geen half EDE-bestand maar een fout."""
    def run(dev, c):
        try:
            c.ede_package("127.0.0.1", DEVICE)
        except bacnet.BacnetError as exc:
            assert "onvolledig" in str(exc), exc
        else:
            raise AssertionError("EDE-export van een onvolledige lijst toegestaan")
    with_fake(run, whole_mode="error", fail_index=7)


def test_http_ede_error_is_json() -> None:
    """Een fout in de export is JSON met status 502, nooit een half zip-bestand."""
    import app as app_mod

    class Stub:
        def bn_ede_package(self, *a, **kw):
            raise bacnet.BacnetError("device antwoordt niet")

        def state(self):
            return {}

    app_mod.Handler.app = Stub()                                # type: ignore[assignment]
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_mod.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/api/bacnet/ede.zip?ip=127.0.0.1&device=1234"
        try:
            urllib.request.urlopen(url, timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 502, exc.code
            assert exc.headers.get("Content-Type", "").startswith("application/json"), \
                exc.headers.get("Content-Type")
            body = json.loads(exc.read().decode("utf-8"))
            assert "antwoordt niet" in body.get("error", ""), body
        else:
            raise AssertionError("dode export gaf geen foutstatus")
    finally:
        httpd.shutdown()
        app_mod.Handler.app = None                              # type: ignore[assignment]


def test_http_points_all() -> None:
    """POST /api/bacnet/points zonder limit levert via HTTP alle 331 punten."""
    import app as app_mod

    def run(dev, a):
        app_mod.Handler.app = a
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), app_mod.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{httpd.server_address[1]}/api/bacnet/points",
                data=json.dumps({"ip": "127.0.0.1", "device": DEVICE}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=30) as res:
                d = json.loads(res.read().decode("utf-8"))
            assert len(d["points"]) == OBJECTS, len(d["points"])
            assert d["total"] == OBJECTS and d["complete"] is True, \
                (d["total"], d["complete"], d["warning"])
        finally:
            httpd.shutdown()
            app_mod.Handler.app = None                          # type: ignore[assignment]
    with_app(run)


def serve(port: int) -> None:
    """Dummy voor handmatige controle: app.py ertegenaan, curl ernaar."""
    dev = FakeDevice(port=port)
    dev.start()
    print(f"BACnet dummy op 127.0.0.1:{port}: device {DEVICE} + {AI_COUNT} analog inputs",
          flush=True)
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        dev.stop()


if __name__ == "__main__":
    if "--serve" in sys.argv:
        idx = sys.argv.index("--serve")
        serve(int(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else FAKE_PORT)
        sys.exit(0)

    print("BACnet-punten zelftest (331 objecten)")
    try:
        check("331 objecten compleet uit korte array", test_objects_complete)
        check("1 op 10 antwoorden weg", test_objects_flaky)
        check("onleesbare index wordt gemeld", test_objects_never_truncates_on_error)
        check("error-PDU wordt niet herkanst", test_error_is_not_retried)
        check("bn_points zonder limit = alles", test_bn_points_all)
        check("bn_points pagineert op limit/offset", test_bn_points_pagination)
        check("bn_points met weggevallen antwoorden", test_bn_points_flaky)
        check("EDE-export compleet", test_ede_package_complete)
        check("EDE weigert onvolledige lijst", test_ede_refuses_incomplete)
        check("EDE-fout is JSON, geen half zip", test_http_ede_error_is_json)
        check("POST /api/bacnet/points = alles", test_http_points_all)
    except RuntimeError as exc:
        FAILED.append(str(exc))
        print(f"  FOUT — {exc}")

    if FAILED:
        print(f"MISLUKT: {', '.join(FAILED)}")
        sys.exit(1)
    print("geslaagd")
