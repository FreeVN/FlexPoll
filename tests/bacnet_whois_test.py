# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
"""Zelftest voor BACnet/IP Who-Is-discovery: herhaalronden, dedupe en NPDU-koppen.

Geen hardware: de test speelt zelf toestellen op 127.0.0.1 en 127.0.0.2. Drie
fouten die op een werf onzichtbaar zijn en hier wel:

* één Who-Is = één kans op verlies (UDP) — een toestel dat pas op de tweede
  vraag antwoordt, viel stil weg;
* dedupe op device-instance alleen — twee toestellen met hetzelfde nummer op
  een verschillend IP leverden één kaart op;
* NPDU-control 0x20 als "netwerklaag" negeren — een I-Am met DNET-kop (het pad
  via een router of BBMD) werd gedropt, terwijl een echt netwerklaag-bericht
  (0x80) juist niet genegeerd werd.

De client bindt op 127.0.0.1 en elk scenario zendt naar een eigen testpoort, niet
naar 47808. Daardoor bepaalt geen enkel toestel, geen testslave en geen BBMD op
de testbank de uitslag: alleen de fake-toestellen in dit bestand luisteren op de
poort waar de Who-Is heen gaat. Het no-reply-scenario zendt zelfs naar een dode
poort. Elk scenario bewijst een acceptatiecriterium, dus een omgeving die een
scenario niet kan draaien is een fout — geen stilzwijgende skip die `make check`
groen houdt zonder bewijs.
"""

from __future__ import annotations

import os
import socket
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bacnet

FAILED: list[str] = []
SKIPPED: list[str] = []

DEVICE = 4242
VENDOR = 99
# Doelpoort van de Who-Is in deze tests. Niet 47808: daar luistert op een
# testbank vaak een echte slave of simulator, en die mag de uitslag niet bepalen.
TEST_PORT = 47940
# Poort waar aantoonbaar niemand antwoordt (voor het no-reply-scenario).
DEAD_PORT = 47999


class Skip(Exception):
    """Deze omgeving kan het scenario niet draaien (bv. adres niet bindbaar)."""


def check(name: str, fn, required: bool = True) -> None:
    """Draai één scenario.

    ``required`` zegt of het scenario een acceptatiecriterium bewijst. Zo ja, dan
    is een ``Skip`` een fout: een omgeving die 127.0.0.2 niet kan binden mag het
    dedupe-bewijs niet stilzwijgend laten vallen en ``make check`` groen houden.
    """
    try:
        fn()
        print(f"  {name}: ok")
    except Skip as exc:
        if required:
            FAILED.append(name)
            print(f"  {name}: FOUT — omgeving kan dit criterium niet bewijzen: {exc}")
        else:
            SKIPPED.append(name)
            print(f"  {name}: overgeslagen — {exc}")
    except Exception as exc:                        # noqa: BLE001 — testrunner
        FAILED.append(name)
        print(f"  {name}: FOUT — {type(exc).__name__}: {exc}")


def i_am(device: int = DEVICE, vendor: int = VENDOR) -> bytes:
    """I-Am als APDU (unconfirmed service 0) voor device ``device``."""
    oid = (8 << 22) | (device & 0x3FFFFF)
    return bytes([0x10, 0x00]) + b"\xC4" + struct.pack(">I", oid) \
        + b"\x91\x05" + b"\x91\x00" + b"\x91" + bytes([vendor & 0xFF])


