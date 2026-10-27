# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Gezel HVAC+ (https://gezel.be)
"""Minimale BACnet/IP-client (Who-Is, ReadProperty, WriteProperty) — enkel stdlib.

Bewust beperkt: unicast naar één toestel per keer, geen routing, geen
ReadPropertyMultiple. Genoeg om een toestel te vinden, punten te lezen/schrijven
en een EDE-lijst te trekken.
"""

from __future__ import annotations

import random
import re
import socket
import struct
import time

BACNET_PORT = 47808

OBJ_TYPES = {
    0: "analog-input", 1: "analog-output", 2: "analog-value",
    3: "binary-input", 4: "binary-output", 5: "binary-value",
    8: "device", 13: "multi-state-input", 14: "multi-state-output",
    19: "multi-state-value",
}
OBJ_ABBR = {
    0: "AI", 1: "AO", 2: "AV", 3: "BI", 4: "BO", 5: "BV",
    8: "DEV", 13: "MSI", 14: "MSO", 19: "MSV",
}

UNITS = {
    0: "square-meters", 3: "amperes", 5: "volts", 19: "kilowatt-hours", 27: "hertz",
    31: "meters", 39: "kilograms", 47: "watts", 48: "kilowatts", 53: "pascals",
    55: "bars", 62: "degrees-celsius", 63: "degrees-kelvin", 64: "degrees-fahrenheit",
    71: "hours", 72: "minutes", 73: "seconds", 80: "cubic-meters",
    84: "cubic-feet-per-minute", 87: "liters-per-second", 88: "liters-per-minute",
    89: "us-gallons-per-minute", 95: "no-units", 96: "parts-per-million",
    98: "percent", 104: "revolutions-per-minute", 133: "hectopascals",
    134: "millibars", 135: "cubic-meters-per-hour", 136: "liters-per-hour",
    146: "megawatt-hours", 157: "kilo-btus-per-hour", 210: "grams-per-kilogram",
}

PROP_OBJECT_LIST = 76
PROP_OBJECT_NAME = 77
PROP_DESCRIPTION = 28
PROP_PRESENT_VALUE = 85
PROP_UNITS = 117
PROP_STATUS_FLAGS = 111


class BacnetError(Exception):
    pass


# --------------------------------------------------------------------------- encoding
def _ctx(num: int, data: bytes) -> bytes:
    """Context-tag: tag(4 bits) | klasse=1 (0x08) | lengte(3 bits)."""
    if len(data) < 5:
        return bytes([(num << 4) | 0x08 | len(data)]) + data
    return bytes([(num << 4) | 0x08 | 5, len(data)]) + data


