# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
"""Gesimuleerde MS/TP-master, om FlexPoll's MS/TP-laag te testen zonder hardware.

Dit is géén BACnet-stack: het is een peer die precies genoeg doet om de
token-cyclus, de CRCs en de APDU-uitwisseling te bewijzen. Hij antwoordt op
Poll-For-Master, geeft de token door, antwoordt op Who-Is met een I-Am en op
ReadProperty met een complex-ack.

Draait over een pty (zie tests/mstp_selftest.py) of over een echte poort.
"""

from __future__ import annotations

import os
import struct
import time

import mstp
from bacnet import _read_tag

MAC = 5
DEVICE = 1234
VENDOR = 42
NAME = "Testcontroller MS/TP"


def _app_uint(value: int) -> bytes:
    if value < 0x100:
        return b"\x21" + bytes([value])
    if value < 0x10000:
        return b"\x22" + struct.pack(">H", value)
    return b"\x24" + struct.pack(">I", value & 0xFFFFFFFF)


def _app_real(value: float) -> bytes:
    return b"\x44" + struct.pack(">f", value)


def _app_str(text: str) -> bytes:
    raw = text.encode("utf-8")
    return bytes([0x75, len(raw)]) + raw


def _oid(obj_type: int, inst: int) -> bytes:
    return b"\xc4" + struct.pack(">I", ((obj_type & 0x3FF) << 22) | (inst & 0x3FFFFF))


class MstpPeer:
    def __init__(self, fd: int, mac: int = MAC, device: int = DEVICE):
        self.fd = fd
        self.mac = mac
        self.device = device
        self.buf = b""
        self.running = True
        self.last_token = 0.0
        self.sent_token_at = 0.0
        self.values = {(0, 0): 21.5, (0, 1): 55.0}
        self.objects = [(0, 0), (0, 1)]
        self.reads = 0

    # ---------------------------------------------------------------- transport
    def _read(self) -> list[mstp.Frame]:
        try:
            chunk = os.read(self.fd, 4096)
        except (BlockingIOError, OSError):
            chunk = b""
        if chunk:
            self.buf += chunk
        frames, self.buf = mstp.decode_frames(self.buf)
        return frames

    def _write(self, frame: bytes) -> None:
        os.write(self.fd, frame)

    def _send_token(self, dst: int = 0) -> None:
        self._write(mstp.encode_frame(mstp.TOKEN, dst, self.mac))
        self.sent_token_at = time.time()

    # ---------------------------------------------------------------- APDU
    def _npdu(self, apdu: bytes) -> bytes:
        return bytes([0x01, 0x00]) + apdu

    def _i_am(self) -> bytes:
        oid = ((8 & 0x3FF) << 22) | (self.device & 0x3FFFFF)
        apdu = b"\x10\x00" + b"\xc4" + struct.pack(">I", oid)
        apdu += _app_uint(1476) + _app_uint(0) + _app_uint(VENDOR)
        return self._npdu(apdu)

    def _complex_ack(self, inv: int, service: int, payload: bytes) -> bytes:
        return self._npdu(bytes([0x30, inv & 0xFF, service]) + payload)

    def _read_property(self, inv: int, body: bytes) -> bytes:
        """body = ctx0(objid) ctx1(prop) [ctx2(index)] — genoeg voor de test."""
        i = 0
        oid = 0
        prop = None
        index = None
        while i < len(body):
            tag, cls, ln, i = _read_tag(body, i)
            data = body[i:i + ln]
            i += ln
            if tag == 0 and cls == 1:
                oid = int.from_bytes(data, "big")
            elif tag == 1 and cls == 1:
                prop = int.from_bytes(data, "big")
            elif tag == 2 and cls == 1:
                index = int.from_bytes(data, "big")
        obj_type, inst = oid >> 22, oid & 0x3FFFFF
        self.reads += 1
        if obj_type == 8 and inst == self.device:
            if prop == 77:                              # object-name
                return self._complex_ack(inv, 0x0C, b"\x3e" + _app_str(NAME) + b"\x3f")
            if prop == 76:                              # object-list
                if index is not None:
                    if index == 0:
                        return self._complex_ack(inv, 0x0C,
                                                 b"\x3e" + _app_uint(len(self.objects)) + b"\x3f")
                    if 1 <= index <= len(self.objects):
                        t, n = self.objects[index - 1]
                        return self._complex_ack(inv, 0x0C, b"\x3e" + _oid(t, n) + b"\x3f")
                payload = b"\x3e" + b"".join(_oid(t, n) for t, n in self.objects) + b"\x3f"
                return self._complex_ack(inv, 0x0C, payload)
        if obj_type == 0:
            if prop == 85 and (inst == 0 or inst == 1):  # present-value
                return self._complex_ack(inv, 0x0C,
                                         b"\x3e" + _app_real(self.values[(0, inst)]) + b"\x3f")
            if prop == 77:
                return self._complex_ack(inv, 0x0C,
                                         b"\x3e" + _app_str(f"AI-{inst}") + b"\x3f")
        # Onbekend: error-PDU (class 2 = property, code 32 = unknown-property)
        return self._npdu(bytes([0x50, inv & 0xFF, 0x0C, 0x02, 0x20]))

    def handle(self, frame: mstp.Frame) -> None:
        if frame.type == mstp.POLL_FOR_MASTER and frame.dst == self.mac:
            self._write(mstp.encode_frame(mstp.REPLY_TO_POLL_FOR_MASTER, frame.src, self.mac))
            return
        if frame.type == mstp.TOKEN and frame.dst == self.mac:
            self.last_token = time.time()
            self._send_token(0)                         # niets te zenden: meteen door
            return
        if frame.type in (mstp.DATA_EXPECTING_REPLY, mstp.DATA_NOT_EXPECTING_REPLY):
            if frame.dst not in (self.mac, mstp.BROADCAST):
                return
            npdu = frame.data
            if len(npdu) < 3 or npdu[0] != 0x01:
                return
            apdu = npdu[2:]
            if not apdu:
                return
            if apdu[0] == 0x10 and apdu[1] == 0x08:     # Who-Is
                self._write(mstp.encode_frame(mstp.DATA_NOT_EXPECTING_REPLY,
                                              mstp.BROADCAST, self.mac, self._i_am()))
                return
            if apdu[0] & 0xF0 == 0x00 and len(apdu) >= 4:   # confirmed request
                inv, service = apdu[2], apdu[3]
                if service == 0x0C:
                    reply = self._read_property(inv, apdu[4:])
                    self._write(mstp.encode_frame(mstp.DATA_EXPECTING_REPLY,
                                                  frame.src, self.mac, reply))
                elif service == 0x0F:
                    self._write(mstp.encode_frame(mstp.DATA_EXPECTING_REPLY,
                                                  frame.src, self.mac,
                                                  self._npdu(bytes([0x20, inv & 0xFF, service]))))
            return

    def run(self, seconds: float = 10.0) -> None:
        end = time.time() + seconds
        while self.running and time.time() < end:
            for frame in self._read():
                self.handle(frame)
            # Tokencirculatie op gang houden zolang de master niets vraagt.
            if time.time() - self.sent_token_at > 0.1:
                self._send_token(0)
            time.sleep(0.005)