class FakeDevice(threading.Thread):
    """Speelt één BACnet-toestel op een loopback-adres.

    ``answer_after`` — op de hoeveelste Who-Is het antwoordt (1 = meteen).
    ``control``      — control-byte van de NPDU waarmee de I-Am toekomt:
                       0x00 gewoon, 0x20 met DNET-kop, 0x80 netwerklaag-bericht.
    """

    def __init__(self, ip: str, device: int = DEVICE, vendor: int = VENDOR,
                 answer_after: int = 1, control: int = 0x00,
                 port: int = TEST_PORT):
        super().__init__(daemon=True)
        self.ip = ip
        self.device = device
        self.vendor = vendor
        self.answer_after = answer_after
        self.control = control
        self.port = port
        self.whois_count = 0
        self.iam_count = 0
        self._stop = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # SO_REUSEADDR: op een testbank kan al een slave op 0.0.0.0:47808
        # luisteren. Linux levert unicast dan aan het meest specifieke adres.
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind((ip, port))
        except OSError as exc:
            self.sock.close()
            raise Skip(f"kan {ip}:{port} niet binden: {exc}") from None
        self.sock.settimeout(0.05)

    # -- antwoorden ---------------------------------------------------------
    def _iam_npdu(self) -> bytes:
        apdu = i_am(self.device, self.vendor)
        if self.control & 0x80:
            # Netwerklaag-bericht (type 0x00) met daarachter bytes die op een
            # I-Am lijken: die mogen niet als APDU gelezen worden.
            return bytes([0x01, 0x80]) + apdu
        if self.control & 0x20:
            # DNET 0x0000, DLEN 0, hopcount 255 — zoals een toestel achter een
            # router of BBMD antwoordt.
            return bytes([0x01, 0x20, 0x00, 0x00, 0x00, 0xFF]) + apdu
        return bytes([0x01, 0x00]) + apdu

    def _reply(self, npdu: bytes, src) -> None:
        packet = bytes([0x81, bacnet.BVLC_ORIGINAL_UNICAST]) \
            + struct.pack(">H", len(npdu) + 4) + npdu
        try:
            self.sock.sendto(packet, src)
        except OSError:
            pass

    def run(self) -> None:
        while not self._stop.is_set():
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
            apdu = data[4:][offset:]
            if apdu[:2] == b"\x10\x08":                 # Who-Is
                self.whois_count += 1
                if self.whois_count >= self.answer_after:
                    self.iam_count += 1
                    self._reply(self._iam_npdu(), src)
            elif apdu and apdu[0] == 0x00:              # Confirmed-Request
                # Verrijken (naam/model) hoeft hier niet te werken: een reject is
                # een geldig, definitief antwoord en houdt de test snel.
                self._reply(bytes([0x01, 0x00, 0x60, apdu[2], 0x09]), src)

    def stop(self) -> None:
        self._stop.set()
        self.join(timeout=2.0)
        try:
            self.sock.close()
        except OSError:
            pass


def client(port: int) -> bacnet.BacnetClient:
    """Client op 127.0.0.1 (zie de toelichting boven: geen LAN-invloed)."""
    return bacnet.BacnetClient(bind_ip="127.0.0.1", port=port, timeout=1.0, delay=0.0)


def by_device(found: list[dict], device: int = DEVICE) -> list[dict]:
    return [d for d in found if d["device"] == device]


def with_device(ip: str, **kwargs) -> FakeDevice:
    dev = FakeDevice(ip, **kwargs)
    dev.start()
    return dev


# --------------------------------------------------------------------- scenario's
def test_npdu_offsets() -> None:
    """De offsetlogica zelf: geen sockets, wel dezelfde helper als _recv."""
    apdu = i_am()
    assert bacnet._npdu_apdu_offset(bytes([0x01, 0x00]) + apdu) == 2, "gewone NPDU"
    assert bacnet._npdu_apdu_offset(bytes([0x01, 0x20, 0x00, 0x00, 0x00, 0xFF]) + apdu) == 6, \
        "DNET-kop niet overgeslagen"
    assert bacnet._npdu_apdu_offset(bytes([0x01, 0x08, 0x00, 0x05, 0x02, 0xAA, 0xBB, 0xFF]) + apdu) == 8, \
        "SNET-kop niet overgeslagen"
    both = bytes([0x01, 0x28, 0x00, 0x00, 0x00, 0xFF, 0x00, 0x05, 0x00, 0xFF]) + apdu
    assert bacnet._npdu_apdu_offset(both) == 10, "DNET+SNET niet beide overgeslagen"
    assert bacnet._npdu_apdu_offset(bytes([0x01, 0x80]) + apdu) is None, \
        "netwerklaag-bericht moet genegeerd worden"
    assert bacnet._npdu_apdu_offset(bytes([0x01, 0x20, 0x00])) is None, \
        "afgekapte NPDU moet genegeerd worden"


def test_retry_second_round() -> None:
    """Een toestel dat pas op de tweede Who-Is antwoordt, moet gevonden worden."""
    dev = with_device("127.0.0.1", answer_after=2)
    c = client(47930)
    try:
        found = c.whois(timeout=1.5, subnets=[], unicast=["127.0.0.1"], port=TEST_PORT)
    finally:
        c.close()
        dev.stop()
    hits = by_device(found)
    assert dev.whois_count >= 2, f"Who-Is maar {dev.whois_count}× verstuurd"
    assert len(hits) == 1, f"device 4242 niet gevonden: {found}"
    assert hits[0]["ip"] == "127.0.0.1", hits[0]


