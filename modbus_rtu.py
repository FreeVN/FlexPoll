"""Minimal, dependency-light Modbus RTU master on top of pyserial.

Bewust geen pymodbus: we willen exacte controle over timeouts, framing en
foutmeldingen (dit is een testbank voor RS-485 bussen).
"""

from __future__ import annotations

import struct
import time

import serial

PARITIES = {
    "N": serial.PARITY_NONE,
    "E": serial.PARITY_EVEN,
    "O": serial.PARITY_ODD,
}


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


class ModbusError(Exception):
    """Basisklasse voor alle busfouten."""


class ModbusTimeout(ModbusError):
    pass


class BusDown(ModbusError):
    pass


class ModbusException(ModbusError):
    CODES = {
        1: "illegale functie",
        2: "illegaal data-adres",
        3: "illegale waarde",
        4: "slave-fout",
        5: "bezig (acknowledge)",
        6: "slave bezet",
        8: "geheugenpariteitsfout",
        10: "gateway-pad niet beschikbaar",
        11: "gateway: geen antwoord",
    }

    def __init__(self, code: int):
        self.code = code
        super().__init__(f"Modbus exception {code} ({self.CODES.get(code, 'onbekend')})")


class Bus:
    def __init__(self, port: str, baud: int = 9600, parity: str = "N",
                 stopbits: int = 1, timeout: float = 0.5):
        self.port = port
        self.baud = int(baud)
        self.parity = parity if parity in PARITIES else "N"
        self.stopbits = float(stopbits)
        self.timeout = float(timeout)
        self.serial: serial.Serial | None = None
        self.tracer = None   # optioneel: callable(dict) voor busdebug-logging

    # ------------------------------------------------------------------ lifecycle
    def open(self) -> None:
        self.close()
        self.serial = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            bytesize=serial.EIGHTBITS,
            parity=PARITIES[self.parity],
            stopbits=serial.STOPBITS_ONE if self.stopbits == 1 else serial.STOPBITS_TWO,
            timeout=self.timeout,
            write_timeout=max(1.0, self.timeout),
        )

    def close(self) -> None:
        if self.serial is not None:
            try:
                self.serial.close()
            except Exception:
                pass
            self.serial = None

    def is_open(self) -> bool:
        return bool(self.serial is not None and self.serial.is_open)

    def _note(self, addr: int, fc: int, start: int, qty: int, t0: float,
              err: Exception | None = None, val: int | None = None) -> None:
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

    # ------------------------------------------------------------------ framing
    def _xfer(self, addr: int, pdu: bytes, read_len: int) -> bytes:
        if not self.is_open():
            raise BusDown("seriële poort niet open")
        req = bytes([addr & 0xFF]) + pdu
        req += struct.pack("<H", crc16(req))
        try:
            self.serial.reset_input_buffer()
            self.serial.write(req)
            self.serial.flush()
        except (serial.SerialException, OSError) as exc:
            raise BusDown(f"schrijffout op {self.port}: {exc}") from exc

        head = self.serial.read(3)
        if len(head) < 3:
            raise ModbusTimeout(f"geen antwoord van adres {addr}")
        if head[0] != addr:
            raise ModbusError(f"onverwacht slave-adres {head[0]} (verwacht {addr})")
        if head[1] & 0x80:
            tail = self.serial.read(2)
            if len(tail) < 2:
                raise ModbusTimeout("afgekapt exception-antwoord")
            raise ModbusException(head[2])
        if head[1] != pdu[0]:
            raise ModbusError(f"onverwachte functiecode {head[1]} (verwacht {pdu[0]})")

        body = self.serial.read(read_len)
        if len(body) < read_len:
            raise ModbusTimeout("onvolledig antwoord")
        frame = head + body
        if struct.unpack("<H", frame[-2:])[0] != crc16(frame[:-2]):
            raise ModbusError("CRC-fout in antwoord")
        # frame = adres | functie | bytecount | data... | crc16
        return frame[3:-2]

    # ------------------------------------------------------------------ reads
    def _read_bits(self, addr: int, fc: int, start: int, qty: int) -> list[int]:
        if not 1 <= qty <= 2000:
            raise ModbusError("ongeldig aantal bits")
        t0 = time.perf_counter()
        try:
            data = self._xfer(addr, struct.pack(">BHH", fc, start, qty), (qty + 7) // 8 + 2)
        except ModbusError as exc:
            self._note(addr, fc, start, qty, t0, exc)
            raise
        self._note(addr, fc, start, qty, t0)
        bits = []
        for i in range(qty):
            bits.append((data[i // 8] >> (i % 8)) & 1)
        return bits

    def read_coils(self, addr: int, start: int, qty: int) -> list[int]:
        return self._read_bits(addr, 0x01, start, qty)

    def read_discrete_inputs(self, addr: int, start: int, qty: int) -> list[int]:
        return self._read_bits(addr, 0x02, start, qty)

    def read_holding(self, addr: int, start: int, qty: int) -> list[int]:
        if not 1 <= qty <= 125:
            raise ModbusError("ongeldig aantal registers")
        t0 = time.perf_counter()
        try:
            data = self._xfer(addr, struct.pack(">BHH", 0x03, start, qty), qty * 2 + 2)
        except ModbusError as exc:
            self._note(addr, 0x03, start, qty, t0, exc)
            raise
        self._note(addr, 0x03, start, qty, t0)
        return list(struct.unpack(">" + "H" * qty, data))

    def read_input(self, addr: int, start: int, qty: int) -> list[int]:
        if not 1 <= qty <= 125:
            raise ModbusError("ongeldig aantal registers")
        t0 = time.perf_counter()
        try:
            data = self._xfer(addr, struct.pack(">BHH", 0x04, start, qty), qty * 2 + 2)
        except ModbusError as exc:
            self._note(addr, 0x04, start, qty, t0, exc)
            raise
        self._note(addr, 0x04, start, qty, t0)
        return list(struct.unpack(">" + "H" * qty, data))

    # ------------------------------------------------------------------ writes
    def write_coil(self, addr: int, coil: int, value: bool) -> None:
        val = 0xFF00 if value else 0x0000
        t0 = time.perf_counter()
        try:
            self._xfer(addr, struct.pack(">BHH", 0x05, coil, val), 5)
        except ModbusError as exc:
            self._note(addr, 0x05, coil, 1, t0, exc, 1 if value else 0)
            raise
        self._note(addr, 0x05, coil, 1, t0, None, 1 if value else 0)

    def write_register(self, addr: int, register: int, value: int) -> None:
        t0 = time.perf_counter()
        try:
            self._xfer(addr, struct.pack(">BHH", 0x06, register, value & 0xFFFF), 5)
        except ModbusError as exc:
            self._note(addr, 0x06, register, 1, t0, exc, value)
            raise
        self._note(addr, 0x06, register, 1, t0, None, value)

    def write_registers(self, addr: int, start: int, values: list[int]) -> None:
        payload = b"".join(struct.pack(">H", v & 0xFFFF) for v in values)
        pdu = struct.pack(">BHHB", 0x10, start, len(values), len(payload)) + payload
        t0 = time.perf_counter()
        try:
            self._xfer(addr, pdu, 5)
        except ModbusError as exc:
            self._note(addr, 0x10, start, len(values), t0, exc)
            raise
        self._note(addr, 0x10, start, len(values), t0)
