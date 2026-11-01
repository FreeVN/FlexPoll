# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
"""BACnet MS/TP (ANSI/ASHRAE 135, clause 9) — master, enkel stdlib + pyserial.

Waarom een eigen implementatie en geen library: FlexPoll heeft geen
 dependencies buiten pyserial, en MS/TP is goed te overzien: een frame met twee
CRCs, een token-state-machine en dezelfde APDU's die we al voor BACnet/IP
gebruiken.

    WAARSCHUWING — NOG NIET IN HET VELD GETEST.
    Er is geen MS/TP-toestel in deze omgeving. Wat wél getest is: de CRCs tegen
    de gepubliceerde check-waarden, het frame-formaat tegen de voorbeelden uit de
    specificatie, en de token-cyclus tegen een gesimuleerde peer
    (tests/mstp_peer.py). De timing-constanten zijn die van de standaard, maar
    hoe een echt toestel erop reageert is onbewezen. Zeg het in de UI, niet
    alleen in de code.

CRC's (gecontroleerd, zie tests):
  header: CRC-8, poly 0x81 (x^8+x^7+1), init 0xFF, reflected, xorout 0xFF.
          Berekend over type+dst+src+len — NIET over de preamble.
          check("123456789") == 0x89
  data:   CRC-16/X.25, poly 0x8408, init 0xFFFF, reflected, xorout 0xFFFF,
          least-significant byte eerst. check("123456789") == 0x906E
"""

from __future__ import annotations

import struct
import time
from collections import deque

from bacnet import (MAX_APDU_RESP, MAX_SEGS, OBJ_ABBR, OBJ_TYPES, PROP_OBJECT_LIST,
                    PROP_OBJECT_NAME, BacnetError, BacnetServerError, _ctx,
                    _obj_id, _uint_bytes, describe_apdu_error, parse_ack)

BAUD_CHOICES = (9600, 19200, 38400, 57600, 76800)

# Frame-types (Annex: 0..7)
TOKEN = 0
POLL_FOR_MASTER = 1
REPLY_TO_POLL_FOR_MASTER = 2
TEST_REQUEST = 3
TEST_RESPONSE = 4
DATA_EXPECTING_REPLY = 5
DATA_NOT_EXPECTING_REPLY = 6
REPLY_POSTPONED = 7

BROADCAST = 0xFF
MAX_MAC = 127

# Timing (ms), zoals in de standaard. Bij 76800 schaalt de spec sommige waarden
# mee; we houden de veilige bovengrens aan — te langzaam is hinderlijk, te snel
# is onbetrouwbaar.
T_NO_TOKEN = 500
T_REPLY_TIMEOUT = 255
T_USAGE_TIMEOUT = 100
T_FRAME_ABORT = 60           # bit-tijden; wij wachten gewoon op de UART
TURNAROUND = 0.02            # seconde tussen twee zendingen (Tturnaround)

# Hoeveel frames we per token mogen sturen. Eén is genoeg voor een testbank en
# houdt de lus voorspelbaar.
N_MAX_INFO_FRAMES = 1


class MstpError(Exception):
    """Framing-, token- of transportfout op de MS/TP-lijn."""


# --------------------------------------------------------------------------- CRCs
def crc8_header(data: bytes) -> int:
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x81 if crc & 1 else crc >> 1
    return crc ^ 0xFF