def test_dedupe_same_instance_two_ips() -> None:
    """Twee toestellen met instance 4242 op verschillend IP = twee entries."""
    one = with_device("127.0.0.1")
    two = with_device("127.0.0.2")
    c = client(47931)
    try:
        found = c.whois(timeout=1.2, subnets=[], unicast=["127.0.0.1", "127.0.0.2"],
                        port=TEST_PORT)
    finally:
        c.close()
        one.stop()
        two.stop()
    hits = by_device(found)
    assert len(hits) == 2, f"verwacht 2 entries voor device 4242, kreeg {hits}"
    assert {d["ip"] for d in hits} == {"127.0.0.1", "127.0.0.2"}, hits


def test_dedupe_repeated_answer() -> None:
    """Herhaald antwoorden van hetzelfde (ip, device) geeft één entry."""
    dev = with_device("127.0.0.1", answer_after=1)
    c = client(47932)
    try:
        found = c.whois(timeout=1.2, subnets=[], unicast=["127.0.0.1"], port=TEST_PORT)
    finally:
        c.close()
        dev.stop()
    assert dev.iam_count >= 2, f"fake antwoordde maar {dev.iam_count}× — dedupe niet getest"
    hits = by_device(found)
    assert len(hits) == 1, f"dubbele entry voor hetzelfde (ip, device): {hits}"


def test_npdu_dnet_header_parsed() -> None:
    """I-Am met control 0x20 (DNET-kop) moet ontleed worden, niet gedropt."""
    dev = with_device("127.0.0.1", control=0x20)
    c = client(47933)
    try:
        found = c.whois(timeout=1.0, subnets=[], unicast=["127.0.0.1"], port=TEST_PORT)
    finally:
        c.close()
        dev.stop()
    hits = by_device(found)
    assert len(hits) == 1, f"I-Am met DNET-kop niet gevonden: {found}"
    assert hits[0]["vendor"] == VENDOR, hits[0]


def test_npdu_network_layer_message_ignored() -> None:
    """Control 0x80 is een netwerklaag-bericht: de bytes erachter zijn geen APDU."""
    dev = with_device("127.0.0.1", control=0x80)
    c = client(47934)
    try:
        found = c.whois(timeout=1.0, subnets=[], unicast=["127.0.0.1"], port=TEST_PORT)
    finally:
        c.close()
        dev.stop()
    assert dev.iam_count >= 1, "fake heeft niet geantwoord — scenario niet getest"
    assert not by_device(found), f"netwerklaag-bericht als I-Am gelezen: {found}"


def test_no_reply_returns_empty_list() -> None:
    """Zonder antwoord: geen exception, een lege lijst, en het venster blijft timeout.

    Hermetisch: de Who-Is gaat naar een dode poort (DEAD_PORT) waarop alleen het
    zwijgende fake-toestel luistert. De broadcast komt dus niet op 47808 terecht
    en een testslave, simulator of BBMD op de testbank kan niet antwoorden. De
    assertie op een lege lijst is daarom onvoorwaardelijk — geen escape hatch.
    """
    dev = with_device("127.0.0.1", answer_after=10 ** 6, port=DEAD_PORT)   # zwijgt op Who-Is
    c = client(47935)
    t0 = time.time()
    try:
        found = c.whois(timeout=3.0, subnets=[], unicast=["127.0.0.1"], port=DEAD_PORT)
    finally:
        elapsed = time.time() - t0
        c.close()
        dev.stop()
    assert dev.whois_count >= 2, f"Who-Is niet herhaald: {dev.whois_count}×"
    assert isinstance(found, list), f"whois gaf geen lijst: {found!r}"
    assert found == [], f"zonder antwoord toch entries: {found}"
    assert elapsed <= 3.0 + 1.0, f"scantijd {elapsed:.2f}s > timeout + 1 s"


print("BACnet Who-Is zelftest")
check("NPDU-offsets", test_npdu_offsets)
check("Who-Is herhaald tot tweede ronde", test_retry_second_round)
check("Dedupe: zelfde instance op twee IP's", test_dedupe_same_instance_two_ips)
check("Dedupe: herhaald antwoord", test_dedupe_repeated_answer)
check("NPDU met DNET-kop ontleed", test_npdu_dnet_header_parsed)
check("Netwerklaag-bericht (0x80) genegeerd", test_npdu_network_layer_message_ignored)
check("Geen antwoord geeft lege lijst", test_no_reply_returns_empty_list)

if FAILED:
    print(f"MISLUKT: {', '.join(FAILED)}")
    sys.exit(1)
if SKIPPED:
    # Alle scenario's hier bewijzen een acceptatiecriterium; een skip is geen bewijs.
    print(f"MISLUKT: overgeslagen scenario's: {', '.join(SKIPPED)}")
    sys.exit(1)
print("geslaagd")