def _uint_bytes(value: int) -> bytes:
    n = max(1, (int(value).bit_length() + 7) // 8)
    return int(value).to_bytes(n, "big")


def _app_uint(value: int) -> bytes:
    data = _uint_bytes(value)
    return bytes([0x20 | len(data)]) + data


def _app_int(value: int) -> bytes:
    data = int(value).to_bytes(4, "big", signed=True)
    while len(data) > 1 and data[0] in (0x00, 0xFF) and (
        (data[0] == 0 and data[1] < 0x80) or (data[0] == 0xFF and data[1] >= 0x80)
    ):
        data = data[1:]
    return bytes([0x30 | len(data)]) + data


def _app_real(value: float) -> bytes:
    return b"\x44" + struct.pack(">f", float(value))


def _app_bool(value: bool) -> bytes:
    return bytes([0x10 | (1 if value else 0)])


def _app_enum(value: int) -> bytes:
    data = _uint_bytes(value)
    return bytes([0x90 | len(data)]) + data


def _app_str(text: str) -> bytes:
    data = text.encode("utf-8")
    if len(data) < 5:
        return bytes([0x70 | len(data)]) + data
    return b"\x75" + bytes([len(data)]) + data


UNIT_SYMBOLS = {
    "degrees-celsius": "°C", "degrees-kelvin": "K", "degrees-fahrenheit": "°F",
    "percent": "%", "parts-per-million": "ppm", "parts-per-billion": "ppb",
    "cubic-meters-per-hour": "m³/h", "cubic-meters-per-second": "m³/s",
    "liters-per-second": "l/s", "liters-per-minute": "l/min",
    "pascals": "Pa", "kilopascals": "kPa", "bar": "bar", "millibar": "mbar",
    "watts": "W", "kilowatts": "kW", "megawatts": "MW",
    "kilowatt-hours": "kWh", "volts": "V", "millivolts": "mV", "amperes": "A",
    "hertz": "Hz", "seconds": "s", "minutes": "min", "hours": "h", "days": "d",
    "no-units": "", "degrees": "°", "meters": "m", "millimeters": "mm",
    "kilograms": "kg", "cubic-meters": "m³", "liters": "l",
}


def local_broadcasts() -> list[str]:
    """Broadcast-adressen van de eigen interfaces (IPv4), afgeleid uit ip/mask.

    Zo blijft Who-Is werken als de Pi op de werf in een andere DHCP-range staat.
    """
    out: list[str] = []
    try:
        import subprocess

        raw = subprocess.check_output(["ip", "-4", "-o", "addr", "show"], timeout=3).decode()
    except Exception:                                   # noqa: BLE001
        return out
    for line in raw.splitlines():
        parts = line.split()
        for token in parts:
            if "/" in token and token.count(".") == 3:
                addr, _, mask = token.partition("/")
                try:
                    bits = int(mask)
                    if bits >= 31:                    # /31 en /32 hebben geen broadcast
                        continue
                    ip_int = struct.unpack(">I", socket.inet_aton(addr))[0]
                    netmask = (0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF if bits else 0
                    bcast = socket.inet_ntoa(struct.pack(">I", (ip_int & netmask) | (~netmask & 0xFFFFFFFF)))
                except (OSError, ValueError):
                    continue
                if bcast not in out and not addr.startswith("127."):
                    out.append(bcast)
    return out


def _obj_id(obj_type: int, instance: int) -> bytes:
    return struct.pack(">I", ((obj_type & 0x3FF) << 22) | (instance & 0x3FFFFF))


# --------------------------------------------------------------------------- decoding
def _read_tag(buf: bytes, i: int):
    b = buf[i]
    i += 1
    tag = b >> 4
    cls = (b >> 3) & 1
    ln = b & 7
    if ln == 5:
        ln = buf[i]
        i += 1
    return tag, cls, ln, i


def parse_value(buf: bytes, i: int):
    """Lees één applicatie-tag vanaf positie i. Geeft (waarde, nieuwe index)."""
    tag, cls, ln, i = _read_tag(buf, i)
    if cls == 1:                       # context tag binnen een waarde
        data = buf[i:i + ln]
        return ("ctx", data), i + ln
    if tag == 0:                       # null
        return None, i
    if tag == 1:                       # boolean: lengteveld is de waarde
        return bool(ln), i
    data = buf[i:i + ln]
    i += ln
    if tag == 2:
        return int.from_bytes(data, "big"), i
    if tag == 3:
        return int.from_bytes(data, "big", signed=True), i
    if tag == 4:
        return struct.unpack(">f", data)[0], i
    if tag == 5:
        return struct.unpack(">d", data)[0], i
    if tag == 6:
        return data, i
    if tag == 7:
        return data.decode("utf-8", "replace"), i
    if tag == 8:                       # bit string
        return data, i
    if tag == 9:
        return int.from_bytes(data, "big"), i
    if tag == 12:
        return int.from_bytes(data, "big"), i
    return data, i


def parse_ack(buf: bytes):
    """buf = APDU vanaf de servicecode; geeft lijst waarden uit de opening tag."""
    i = 0
    while i < len(buf):
        b = buf[i]
        if (b >> 4) == 3 and (b & 7) == 6:      # opening tag 3
            i += 1
            break
        tag, cls, ln, i = _read_tag(buf, i)
        i += ln
    values = []
    while i < len(buf):
        if buf[i] == 0x3F:                       # closing tag 3
            break
        value, i = parse_value(buf, i)
        values.append(value)
    if not values:
        return None
    return values[0] if len(values) == 1 else values


# --------------------------------------------------------------------------- EDE
PROP_DESCRIPTION = 28
PROP_NOTIFICATION_CLASS = 17
PROP_STATE_TEXT = 111
PROP_NUMBER_OF_STATES = 74

EDE_LAYOUT = "2.3"
EDE_SEP = ";"
EDE_EOL = "\r\n"
BOM = "\ufeff"

EDE_COLUMNS = [
    ("keyname", True),
    ("device obj.-instance", True),
    ("object-name", True),
    ("object-type", True),
    ("object-instance", True),
    ("description", False),
    ("present-value-default", False),
    ("min-present-value", False),
    ("max-present-value", False),
    ("settable", False),
    ("supports COV", False),
    ("hi-limit", False),
    ("low-limit", False),
    ("state-text-reference", False),
    ("unit-code", False),
    ("vendor-specific-address", False),
    ("notification-class", False),
]

COMMANDABLE = (1, 2, 4, 5, 14, 19)
STATEFUL = (3, 4, 5, 13, 14, 19)


def _ede_row(cells) -> str:
    return EDE_SEP.join(str(c).replace(EDE_SEP, ",") if c is not None else "" for c in cells) + EDE_EOL


def _ede_clean(text) -> str:
    """Waarden mogen geen regelafbreking of scheidingsteken bevatten."""
    return " ".join(str(text or "").split())


def _slug(text: str, fallback: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_.\-]", "_", text or "").strip("_")
    return out or fallback


def _csv_bytes(lines) -> bytes:
    return (BOM + "".join(lines)).encode("utf-8")


def _unit_rows() -> list[str]:
    lines = [_ede_row(["#Encoding of BACnet Engineering Units"]), _ede_row(["#Code", "Unit Text"])]
    for code in sorted(UNITS):
        lines.append(_ede_row([code, UNITS[code]]))
    return lines


def _objtype_rows() -> list[str]:
    lines = [_ede_row(["#Encoding of BACnet Object Types", "", ""]), _ede_row(["#Code", "Object Type", ""])]
    for code in sorted(OBJ_TYPES):
        pretty = OBJ_TYPES[code].replace("-", " ").title()
        lines.append(_ede_row([code, pretty, ""]))
    return lines


def _state_rows(table: list[tuple[int, list[str]]]) -> list[str]:
    width = max([len(texts) for _, texts in table] or [2])
    header = ["#Reference Number", "Text 1 or Inactive-Text", "Text 2 or Active-Text"]
    header += [f"Text {i}" for i in range(3, width + 1)]
    lines = [_ede_row(["#State Text Reference"] + [""] * (len(header) - 1)), _ede_row(header)]
    for ref, texts in table:
        lines.append(_ede_row([ref] + texts + [""] * (len(header) - 1 - len(texts))))
    return lines


# --------------------------------------------------------------------------- client
class BacnetClient:
    def __init__(self, bind_ip: str = "0.0.0.0", port: int = BACNET_PORT, timeout: float = 2.0,
                 delay: float = 0.04):
        self.delay = max(0.0, delay)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind((bind_ip, port))
        self.timeout = timeout
        self._inv = random.randint(0, 180)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    # ---------------------------------------------------------------- transport
    def _send(self, ip: str, apdu: bytes, control: int = 0x04) -> None:
        npdu = bytes([0x01, control]) + apdu
        packet = bytes([0x81, 0x0A]) + struct.pack(">H", len(npdu) + 4) + npdu
        try:
            self.sock.sendto(packet, (ip, BACNET_PORT))
        except OSError as exc:
            raise BacnetError(f"versturen mislukt: {exc}") from None

    def _recv(self, deadline: float):
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise BacnetError("timeout — geen antwoord")
            self.sock.settimeout(remaining)
            try:
                data, src = self.sock.recvfrom(4096)
            except socket.timeout:
                raise BacnetError("timeout — geen antwoord") from None
            if len(data) < 8 or data[0] != 0x81:
                continue
            npdu = data[4:]
            if not npdu or npdu[0] != 0x01:
                continue
            if npdu[1] & 0x20:            # netwerklaag-bericht (bv. Who-Is)
                continue
            return npdu[2:], src

    def _pace(self) -> None:
        """Kleine pauze tussen verzoeken; sommige toestellen/ stacks verzuren bij een salvo."""
        if self.delay:
            time.sleep(self.delay)

    def _drain(self) -> None:
        """Gooi oude datagrammen weg zodat een antwoord niet bij het vorige verzoek hoort."""
        try:
            self.sock.setblocking(False)
            while True:
                self.sock.recvfrom(4096)
        except (BlockingIOError, OSError):
            pass
        finally:
            self.sock.setblocking(True)

    def _confirmed(self, ip: str, service: int, body: bytes, timeout: float | None = None,
                   attempts: int = 3):
        """Eén verzoek tegelijk; UDP kan een antwoord verliezen, dus we proberen het opnieuw."""
        last: Exception | None = None
        for _ in range(max(1, attempts)):
            self._inv = (self._inv % 127) + 1
            inv = self._inv
            self._drain()
            self._pace()
            self._send(ip, bytes([0x00, inv, 0x05, service]) + body)
            try:
                return self._await(ip, inv, timeout)
            except BacnetError as exc:
                last = exc
                time.sleep(0.05)
        raise last or BacnetError("geen antwoord")

    def _await(self, ip: str, inv: int, timeout: float | None = None):
        deadline = time.time() + (timeout or self.timeout)
        while True:
            apdu, _src = self._recv(deadline)
            pdu_type = apdu[0] & 0xF0
            # We doen één verzoek tegelijk, dus een ack zonder exacte invoke-match
            # is nog steeds ons antwoord (sommige stacks echoën de invoke niet).
            if pdu_type == 0x30 and len(apdu) > 2:      # complex ack
                return apdu[3:]
            if pdu_type == 0x20 and len(apdu) > 1:      # simple ack
                return b""
            if pdu_type == 0x50:
                raise BacnetError("BACnet error (toestel weigert het verzoek)")
            if pdu_type == 0x60:
                raise BacnetError("BACnet reject (onbekende parameter)")
            if pdu_type == 0x70:
                raise BacnetError("BACnet abort")

    # ---------------------------------------------------------------- services
    def whois(self, timeout: float = 3.0, subnets: list[str] | None = None) -> list[dict]:
        apdu = b"\x10\x08"
        npdu = bytes([0x01, 0x20, 0xFF, 0xFF, 0x00, 0xFF]) + apdu
        packet = bytes([0x81, 0x0B]) + struct.pack(">H", len(npdu) + 4) + npdu
        targets = ["255.255.255.255"]
        for s in subnets or []:
            if s and s not in targets:
                targets.append(s)
        for target in targets:
            try:
                self.sock.sendto(packet, (target, BACNET_PORT))
            except OSError:
                pass
        found: dict[int, dict] = {}
        end = time.time() + timeout
        while time.time() < end:
            try:
                apdu, src = self._recv(end)
            except BacnetError:
                break
            if not apdu or apdu[0] != 0x10 or len(apdu) < 10 or apdu[1] != 0x00:
                continue
            tag, cls, ln, i = _read_tag(apdu, 2)
            if ln != 4 or not ((tag == 12 and cls == 0) or (tag == 0 and cls == 1)):
                continue
            oid = int.from_bytes(apdu[i:i + 4], "big")
            i += 4
            vals = []
            while i < len(apdu):
                value, i = parse_value(apdu, i)
                vals.append(value)
            dev = oid & 0x3FFFFF
            vendor = vals[2] if len(vals) > 2 and isinstance(vals[2], int) else 0
            if dev in found:
                continue
            entry = {
                "device": dev, "ip": src[0], "vendor": vendor,
                "name": "", "model": "",
            }
            try:
                entry["name"] = self.read_property(src[0], 8, dev, PROP_OBJECT_NAME, timeout=0.8)
            except BacnetError:
                pass
            try:
                entry["model"] = self.read_property(src[0], 8, dev, 70, timeout=0.8)
            except BacnetError:
                pass
            found[dev] = entry
        return sorted(found.values(), key=lambda d: d["device"])

    def read_property(self, ip: str, obj_type: int, instance: int, prop: int,
                      index: int | None = None, timeout: float | None = None):
        body = _ctx(0, _obj_id(obj_type, instance)) + _ctx(1, _uint_bytes(prop))
        if index is not None:
            body += _ctx(2, _uint_bytes(index))
        rest = self._confirmed(ip, 0x0C, body, timeout)
        return parse_ack(rest)

    def write_property(self, ip: str, obj_type: int, instance: int, prop: int, value) -> None:
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
        self._confirmed(ip, 0x0F, body, timeout=max(self.timeout, 3.0))

    # ---------------------------------------------------------------- EDE
    def objects(self, ip: str, device: int, timeout: float | None = None) -> list[dict]:
        count = self.read_property(ip, 8, device, PROP_OBJECT_LIST, 0, timeout)
        if not isinstance(count, int):
            raise BacnetError("object-list niet leesbaar")
        out = []
        for i in range(1, min(count, 400) + 1):
            oid = self.read_property(ip, 8, device, PROP_OBJECT_LIST, i, timeout)
            if isinstance(oid, tuple) and len(oid) == 2 and len(oid[1]) == 4:
                oid = int.from_bytes(oid[1], "big")     # context-getagd object-id
            if not isinstance(oid, int):
                continue
            t, inst = oid >> 22, oid & 0x3FFFFF
            out.append({"type": t, "inst": inst, "name": OBJ_TYPES.get(t, f"type-{t}"),
                        "abbr": OBJ_ABBR.get(t, str(t))})
        return out

    def ede_package(self, ip: str, device: int, project: str = "", author: str = "",
                    max_points: int = 400) -> dict:
        """Volledige EDE-export volgens B.I.G.-EU layout 2.3: vier CSV-bestanden."""
        objs = self.objects(ip, device)[:max_points]

        try:
            dev_name = _ede_clean(self.read_property(ip, 8, device, PROP_OBJECT_NAME))
        except BacnetError:
            dev_name = ""

        prefix = _slug(project or dev_name or f"Device{device}", f"Device{device}")
        state_table: list[tuple[int, list[str]]] = []
        state_refs: dict[tuple, int] = {}
        units_used: set[int] = set()
        rows: list[str] = []

        for o in objs:
            t, inst = o["type"], o["inst"]
            name = ""
            desc = ""
            unit = None
            nc = None
            try:
                name = _ede_clean(self.read_property(ip, t, inst, PROP_OBJECT_NAME))
            except BacnetError:
                pass
            try:
                desc = _ede_clean(self.read_property(ip, t, inst, PROP_DESCRIPTION))
            except BacnetError:
                pass
            if t in (0, 1, 2):
                try:
                    u = self.read_property(ip, t, inst, PROP_UNITS)
                    if isinstance(u, (int, float)) and not isinstance(u, bool):
                        unit = int(u)
                        units_used.add(unit)
                except BacnetError:
                    pass
            try:
                value = self.read_property(ip, t, inst, PROP_NOTIFICATION_CLASS)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    nc = int(value)
            except BacnetError:
                pass

            state_ref = ""
            if t in STATEFUL:
                texts: list[str] = []
                count = 2
                if t in (13, 14, 19):
                    try:
                        n = self.read_property(ip, t, inst, PROP_NUMBER_OF_STATES)
                        count = int(n) if isinstance(n, (int, float)) else 2
                    except BacnetError:
                        count = 2
                for idx in range(1, max(2, min(count, 12)) + 1):
                    try:
                        texts.append(_ede_clean(self.read_property(ip, t, inst, PROP_STATE_TEXT, idx)))
                    except BacnetError:
                        break
                texts = [x for x in texts if x]
                if texts:
                    key = tuple(texts)
                    if key not in state_refs:
                        ref = len(state_refs) + 1
                        state_refs[key] = ref
                        state_table.append((ref, texts))
                    state_ref = state_refs[key]

            keyname = _slug(name or f"{o['abbr']}{inst}", f"{o['abbr']}{inst}")
            rows.append(_ede_row([
                keyname, device, name, t, inst, desc,
                "", "", "",
                "Y" if t in COMMANDABLE else "N",
                "", "", "",
                state_ref, "" if unit is None else unit,
                "", "" if nc is None else nc,
            ]))

        head = [
            _ede_row(["# Engineering-Data-Exchange - B.I.G.-EU"]),
            _ede_row(["PROJECT_NAME", _ede_clean(project or prefix)]),
            _ede_row(["VERSION_OF_REFERENCEFILE", "1"]),
            _ede_row(["TIMESTAMP_OF_LAST_CHANGE", time.strftime("%d.%m.%Y %H:%M:%S")]),
            _ede_row(["AUTHOR_OF_LAST_CHANGE", _ede_clean(author or "Gezel HVAC+ Modbus Lab")]),
            _ede_row(["VERSION_OF_LAYOUT", EDE_LAYOUT]),
            _ede_row(["#" + ("mandatory" if EDE_COLUMNS[0][1] else "optional")]
                     + ["mandatory" if m else "optional" for _, m in EDE_COLUMNS[1:]]),
            _ede_row(["# " + EDE_COLUMNS[0][0]] + [name for name, _ in EDE_COLUMNS[1:]]),
        ]

        return {
            "prefix": prefix,
            "files": {
                f"{prefix}_EDE.csv": _csv_bytes(head + rows),
                f"{prefix}_ObjTypes.csv": _csv_bytes(_objtype_rows()),
                f"{prefix}_StateTexts.csv": _csv_bytes(_state_rows(state_table)),
                f"{prefix}_Units.csv": _csv_bytes(_unit_rows()),
            },
            "objects": len(rows),
            "state_texts": len(state_table),
            "units": len(units_used),
        }

    def ede(self, ip: str, device: int, max_points: int = 200) -> list[dict]:
        rows = []
        for obj in self.objects(ip, device)[:max_points]:
            t, inst = obj["type"], obj["inst"]
            row = {"ObjectType": obj["abbr"], "ObjectInstance": inst,
                   "ObjectName": "", "Description": "", "PresentValue": "",
                   "Units": ""}
            try:
                row["ObjectName"] = self.read_property(ip, t, inst, PROP_OBJECT_NAME, timeout=1.0) or ""
            except BacnetError:
                pass
            try:
                row["Description"] = self.read_property(ip, t, inst, PROP_DESCRIPTION, timeout=1.0) or ""
            except BacnetError:
                pass
            try:
                pv = self.read_property(ip, t, inst, PROP_PRESENT_VALUE, timeout=1.0)
                row["PresentValue"] = "" if pv is None else (round(pv, 3) if isinstance(pv, float) else pv)
            except BacnetError:
                pass
            if t in (0, 1, 2):
                try:
                    unit = self.read_property(ip, t, inst, PROP_UNITS, timeout=1.0)
                    if isinstance(unit, (int, float)) and not isinstance(unit, bool):
                        name = UNITS.get(int(unit), f"unit-{int(unit)}")
                        row["Units"] = UNIT_SYMBOLS.get(name, name)
                    else:
                        row["Units"] = ""
                except BacnetError:
                    pass
            rows.append(row)
        return rows