def crc16_data(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


# --------------------------------------------------------------------------- frames
def encode_frame(ftype: int, dst: int, src: int, data: bytes = b"") -> bytes:
    head = bytes([ftype & 0xFF, dst & 0xFF, src & 0xFF,
                  (len(data) >> 8) & 0xFF, len(data) & 0xFF])
    frame = b"\x55\xff" + head + bytes([crc8_header(head)])
    if data:
        crc = crc16_data(data)
        # CRC laag-byte eerst: zo schrijft de standaard het voor.
        frame += data + bytes([crc & 0xFF, (crc >> 8) & 0xFF])
    return frame


class Frame:
    __slots__ = ("type", "dst", "src", "data", "raw")

    def __init__(self, ftype: int, dst: int, src: int, data: bytes, raw: bytes):
        self.type, self.dst, self.src, self.data, self.raw = ftype, dst, src, data, raw

    def __repr__(self) -> str:  # pragma: no cover - enkel voor logs
        return f"Frame(type={self.type}, {self.src}->{self.dst}, {len(self.data)}B)"


def decode_frames(buf: bytes) -> tuple[list[Frame], bytes]:
    """Haal alle volledige frames uit een buffer; geef (frames, rest) terug."""
    out: list[Frame] = []
    i = 0
    n = len(buf)
    while True:
        start = buf.find(b"\x55\xff", i)
        if start < 0 or n - start < 8:
            return out, buf[i if start < 0 else start:]
        if n - start < 8:
            return out, buf[start:]
        head = buf[start + 2:start + 7]
        ftype, dst, src, hi, lo = head
        length = (hi << 8) | lo
        if length > 501:
            i = start + 2                       # onzin: schuif één byte op
            continue
        total = 7 + 1 + length + (2 if length else 0)
        if n - start < total:
            return out, buf[start:]
        if crc8_header(head) != buf[start + 7]:
            i = start + 2                       # header-CRC fout: overslaan
            continue
        data = buf[start + 8:start + 8 + length]
        if length:
            crc = crc16_data(data)
            got = buf[start + 8 + length] | (buf[start + 9 + length] << 8)
            if crc != got:
                i = start + 2
                continue
        out.append(Frame(ftype, dst, src, data, buf[start:start + total]))
        i = start + total


# --------------------------------------------------------------------------- master
class MstpMaster:
    """Eén master op de lijn. Kan samenwerken met andere masters (token) of
    alleen staan (sole master), wat op een testbank het normale geval is."""

    def __init__(self, port: str, mac: int = 0, baud: int = 19200,
                 master_timeout: float = 2.0, device_instance: int = 0):
        self.port_name = port
        self.mac = max(0, min(MAX_MAC, int(mac)))
        self.baud = int(baud)
        self.timeout = float(master_timeout)
        self.device_instance = int(device_instance)
        self.ser = None
        self.buf = b""
        self.inv = 0
        self.queue: deque[bytes] = deque()        # frames die wachten op een token
        self.token_held = False
        self.last_token = 0.0
        self.masters: list[int] = []               # bekende master-MAC's
        self.successor: int | None = None
        self.sole = False
        self.reply: Frame | None = None
        self.received: list[Frame] = []
        self.last_error: str | None = None
        self.stats = {"tx": 0, "rx": 0, "token": 0, "crc": 0, "pfm": 0}

    # ---------------------------------------------------------------- transport
    def open(self) -> None:
        import serial                                  # noqa: PLC0415

        if self.ser is not None and getattr(self.ser, "is_open", False):
            return
        self.ser = serial.Serial(self.port_name, baudrate=self.baud, bytesize=8,
                                 parity="N", stopbits=1, timeout=0.05,
                                 write_timeout=1.0, exclusive=True)
        self.buf = b""
        self.last_token = time.time()
        self.sole = False

    def close(self) -> None:
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:                          # noqa: BLE001
                pass
            self.ser = None

    def is_open(self) -> bool:
        return bool(self.ser is not None and getattr(self.ser, "is_open", False))

    def _write(self, frame: bytes) -> None:
        if not self.is_open():
            raise MstpError("poort niet open")
        self.ser.write(frame)
        self.ser.flush()
        self.stats["tx"] += 1
        time.sleep(TURNAROUND)

    def _pump_serial(self) -> list[Frame]:
        if not self.is_open():
            raise MstpError("poort niet open")
        chunk = self.ser.read(512)
        if chunk:
            self.buf += chunk
        frames, self.buf = decode_frames(self.buf)
        self.stats["rx"] += len(frames)
        return frames

    # ---------------------------------------------------------------- token
    def _send_token(self, dst: int) -> None:
        self._write(encode_frame(TOKEN, dst, self.mac))
        self.token_held = False
        self.last_token = time.time()
        self.stats["token"] += 1

    def _next_successor(self) -> int:
        """Volgende master na ons MAC-nummer; zonder bekende masters: onszelf."""
        if not self.masters:
            return self.mac
        for mac in sorted(self.masters):
            if mac > self.mac:
                return mac
        return min(self.masters)

    def _handle(self, frame: Frame) -> None:
        """Eén frame verwerken. Antwoorden die bij ons horen blijven in self.reply."""
        if frame.type == TOKEN:
            if frame.dst == self.mac:
                self.token_held = True
                self.last_token = time.time()
                self.stats["token"] += 1
                if frame.src != self.mac and frame.src not in self.masters and frame.src <= MAX_MAC:
                    self.masters.append(frame.src)
            return
        if frame.type == POLL_FOR_MASTER:
            if frame.dst == self.mac:
                self.stats["pfm"] += 1
                self._write(encode_frame(REPLY_TO_POLL_FOR_MASTER, frame.src, self.mac))
                if frame.src not in self.masters and frame.src <= MAX_MAC:
                    self.masters.append(frame.src)
            return
        if frame.type == REPLY_TO_POLL_FOR_MASTER:
            if frame.src not in self.masters and frame.src <= MAX_MAC:
                self.masters.append(frame.src)
            return
        if frame.type in (DATA_EXPECTING_REPLY, DATA_NOT_EXPECTING_REPLY):
            if frame.dst in (self.mac, BROADCAST):
                self.reply = frame
            return
        # TestRequest/Response en ReplyPostponed laten we ongemoeid; een
        # testverzoek beantwoorden we wel zodat een andere master ons ziet.
        if frame.type == TEST_REQUEST and frame.dst == self.mac:
            self._write(encode_frame(TEST_RESPONSE, frame.src, self.mac, frame.data))

    def _discover(self, timeout: float = 0.6) -> None:
        """Poll voor meesters tot iemand antwoordt; anders zijn we alleen."""
        end = time.time() + timeout
        candidate = (self.mac + 1) % 128
        while time.time() < end:
            self._write(encode_frame(POLL_FOR_MASTER, candidate, self.mac))
            t_end = time.time() + 0.05
            while time.time() < t_end:
                for frame in self._pump_serial():
                    self._handle(frame)
            if candidate in self.masters:
                self.successor = candidate
                return
            candidate = (candidate + 1) % 128
            if candidate == self.mac:
                break
        self.sole = True
        self.successor = self.mac

    def service(self, seconds: float) -> None:
        """Bus een tijdje bedienen: tokens doorgeven, PFM beantwoorden, zenden."""
        if not self.is_open():
            self.open()
        if not self.masters and not self.sole and self.queue:
            self._discover()
        end = time.time() + seconds
        while time.time() < end:
            for frame in self._pump_serial():
                self._handle(frame)
            if self.queue and (self.token_held or self.sole):
                self._transmit_queued()
            # Token te lang stil? Dan is de lijn (of de andere master) weg.
            if self.token_held and time.time() - self.last_token > 0.2:
                self._send_token(self.successor or self.mac)

    def _transmit_queued(self) -> None:
        sent = 0
        while self.queue and sent < N_MAX_INFO_FRAMES:
            self._write(self.queue.popleft())
            sent += 1
        if self.token_held:
            self._send_token(self._next_successor())

    # ---------------------------------------------------------------- APDU
    def _npdu(self, apdu: bytes, expecting_reply: bool) -> bytes:
        # Geen routing: versie 1, control 0x04 (verwacht antwoord) of 0x00.
        return bytes([0x01, 0x04 if expecting_reply else 0x00]) + apdu

    def _transact(self, dst: int, apdu: bytes, expecting_reply: bool,
                  timeout: float | None = None) -> bytes:
        ftype = DATA_EXPECTING_REPLY if expecting_reply else DATA_NOT_EXPECTING_REPLY
        self.reply = None
        self.queue.append(encode_frame(ftype, dst, self.mac, self._npdu(apdu, expecting_reply)))
        end = time.time() + (timeout or self.timeout)
        if not expecting_reply:
            # Broadcast (Who-Is): wachten tot het frame de deur uit is, niet op
            # een antwoord — dat komt later als I-Am en wordt apart opgevangen.
            while self.queue and time.time() < end:
                self.service(0.05)
            if self.queue:
                raise MstpError("kon niet verzenden — geen token van een andere master")
            return b""
        while time.time() < end:
            self.service(0.05)
            if self.reply is not None and self.reply.data[:1] == b"\x01":
                npdu = self.reply.data
                if len(npdu) < 3:
                    continue
                return npdu[2:]                     # APDU (zonder NPDU-kop)
        raise MstpError("timeout — geen antwoord op MS/TP")

    def _confirmed(self, dst: int, service: int, body: bytes,
                   timeout: float | None = None, what: str = "") -> bytes:
        last: Exception | None = None
        for _ in range(2):
            self.inv = (self.inv % 127) + 1
            inv = self.inv
            apdu = bytes([0x00, MAX_SEGS | MAX_APDU_RESP, inv, service]) + body
            try:
                rest = self._transact(dst, apdu, True, timeout)
            except MstpError as exc:
                last = exc
                continue
            pdu_type = rest[0] & 0xF0
            if pdu_type == 0x30:
                return rest[3:]
            if pdu_type == 0x20:
                return b""
            if pdu_type in (0x50, 0x60, 0x70):
                raise BacnetServerError(describe_apdu_error(rest, what))
        raise last or MstpError("geen antwoord")

    # ---------------------------------------------------------------- diensten
    def whois(self, timeout: float = 3.0) -> list[dict]:
        apdu = b"\x10\x08"
        self._transact(BROADCAST, apdu, False, self.timeout)
        found: dict[int, dict] = {}
        end = time.time() + timeout
        while time.time() < end:
            self.service(0.1)
            if self.reply is None:
                continue
            npdu = self.reply.data
            frame_mac = self.reply.src
            self.reply = None
            if len(npdu) < 3 or npdu[0] != 0x01:
                continue
            apdu = npdu[2:]
            if not apdu or apdu[0] != 0x10 or len(apdu) < 10 or apdu[1] != 0x00:
                continue
            oid = int.from_bytes(apdu[3:7], "big") if len(apdu) > 6 else 0
            dev = oid & 0x3FFFFF
            if not dev or dev in found:
                continue
            entry = {"device": dev, "mac": frame_mac, "vendor": 0,
                     "name": "", "model": ""}
            found[dev] = entry
            try:
                entry["name"] = self.read_property(frame_mac, 8, dev, PROP_OBJECT_NAME, timeout=0.8)
            except (BacnetError, MstpError):
                pass
        return sorted(found.values(), key=lambda d: d["device"])

    def read_property(self, mac: int, obj_type: int, instance: int, prop: int,
                      index: int | None = None, timeout: float | None = None):
        body = _ctx(0, _obj_id(obj_type, instance)) + _ctx(1, _uint_bytes(prop))
        if index is not None:
            body += _ctx(2, _uint_bytes(index))
        what = f"lezen {OBJ_ABBR.get(obj_type, obj_type)} {instance} · property {prop}"
        rest = self._confirmed(mac, 0x0C, body, timeout, what=what)
        return parse_ack(rest)

    def write_property(self, mac: int, obj_type: int, instance: int, prop: int, value) -> None:
        from bacnet import _app_bool, _app_enum, _app_real, _app_str, _app_uint

        if isinstance(value, bool):
            enc = _app_bool(value)
        elif isinstance(value, float):
            enc = _app_real(value)
        elif isinstance(value, int):
            enc = _app_enum(value) if obj_type in (3, 4, 5, 13, 14, 19) else _app_uint(value)
        elif isinstance(value, str):
            enc = _app_str(value)
        else:
            raise BacnetError("ongeldige waarde")
        body = _ctx(0, _obj_id(obj_type, instance)) + _ctx(1, _uint_bytes(prop)) + b"\x3e" + enc + b"\x3f"
        self._confirmed(mac, 0x0F, body, timeout=max(self.timeout, 3.0))

    def object_list(self, mac: int, device: int, count: int | None = None) -> list[int]:
        try:
            whole = self.read_property(mac, 8, device, PROP_OBJECT_LIST, None)
            items = whole if isinstance(whole, list) else [whole]
            oids = []
            for item in items:
                if isinstance(item, tuple) and len(item) == 2:
                    item = item[1]
                if isinstance(item, (bytes, bytearray)) and len(item) == 4:
                    item = int.from_bytes(item, "big")
                if isinstance(item, int):
                    oids.append(item)
            if oids:
                return oids[:count] if count else oids
        except (BacnetError, MstpError):
            pass
        out = []
        for i in range(1, min(count or 200, 400) + 1):
            try:
                oid = self.read_property(mac, 8, device, PROP_OBJECT_LIST, i)
            except (BacnetError, MstpError):
                break
            if isinstance(oid, tuple) and len(oid) == 2:
                oid = oid[1]
            if isinstance(oid, (bytes, bytearray)) and len(oid) == 4:
                oid = int.from_bytes(oid, "big")
            if isinstance(oid, int):
                out.append(oid)
        return out

    def objects(self, mac: int, device: int) -> list[dict]:
        count = self.read_property(mac, 8, device, PROP_OBJECT_LIST, 0)
        if not isinstance(count, int):
            raise BacnetError("object-list niet leesbaar")
        out = []
        for oid in self.object_list(mac, device, count):
            otype, inst = oid >> 22, oid & 0x3FFFFF
            out.append({"type": otype, "inst": inst,
                        "name": OBJ_TYPES.get(otype, f"type-{otype}"),
                        "abbr": OBJ_ABBR.get(otype, str(otype))})
        return out
