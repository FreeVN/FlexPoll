# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
"""Modbus TCP/IP testslave — stdlib only.

Een klein maar volledig genoeg slave voor de FlexPoll-testbank:
coils, discrete inputs, holding- en input-registers, met een paar
realistische waarden (int16, uint16, float32) om schaling te testen.

Poort 5020 (geen root nodig), unit 1. Elke schrijfactie wordt gelogd,
zodat je in `journalctl -u modbus-tcpslave -f` ziet wat de master doet.
"""

from __future__ import annotations

import socket
import struct
import sys
import threading
import time

HOST = "0.0.0.0"
PORT = 5020
UNIT = 1

LOCK = threading.Lock()

COILS = [1, 0, 1, 0, 0, 0, 1, 1, 0, 0] + [0] * 54            # 0x0000-0x003F
DISCRETE = [1, 1, 0, 0, 1, 0, 0, 1] + [0] * 56                # 1x0000-1x003F

HOLDING = [0] * 128                                            # 4x0000-4x007F
INPUT = [0] * 128                                              # 3x0000-3x007F


def _f32(value: float) -> tuple[int, int]:
    hi, lo = struct.unpack(">HH", struct.pack(">f", value))
    return hi, lo


def reset() -> None:
    HOLDING[:] = [0] * 128
    INPUT[:] = [0] * 128
    # 4x0000: s16 215  → 21,5 °C bij schaal 0,1
    HOLDING[0] = 215 & 0xFFFF
    # 4x0001: u16 65000 (grote teller)
    HOLDING[1] = 65000
    # 4x0002-0003: float32 45,5 (AB-orde)
    HOLDING[2], HOLDING[3] = _f32(45.5)
    # 4x0004: bereik / status
    HOLDING[4] = 1
    # 4x0008: bedrijfsmodus (1 koelen, 2 verwarmen, 3 auto)
    HOLDING[8] = 2
    # 4x0010: setpunt ×10 = 215 → 21,5 °C
    HOLDING[16] = 215
    # 4x0011-0012: float32 12,0
    HOLDING[17], HOLDING[18] = _f32(12.0)

    INPUT[0] = 215          # 3x0000 temperatuur ×0,1
    INPUT[1] = 438          # 3x0001 vochtigheid ×0,1 = 43,8 %
    INPUT[2], INPUT[3] = _f32(3.42)   # 3x0002 debiet
    INPUT[4] = 1            # 3x0004 running
    INPUT[5] = 0            # 3x0005 alarm


reset()


def _exc(fc: int, code: int) -> bytes:
    return bytes([fc | 0x80, code])


def _read_bits(fc: int, start: int, qty: int) -> bytes:
    src = COILS if fc == 1 else DISCRETE
    if qty < 1 or qty > 2000:
        return _exc(fc, 3)
    if start + qty > len(src):
        return _exc(fc, 2)
    bits = src[start:start + qty]
    out = bytearray((qty + 7) // 8)
    for i, b in enumerate(bits):
        if b:
            out[i // 8] |= 1 << (i % 8)
    return bytes([fc, len(out)]) + bytes(out)


def _read_regs(fc: int, start: int, qty: int) -> bytes:
    src = HOLDING if fc == 3 else INPUT
    if qty < 1 or qty > 125:
        return _exc(fc, 3)
    if start + qty > len(src):
        return _exc(fc, 2)
    vals = src[start:start + qty]
    return bytes([fc, qty * 2]) + b"".join(struct.pack(">H", v & 0xFFFF) for v in vals)


def _write_bits(fc: int, start: int, values: list[int]) -> bytes:
    if start + len(values) > len(COILS):
        return _exc(fc, 2)
    for i, v in enumerate(values):
        COILS[start + i] = 1 if v else 0
    return bytes([fc]) + struct.pack(">HH", start, len(values))


def _write_regs(fc: int, start: int, values: list[int]) -> bytes:
    if start + len(values) > len(HOLDING):
        return _exc(fc, 2)
    for i, v in enumerate(values):
        HOLDING[start + i] = v & 0xFFFF
    return bytes([fc]) + struct.pack(">HH", start, len(values))


def handle_pdu(pdu: bytes) -> bytes:
    if not pdu:
        return _exc(0, 3)
    fc = pdu[0]
    if fc in (1, 2):
        if len(pdu) < 5:
            return _exc(fc, 3)
        start, qty = struct.unpack(">HH", pdu[1:5])
        return _read_bits(fc, start, qty)
    if fc in (3, 4):
        if len(pdu) < 5:
            return _exc(fc, 3)
        start, qty = struct.unpack(">HH", pdu[1:5])
        return _read_regs(fc, start, qty)
    if fc == 5:
        if len(pdu) < 5:
            return _exc(fc, 3)
        addr, value = struct.unpack(">HH", pdu[1:5])
        if value not in (0x0000, 0xFF00):
            return _exc(fc, 3)
        if addr >= len(COILS):
            return _exc(fc, 2)
        COILS[addr] = 1 if value else 0
        print(f"FC5  coil {addr} → {COILS[addr]}", flush=True)
        return pdu[:5]
    if fc == 6:
        if len(pdu) < 5:
            return _exc(fc, 3)
        addr, value = struct.unpack(">HH", pdu[1:5])
        if addr >= len(HOLDING):
            return _exc(fc, 2)
        HOLDING[addr] = value
        print(f"FC6  4x{addr:04d} → {value}", flush=True)
        return pdu[:5]
    if fc == 15:
        if len(pdu) < 6:
            return _exc(fc, 3)
        start, qty, _bc = struct.unpack(">HHB", pdu[1:6])
        raw = pdu[6:]
        values = [(raw[i // 8] >> (i % 8)) & 1 for i in range(qty)]
        print(f"FC15 coils {start}..{start + qty - 1} → {values}", flush=True)
        return _write_bits(fc, start, values)
    if fc == 16:
        if len(pdu) < 6:
            return _exc(fc, 3)
        start, qty, _bc = struct.unpack(">HHB", pdu[1:6])
        raw = pdu[6:]
        values = [struct.unpack(">H", raw[i * 2:i * 2 + 2])[0] for i in range(min(qty, len(raw) // 2))]
        print(f"FC16 4x{start:04d}..4x{start + qty - 1:04d} → {values}", flush=True)
        return _write_regs(fc, start, values)
    return _exc(fc, 1)


def serve(conn: socket.socket, peer) -> None:
    conn.settimeout(60)
    try:
        while True:
            head = conn.recv(7)
            if not head:
                return
            if len(head) < 7:
                return
            tid, pid_, length, unit = struct.unpack(">HHHB", head)
            body = b""
            while len(body) < length - 1:
                chunk = conn.recv(length - 1 - len(body))
                if not chunk:
                    return
                body += chunk
            if pid_ != 0:
                return
            with LOCK:
                resp = handle_pdu(body)
            conn.sendall(struct.pack(">HHHB", tid, 0, len(resp) + 1, unit) + resp)
    except (socket.timeout, ConnectionResetError, BrokenPipeError):
        pass
    finally:
        conn.close()


def main() -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(16)
    print(f"Modbus TCP testslave op {HOST}:{PORT} · unit {UNIT} · "
          f"{len(COILS)} coils, {len(DISCRETE)} DI, {len(HOLDING)} HR, {len(INPUT)} IR", flush=True)
    try:
        while True:
            conn, peer = srv.accept()
            threading.Thread(target=serve, args=(conn, peer), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()


if __name__ == "__main__":
    sys.exit(main())
