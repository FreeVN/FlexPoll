# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
"""Zelftest voor de BACnet/IP-routering: Foreign Device + Forwarded-NPDU.

Geen echte BBMD nodig: de test speelt zelf BBMD op loopback. Dat is precies het
deel dat op een werf niet te debuggen is — een BBMD die antwoordt maar waarvan
wij de doorgestuurde pakketten verkeerd ontleden (verkeerde offset) ziet er in
de UI uit als "geen toestellen", terwijl het netwerk perfect is.
"""

from __future__ import annotations

import socket
import struct
import sys
import time

import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bacnet

FAILED = []


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"  {name}: ok")
    except AssertionError as exc:
        FAILED.append(name)
        print(f"  {name}: FOUT — {exc}")


def i_am(device: int, vendor: int = 999) -> bytes:
    """I-Am voor device N als APDU (unconfirmed service 0)."""
    oid = (8 << 22) | (device & 0x3FFFFF)
    apdu = bytes([0x10, 0x00]) + b"\xC4" + struct.pack(">I", oid) \
        + b"\x91\x05" + b"\x91\x00" + b"\x91" + bytes([vendor & 0xFF])
    return apdu


def npdu(apdu: bytes) -> bytes:
    return bytes([0x01, 0x00]) + apdu


def client(port: int) -> bacnet.BacnetClient:
    c = bacnet.BacnetClient(port=port, timeout=1.0, delay=0.0)
    return c


def test_forwarded_npdu() -> None:
    """Forwarded-NPDU (BVLC 0x04) heeft 6 extra bytes: die offset moet kloppen."""
    c = client(47901)
    bbmd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        orig = socket.inet_aton("10.9.8.7") + struct.pack(">H", 47808)
        payload = npdu(i_am(4242, 77))
        packet = bytes([0x81, 0x04]) + struct.pack(">H", len(payload) + 4 + 6) + orig + payload
        bbmd.sendto(packet, ("127.0.0.1", 47901))
        apdu, src = c._recv(time.time() + 1.0)
        assert src[0] == "10.9.8.7", f"bron-IP komt niet uit de forwarded header: {src}"
        assert apdu[0] == 0x10 and apdu[1] == 0x00, f"geen I-Am: {apdu.hex()}"
        dev = int.from_bytes(apdu[3:7], "big") & 0x3FFFFF
        assert dev == 4242, f"device-id verkeerd gelezen: {dev}"
    finally:
        bbmd.close()
        c.close()


def _fd_server(port: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", port))
    s.settimeout(0.05)
    return s


def _serve_once(s: socket.socket, result: int, hits: list) -> None:
    try:
        data, src = s.recvfrom(512)
    except socket.timeout:
        return
    except OSError:
        return                                  # socket intussen gesloten
    if len(data) >= 7 and data[4] == 0x05:      # BVLC Register-Foreign-Device
        hits.append(int.from_bytes(data[5:7], "big"))
        # BVLC-Result: 81 00 00 06 <result 2 bytes> (lengte = 6, totaal 6 bytes)
        reply = bytes([0x81, 0x00, 0x00, 0x06]) + struct.pack(">H", result)
        s.sendto(reply, src)


def test_register_ok() -> None:
    hits: list[int] = []
    srv = _fd_server(47902)
    c = client(47903)
    import threading

    stop: list[int] = []

    def loop() -> None:
        while not stop:
            _serve_once(srv, 0, hits)
            time.sleep(0.02)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    try:
        res = c.register_foreign_device("127.0.0.1", 47902, ttl=30, wait=1.0)
        assert res["ok"] and res["ttl"] == 30, res
        assert c.fd and c.fd["ip"] == "127.0.0.1", "fd-status niet gezet"
        status = c.fd_status() or {}
        assert status.get("remaining", 0) > 0, "TTL-aftelling ontbreekt"
        assert len(hits) == 1, f"registratie niet op de BBMD gezien: {hits}"
    finally:
        stop.append(1)
        srv.close()
        c.close()


def test_register_denied() -> None:
    c = client(47904)
    srv = _fd_server(47905)
    import threading

    t = threading.Thread(target=_serve_once, args=(srv, 1, []), daemon=True)
    t.start()
    try:
        try:
            c.register_foreign_device("127.0.0.1", 47905, ttl=30, wait=1.0)
        except bacnet.BacnetError as exc:
            assert "weigert" in str(exc), f"verkeerde fout: {exc}"
        else:
            raise AssertionError("BBMD-result 1 werd aanvaard als succes")
    finally:
        srv.close()
        c.close()


def test_keepalive() -> None:
    """Op TTL/2 opnieuw aanmelden — anders valt de FD er stil uit."""
    c = client(47906)
    srv = _fd_server(47907)
    try:
        import threading

        hits: list[int] = []
        stop: list[int] = []

        def loop() -> None:
            while not stop:
                _serve_once(srv, 0, hits)
                time.sleep(0.02)

        t = threading.Thread(target=loop, daemon=True)
        t.start()
        c.register_foreign_device("127.0.0.1", 47907, ttl=30, wait=1.0)
        assert len(hits) == 1, f"eerste registratie niet gezien: {hits}"
        assert c.fd is not None
        c.fd["expires"] = time.time() - 1          # TTL verstreken
        c.fd_keepalive()
        time.sleep(0.1)
        assert len(hits) >= 2, f"geen keepalive-registratie: {hits}"
        stop.append(1)
    finally:
        srv.close()
        c.close()


def test_unicast_probe() -> None:
    """Echte route-test: unicast Who-Is naar een toestel op deze machine.

    Draait de testslave niet, dan is dit geen failure maar een skip — CI heeft
    geen BACnet-hardware en mag daar niet op zakken.
    """
    c = client(47908)
    try:
        found = c.whois(timeout=1.5, subnets=[], unicast=["127.0.0.1"])
    except bacnet.BacnetError:
        found = []
    finally:
        c.close()
    if not found:
        print("    (overgeslagen: geen BACnet-testslave op 127.0.0.1:47808)")
        return
    assert found[0]["device"] > 0, f"device-id ontbreekt: {found[0]}"


print("BACnet-routering zelftest")
check("Forwarded-NPDU ontleden", test_forwarded_npdu)
check("Foreign Device aanmelden", test_register_ok)
check("BBMD weigert registratie", test_register_denied)
check("Keepalive vóór TTL", test_keepalive)
check("Unicast-probe", test_unicast_probe)

if FAILED:
    print(f"MISLUKT: {', '.join(FAILED)}")
    sys.exit(1)
print("geslaagd")
