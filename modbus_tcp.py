"""Minimale Modbus TCP-master (MBAP) met dezelfde interface als modbus_rtu.Bus.

Alleen wat de testbank nodig heeft: FC1/2/3/4/5/6/16, één verbinding per
eindpunt, geen reconnect-magie (dat doet de app).
"""

from __future__ import annotations

import socket
import struct
import time

from modbus_rtu import ModbusError, ModbusException, ModbusTimeout

FC_READ_COILS = 0x01
FC_READ_DI = 0x02
FC_READ_HR = 0x03
FC_READ_IR = 0x04


class TcpBus:
    def __init__(self, host: str, port: int = 502, unit: int = 1, timeout: float = 1.0):
        self.host = host
        self.port = int(port)
        self.unit = int(unit) & 0xFF
        self.timeout = float(timeout)
        self.sock: socket.socket | None = None
        self.tracer = None
        self._tid = 0
        self.port_label = f"{host}:{port}"

    # ------------------------------------------------------------- lifecycle
    def open(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def is_open(self) -> bool:
        return self.sock is not None

    # ------------------------------------------------------------- transport
    def _recv(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            try:
                chunk = self.sock.recv(n - len(buf))  # type: ignore[union-attr]
            except socket.timeout:
                raise ModbusTimeout(f"timeout op {self.port_label}") from None
            except OSError as exc:
                self.close()
                raise ModbusError(f"verbinding verbroken: {exc}") from None
            if not chunk:
                self.close()
                raise ModbusError(f"verbinding gesloten door {self.port_label}")
            buf += chunk
        return buf

    def _xfer(self, pdu: bytes) -> bytes:
        if self.sock is None:
            raise ModbusError("niet verbonden")
        self._tid = (self._tid + 1) & 0xFFFF
        req = struct.pack(">HHHB", self._tid, 0, len(pdu) + 1, self.unit) + pdu
        try:
            self.sock.sendall(req)
        except OSError as exc:
            self.close()
            raise ModbusError(f"versturen mislukt: {exc}") from None
        tid, proto, length, _unit = struct.unpack(">HHHB", self._recv(7))
        if length < 2 or length > 260:
            raise ModbusError(f"ongeldige MBAP-lengte {length}")
        body = self._recv(length - 1)
        if not body:
            raise ModbusTimeout(f"leeg antwoord van {self.port_label}")
        if body[0] & 0x80:
            raise ModbusException(body[1])
        return body[1:]

    # ------------------------------------------------------------- reads
    def _read_bits(self, fc: int, addr: int, start: int, qty: int) -> list[int]:
        if not 1 <= qty <= 2000:
            raise ModbusError("ongeldig aantal bits")
        t0 = time.perf_counter()
        try:
            data = self._xfer(struct.pack(">BHH", fc, start, qty))
        except ModbusError as exc:
            self._note(fc, addr, start, qty, t0, exc)
            raise
        self._note(fc, addr, start, qty, t0)
        bits = []
        for i in range(qty):
            bits.append((data[1 + i // 8] >> (i % 8)) & 1)
        return bits

    def read_coils(self, addr: int, start: int, qty: int) -> list[int]:
        return self._read_bits(FC_READ_COILS, addr, start, qty)

    def read_discrete_inputs(self, addr: int, start: int, qty: int) -> list[int]:
        return self._read_bits(FC_READ_DI, addr, start, qty)

    def _read_regs(self, fc: int, addr: int, start: int, qty: int) -> list[int]:
        if not 1 <= qty <= 125:
            raise ModbusError("ongeldig aantal registers")
        t0 = time.perf_counter()
        try:
            data = self._xfer(struct.pack(">BHH", fc, start, qty))
        except ModbusError as exc:
            self._note(fc, addr, start, qty, t0, exc)
            raise
        self._note(fc, addr, start, qty, t0)
        return list(struct.unpack(">" + "H" * qty, data[1:1 + qty * 2]))

    def read_holding(self, addr: int, start: int, qty: int) -> list[int]:
        return self._read_regs(FC_READ_HR, addr, start, qty)

    def read_input(self, addr: int, start: int, qty: int) -> list[int]:
        return self._read_regs(FC_READ_IR, addr, start, qty)

    # ------------------------------------------------------------- writes
    def write_coil(self, addr: int, coil: int, value: bool) -> None:
        val = 0xFF00 if value else 0x0000
        t0 = time.perf_counter()
        try:
            self._xfer(struct.pack(">BHH", 0x05, coil, val))
        except ModbusError as exc:
            self._note(0x05, addr, coil, 1, t0, exc, 1 if value else 0)
            raise
        self._note(0x05, addr, coil, 1, t0, None, 1 if value else 0)

    def write_register(self, addr: int, register: int, value: int) -> None:
        t0 = time.perf_counter()
        try:
            self._xfer(struct.pack(">BHH", 0x06, register, value & 0xFFFF))
        except ModbusError as exc:
            self._note(0x06, addr, register, 1, t0, exc, value)
            raise
        self._note(0x06, addr, register, 1, t0, None, value)

    def write_registers(self, addr: int, start: int, values: list[int]) -> None:
        payload = b"".join(struct.pack(">H", v & 0xFFFF) for v in values)
        pdu = struct.pack(">BHHB", 0x10, start, len(values), len(payload)) + payload
        t0 = time.perf_counter()
        try:
            self._xfer(pdu)
        except ModbusError as exc:
            self._note(0x10, addr, start, len(values), t0, exc)
            raise
        self._note(0x10, addr, start, len(values), t0)

    # ------------------------------------------------------------- tracing
    def _note(self, fc, addr, start, qty, t0, err=None, val=None):
        if self.tracer is None:
            return
        try:
            self.tracer({
                "addr": addr, "fc": fc, "start": start, "qty": qty,
                "ms": int((time.perf_counter() - t0) * 1000),
                "err": str(err) if err else None, "val": val,
            })
        except Exception:
            pass
