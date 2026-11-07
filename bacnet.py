# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
"""Minimale BACnet/IP-client (Who-Is, ReadProperty, WriteProperty) — enkel stdlib.

Bewust beperkt: één toestel per keer, geen ReadPropertyMultiple. Genoeg om een
toestel te vinden, punten te lezen/schrijven en een EDE-lijst te trekken.

Routing: een broadcast gaat niet door een router. Daarom twee uitwegen, allebei
zonder dat wij zelf een BBMD worden:

* **Foreign Device** — we melden ons aan bij een bestaande BBMD (BVLC 0x05) en
  herhalen die registratie vóór de TTL verloopt. De BBMD stuurt de broadcasts
  van zijn subnet unicast naar ons door.
* **Unicast-probe** — een Who-Is rechtstreeks naar het IP van één toestel. Lezen
  (ReadProperty) is toch al unicast, dus alleen de discovery heeft een route nodig.
"""

from __future__ import annotations

import random
import re
import socket
import struct
import sys
import time

BACNET_PORT = 47808

# BVLC-functiecodes (het eerste byte na 0x81 is de functie).
BVLC_RESULT = 0x00
BVLC_FORWARDED_NPDU = 0x04
BVLC_REGISTER_FD = 0x05
BVLC_ORIGINAL_UNICAST = 0x0A
BVLC_ORIGINAL_BROADCAST = 0x0B

# Wat wij per antwoord aankunnen: geen segmentatie (0), 1476 bytes (5). Zonder dit veld
# juist te zetten weigert een toestel dat zelf niet kan segmenteren elk groot antwoord.
MAX_SEGS = 0x00
MAX_APDU_RESP = 0x05

OBJ_TYPES = {
    0: "analog-input", 1: "analog-output", 2: "analog-value",
    3: "binary-input", 4: "binary-output", 5: "binary-value",
    6: "calendar", 7: "command", 8: "device", 9: "event-enrollment",
    10: "file", 11: "group", 12: "loop", 13: "multi-state-input",
    14: "multi-state-output", 15: "notification-class", 16: "program",
    17: "schedule", 18: "averaging", 19: "multi-state-value",
    20: "trend-log", 21: "life-safety-point", 22: "life-safety-zone",
    23: "accumulator", 24: "pulse-converter",
}
OBJ_ABBR = {
    0: "AI", 1: "AO", 2: "AV", 3: "BI", 4: "BO", 5: "BV",
    6: "CAL", 7: "CMD", 8: "DEV", 9: "EE", 10: "FILE", 11: "GRP",
    12: "LOOP", 13: "MSI", 14: "MSO", 15: "NC", 16: "PRG", 17: "SCH",
    18: "AVG", 19: "MSV", 20: "TL", 21: "LSP", 22: "LSZ",
    23: "ACC", 24: "PC",
}

# Niet elk objecttype heeft een present-value. Bij de rest (file, group, trend-log,
# notification-class, vendor-types) is een leesactie op 85 gegarandeerd een error —
# dat is geen storing en hoort dus niet als fout op de kaart te staan.
PV_OBJECT_TYPES = {0, 1, 2, 3, 4, 5, 13, 17, 19, 21, 22, 23, 24}

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


class BacnetServerError(BacnetError):
    """Het toestel antwoordde met error/reject/abort — opnieuw sturen helpt niet."""
    definitive = True


# --- named codes: een kale "toestel weigert" verbergt precies de informatie
# --- die je nodig hebt (verkeerd property, read-only punt, verkeerde index).
ERROR_CLASSES = {
    0: "device", 1: "object", 2: "property", 3: "resources",
    4: "security", 5: "services", 6: "vt", 7: "communication",
}

ERROR_CODES = {
    0: "other", 2: "configuration-in-progress", 3: "device-busy",
    7: "inconsistent-parameters", 9: "invalid-data-type",
    16: "missing-required-parameter", 17: "no-objects-of-specified-type",
    18: "no-space-for-object", 25: "operational-problem",
    27: "read-access-denied", 29: "service-request-denied", 30: "timeout",
    31: "unknown-object", 32: "unknown-property",
    36: "unsupported-object-type", 37: "value-out-of-range",
    40: "write-access-denied", 41: "character-set-not-supported",
    42: "invalid-array-index", 45: "optional-functionality-not-supported",
    46: "invalid-configuration-data", 47: "datatype-not-supported",
    48: "duplicate-name", 49: "duplicate-object-id",
    50: "property-is-not-an-array", 54: "segmentation-not-supported",
    57: "invalid-tag", 58: "network-down",
    80: "parameter-out-of-range", 81: "list-element-not-found",
    83: "communication-disabled",
}

ERROR_HINTS = {
    "unknown-object": "dat object bestaat niet op dit toestel — klopt instance/type?",
    "unknown-property": "dit toestel kent dat property niet — sommige leveranciers gebruiken een eigen (vendor-)property",
    "write-access-denied": "punt is read-only of het toestel staat in monitor-only",
    "read-access-denied": "dit punt is niet leesbaar (write-only of beveiligd)",
    "invalid-array-index": "gevraagde index bestaat niet (array te kort of index 0 nodig)",
    "service-request-denied": "toestel weigert deze service — vaak staat schrijven uit op het toestel zelf",
    "optional-functionality-not-supported": "toestel ondersteunt deze service niet (bv. geen WriteProperty)",
    "value-out-of-range": "waarde buiten het bereik van het punt",
    "invalid-data-type": "verkeerd datatype voor dit property (bv. enum naar analog)",
    "device-busy": "toestel is bezet — probeer straks opnieuw",
    "parameter-out-of-range": "parameter buiten bereik",
    "configuration-in-progress": "toestel is in configuratiemodus",
    "segmentation-not-supported": "toestel kan niet segmenteren en het antwoord is groter dan de APDU die wij aankondigen",
}

REJECT_REASONS = {
    0: "other", 1: "buffer-overflow", 2: "inconsistent-parameters",
    3: "invalid-parameter-data-type", 4: "invalid-tag", 5: "missing-required-parameter",
    6: "parameter-out-of-range", 7: "too-many-arguments", 8: "undefined-enumeration",
    9: "unrecognized-service",
}

ABORT_REASONS = {
    0: "other", 1: "buffer-overflow", 2: "invalid-apdu-in-this-state",
    3: "preempted-by-higher-priority-task", 4: "segmentation-not-supported",
    5: "security-error", 6: "insufficient-security", 7: "window-size-out-of-range",
    8: "application-exceeded-reply-time", 9: "out-of-resources", 10: "tsm-timeout",
    11: "apdu-too-long",
}


def _as_int(value, default: int = 0) -> int:
    """Property-waarde veilig naar int; parser kan ook lijsten/strings teruggeven."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _enum_from(buf: bytes, i: int):
    """Lees een getal-tag (applicatie-ENUMERATED 0x91 of context-tag); → (waarde, index)."""
    if i >= len(buf):
        return None, i
    tag, _cls, ln, start = _read_tag(buf, i)
    if ln == 0:
        return None, start
    return int.from_bytes(buf[start:start + ln], "big"), start + ln


def describe_apdu_error(apdu: bytes, what: str = "") -> str:
    """Vertaal een error/reject/abort-PDU naar iets waar je iets aan hebt."""
    prefix = f"{what}: " if what else ""
    kind = apdu[0] & 0xF0
    if kind == 0x50:                                  # error
        # error-PDU: [0]=0x50 | [1]=invoke-id | [2]=service | [3..]=error-class+error-code
        cls = code = None
        if len(apdu) > 3:
            cls, i = _enum_from(apdu, 3)
            code, _ = _enum_from(apdu, i)
        cls_name = ERROR_CLASSES.get(cls, f"class {cls}")
        code_name = ERROR_CODES.get(code, f"code {code}")
        msg = f"{prefix}toestel weigert het verzoek — error-class {cls_name}, error-code {code_name}"
        hint = ERROR_HINTS.get(code_name)
        return msg + (f" ({hint})" if hint else "")
    if kind == 0x60:                                  # reject
        reason = apdu[2] if len(apdu) > 2 else None
        return (f"{prefix}verzoek afgewezen — reject reason "
                f"{REJECT_REASONS.get(reason, reason)} (PDU zelf ongeldig, niet het punt)")
    if kind == 0x70:                                  # abort
        server = bool(apdu[0] & 0x01)                 # server-flag zit in het type-octet
        reason = apdu[2] if len(apdu) > 2 else None
        who = "toestel" if server else "wij"
        return (f"{prefix}verzoek afgebroken door {who} — abort reason "
                f"{ABORT_REASONS.get(reason, reason)}")
    return prefix + "onbekend antwoord"


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


LAST_SOURCE = ""


def _subnet_broadcast(addr: str, mask) -> str | None:
    """Broadcastadres uit een IPv4-adres en een masker (bits of dotted-notatie)."""
    try:
        if isinstance(mask, str):
            if mask.startswith("0x"):
                bits = bin(int(mask, 16)).count("1")
            elif "." in mask:
                bits = bin(struct.unpack(">I", socket.inet_aton(mask))[0]).count("1")
            else:
                bits = int(mask)
        else:
            bits = int(mask)
    except (TypeError, ValueError, OSError):
        return None
    if bits <= 0 or bits >= 31:          # /0, /31 en /32 hebben geen broadcast
        return None
    if addr.startswith(("127.", "169.254.")):
        return None
    try:
        ip_int = struct.unpack(">I", socket.inet_aton(addr))[0]
        nm = (0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF
        return socket.inet_ntoa(struct.pack(">I", (ip_int & nm) | (~nm & 0xFFFFFFFF)))
    except OSError:
        return None


def _from_psutil() -> list[str]:
    """psutil staat niet in de requirements, maar is wel de nette bron als hij er is."""
    import psutil                                  # noqa: PLC0415

    out = []
    for addrs in psutil.net_if_addrs().values():
        for a in addrs:
            if a.family == socket.AF_INET and a.netmask:
                b = _subnet_broadcast(a.address, a.netmask)
                if b:
                    out.append(b)
    return out


def _from_windows() -> list[str]:
    """Windows: IPHLPAPI→GetIpAddrTable. `ip` bestaat daar niet, dus de oude
    aanpak gaf altijd een lege lijst — en dus "geen IPv4-interface gevonden"."""
    import ctypes                                    # noqa: PLC0415

    class Row(ctypes.Structure):
        _fields_ = [("dwAddr", ctypes.c_uint32), ("dwIndex", ctypes.c_uint32),
                    ("dwMask", ctypes.c_uint32), ("dwBCastAddr", ctypes.c_uint32),
                    ("dwReasmSize", ctypes.c_uint32),
                    ("unused1", ctypes.c_uint16), ("unused2", ctypes.c_uint16)]

    class Table(ctypes.Structure):
        _fields_ = [("dwNumEntries", ctypes.c_uint32), ("table", Row * 1)]

    iphlpapi = ctypes.WinDLL("iphlpapi.dll")                     # type: ignore[attr-defined]
    size = ctypes.c_ulong(0)
    iphlpapi.GetIpAddrTable(None, ctypes.byref(size), False)
    if size.value == 0:
        return []
    buf = ctypes.create_string_buffer(size.value)
    if iphlpapi.GetIpAddrTable(buf, ctypes.byref(size), False) != 0:
        return []
    tbl = ctypes.cast(buf, ctypes.POINTER(Table)).contents
    rows = ctypes.cast(ctypes.byref(tbl.table),
                       ctypes.POINTER(Row * tbl.dwNumEntries)).contents
    out = []
    for r in rows:
        # De velden staan in netwerkbytevolgorde; native unpacken geeft het juiste adres.
        addr = socket.inet_ntoa(struct.pack("=I", r.dwAddr))
        b = _subnet_broadcast(addr, bin(r.dwMask).count("1"))
        if b:
            out.append(b)
    return out


def _from_ip_command() -> list[str]:
    import subprocess                                 # noqa: PLC0415

    raw = subprocess.check_output(["ip", "-4", "-o", "addr", "show"],
                                  timeout=3, stderr=subprocess.DEVNULL).decode()
    out = []
    for line in raw.splitlines():
        for token in line.split():
            if token.count(".") == 3 and "/" in token:
                addr, _, mask = token.partition("/")
                b = _subnet_broadcast(addr, mask)
                if b:
                    out.append(b)
    return out


def _from_ifconfig() -> list[str]:
    """macOS/BSD: `ip` ontbreekt, `ifconfig` is er wel. Formaat:
    `inet 192.168.1.34 netmask 0xffffff00 broadcast 192.168.1.255`."""
    import subprocess                                 # noqa: PLC0415

    raw = subprocess.check_output(["ifconfig"], timeout=3,
                                  stderr=subprocess.DEVNULL).decode(errors="replace")
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("inet "):
            continue
        addr = line.split()[1]
        m = re.search(r"netmask\s+(\S+)", line)
        if not m:
            continue
        b = _subnet_broadcast(addr, m.group(1))
        if b:
            out.append(b)
    return out


def local_broadcasts() -> list[str]:
    """Broadcast-adressen van de eigen interfaces (IPv4), afgeleid uit ip/mask.

    Zo blijft Who-Is werken als de doos op de werf in een andere DHCP-range staat.
    Meerdere bronnen, in volgorde van betrouwbaarheid: psutil (als het geïnstalleerd
    is), dan de OS-eigen manier. De oude versie leunde enkel op `ip`, wat op Windows
    én macOS niet bestaat — daar bleef de lijst leeg en leek er geen interface te zijn.
    """
    global LAST_SOURCE

    strategies = [("psutil", _from_psutil)]
    if sys.platform.startswith("win"):
        strategies.append(("iphlpapi", _from_windows))
    strategies += [("ip", _from_ip_command), ("ifconfig", _from_ifconfig)]

    for name, fn in strategies:
        try:
            found = [b for b in fn() if b]
        except Exception:                            # noqa: BLE001 — bron niet beschikbaar
            continue
        if found:
            uniq: list[str] = []
            for b in found:
                if b not in uniq:
                    uniq.append(b)
            LAST_SOURCE = name
            return uniq
    LAST_SOURCE = ""
    return []


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
    """Waarden mogen geen regelafbreking of scheidingsteken bevatten.

    Ook NUL's weg: legacy-toestellen (EuroICC) leveren hun object-name met een
    leidende \\x00, wat in de EDE-import als rommel in de naam belandt.
    """
    return " ".join(str(text or "").replace("\x00", "").split())


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
        # Foreign Device-registratie: {"ip", "port", "ttl", "expires"} of None.
        self.fd: dict | None = None

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
        """Wacht op een NPDU en geef (apdu, src) terug.

        Een BBMD kan een NPDU doorsturen als *Forwarded-NPDU* (0x04): dan staan er
        nog 6 bytes origineel adres tussen de BVLC-kop en de NPDU. Wie die offset
        negeert, leest het B/IP-adres als NPDU-versie en ziet elk antwoord als
        ongeldig — precies het symptoom \"BBMD werkt wel, FlexPoll vindt niets\".
        """
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
            fn = data[1]
            if fn not in (BVLC_ORIGINAL_UNICAST, BVLC_ORIGINAL_BROADCAST, BVLC_FORWARDED_NPDU):
                continue                       # result/register-FD/BDT: geen NPDU
            offset = 10 if fn == BVLC_FORWARDED_NPDU else 4
            if fn == BVLC_FORWARDED_NPDU and len(data) >= 10:
                # Het origineel B/IP-adres staat in de kop: dat is het toestel,
                # niet de BBMD. Zonder dit lees je later van het BBMD-adres.
                orig_ip = socket.inet_ntoa(data[4:8])
                orig_port = int.from_bytes(data[8:10], "big")
                if orig_ip not in ("0.0.0.0", ""):
                    src = (orig_ip, orig_port or BACNET_PORT)
            npdu = data[offset:]
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
                   attempts: int = 3, what: str = ""):
        """Eén verzoek tegelijk; UDP kan een antwoord verliezen, dus we proberen het opnieuw.

        Alleen bij timeouts is opnieuw sturen zinvol: een error/reject/abort-PDU is een
        beslissing van het toestel en blijft dezelfde — daar verbergen we niets achter
        een retry, we gooien de echte reden meteen naar boven.
        """
        last: Exception | None = None
        for _ in range(max(1, attempts)):
            self._inv = (self._inv % 127) + 1
            inv = self._inv
            self._drain()
            self._pace()
            # Confirmed-Request header is strikt: type | max-segs+max-resp | invoke | service.
            # Stonden invoke en max-resp omgedraaid: dan leest het toestel ons invoke-id als
            # "grootste APDU die ik aankan" (soms 50 bytes) en weigert het een lang antwoord
            # met error-class communication / segmentation-not-supported i.p.v. te zenden.
            self._send(ip, bytes([0x00, MAX_SEGS | MAX_APDU_RESP, inv, service]) + body)
            try:
                return self._await(ip, inv, timeout, what)
            except BacnetServerError:
                raise
            except BacnetError as exc:
                last = exc
                time.sleep(0.05)
        raise last or BacnetError("geen antwoord")

    def _await(self, ip: str, inv: int, timeout: float | None = None, what: str = ""):
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
            if pdu_type in (0x50, 0x60, 0x70):          # error / reject / abort
                raise BacnetServerError(describe_apdu_error(apdu, what))

    # ------------------------------------------------------------ foreign device
    def fd_status(self) -> dict | None:
        if not self.fd:
            return None
        return {
            "bbmd": self.fd["ip"],
            "port": self.fd["port"],
            "ttl": self.fd["ttl"],
            "remaining": max(0, int(self.fd["expires"] - time.time())),
        }

    def register_foreign_device(self, bbmd_ip: str, bbmd_port: int = BACNET_PORT,
                                ttl: int = 60, wait: float = 2.0) -> dict:
        """Meld ons aan bij een BBMD (BVLC Register-Foreign-Device, 0x05).

        De BBMD zet ons in zijn FDT en stuurt de broadcasts van zijn subnet
        unicast naar ons door. Zonder die registratie blijft een Who-Is binnen
        ons eigen subnet steken. TTL 0 = afmelden.
        """
        if not bbmd_ip:
            raise BacnetError("BBMD-adres ontbreekt")
        ttl = max(0, min(65535, int(ttl)))
        # Register-Foreign-Device is een BVLC-functie (0x05), geen NPDU: het
        # pakket is 81 05 00 06 <ttl 2> — zes bytes totaal. De oude variant zette
        # 0x0A (original-unicast) als functie en 0x05 in de payload; een echte
        # BBMD (bacpypes3) negeert dat volledig, waarna je een timeout ziet.
        packet = bytes([0x81, BVLC_REGISTER_FD, 0x00, 0x06]) + struct.pack(">H", ttl)
        try:
            self.sock.sendto(packet, (bbmd_ip, int(bbmd_port)))
        except OSError as exc:
            raise BacnetError(f"BBMD onbereikbaar: {exc}") from None
        if ttl == 0:
            self.fd = None
            return {"ok": True, "bbmd": bbmd_ip, "ttl": 0}
        deadline = time.time() + wait
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise BacnetError(
                    f"geen antwoord van BBMD {bbmd_ip}:{bbmd_port} — draait daar een "
                    "BBMD en is UDP 47808 open?")
            self.sock.settimeout(remaining)
            try:
                data, _src = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            if len(data) < 6 or data[0] != 0x81 or data[1] != BVLC_RESULT:
                continue
            code = int.from_bytes(data[4:6], "big")
            if code != 0:
                # 1 = register-FD-denied:BBMD weigert (FDT vol of beleid).
                raise BacnetError(f"BBMD weigert registratie (result {code})")
            self.fd = {"ip": bbmd_ip, "port": int(bbmd_port), "ttl": ttl,
                       "expires": time.time() + ttl,
                       "local_ip": self._local_ip(bbmd_ip, bbmd_port)}
            return {"ok": True, "bbmd": bbmd_ip, "port": int(bbmd_port), "ttl": ttl}

    def _local_ip(self, peer_ip: str, peer_port: int) -> str:
        """Ons eigen bronadres zoals de BBMD het ziet (voor Forwarded-NPDU)."""
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect((peer_ip, int(peer_port)))
            ip = probe.getsockname()[0]
            probe.close()
            return ip
        except OSError:
            return "0.0.0.0"

    def fd_keepalive(self) -> bool:
        """Herhaal de registratie vóór de TTL verloopt (op TTL/2).

        Vergeten is de klassieke bug: het werkt vijf minuten en daarna niet meer,
        zonder foutmelding — de BBMD heeft ons stil uit zijn FDT gegooid.

        Een doodgelopen BBMD mag de rest niet blokkeren: dit is een herkansing,
        geen voorwaarde. Mislukt ze, dan vergeten we de registratie en zeggen we
        het — anders wacht elke scan opnieuw twee seconden op een pakket dat
        nooit komt, en lijkt de hele BACnet-tab stuk.
        """
        fd = self.fd
        if not fd or not fd.get("ttl"):
            return True
        if time.time() < fd["expires"] - fd["ttl"] / 2.0:
            return True
        try:
            self.register_foreign_device(fd["ip"], fd["port"], fd["ttl"])
            return True
        except BacnetError:
            self.fd = None
            return False

    # ---------------------------------------------------------------- services
    def _device_entry(self, ip: str, dev: int, vendor: int = 0) -> dict:
        entry = {"device": dev, "ip": ip, "vendor": vendor, "name": "", "model": ""}
        try:
            name = self.read_property(ip, 8, dev, PROP_OBJECT_NAME, timeout=0.8)
            entry["name"] = str(name).replace("\x00", "").strip()
        except BacnetError:
            pass
        try:
            model = self.read_property(ip, 8, dev, 70, timeout=0.8)
            entry["model"] = str(model).replace("\x00", "").strip()
        except BacnetError:
            pass
        return entry

    def device_info(self, ip: str, device: int) -> dict:
        """Naam/model van één toestel — voor handmatig toevoegen op IP.

        Faalt de naamleesactie, dan antwoordt dat toestel niet (of blokkeert het
        ReadProperty). Dat is een echte fout, geen lege kaart: zo komen er geen
        dode toestellen in de lijst.
        """
        dev = int(device or 0)
        if not ip or dev <= 0:
            raise BacnetError("ip en device-id zijn verplicht")
        entry = {"device": dev, "ip": ip, "vendor": 0, "name": "", "model": ""}
        try:
            entry["name"] = str(self.read_property(ip, 8, dev, PROP_OBJECT_NAME)) \
                .replace("\x00", "").strip()
        except BacnetError as exc:
            raise BacnetError(f"device {dev} op {ip} antwoordt niet: {exc}") from None
        try:
            entry["model"] = str(self.read_property(ip, 8, dev, 70, timeout=0.8)) \
                .replace("\x00", "").strip()
        except BacnetError:
            pass
        try:
            entry["vendor"] = _as_int(self.read_property(ip, 8, dev, 120, timeout=0.8), 0)
        except (BacnetError, TypeError, ValueError):
            pass
        return entry

    def whois(self, timeout: float = 3.0, subnets: list[str] | None = None,
              unicast: list[str] | None = None) -> list[dict]:
        apdu = b"\x10\x08"
        npdu = bytes([0x01, 0x20, 0xFF, 0xFF, 0x00, 0xFF]) + apdu
        packet = bytes([0x81, 0x0B]) + struct.pack(">H", len(npdu) + 4) + npdu
        targets = ["255.255.255.255"]
        for s in subnets or []:
            if s and s not in targets:
                targets.append(s)
        # Unicast-probe: één Who-Is rechtstreeks naar een toestel-IP. Zo vind je
        # een toestel achter een router zonder BBMD (de meeste stacks antwoorden
        # op een unicast Who-Is; de Who-Is hoeft geen broadcast te zijn).
        for u in unicast or []:
            u = (u or "").strip()
            if u and u not in targets:
                targets.append(u)
        for target in targets:
            try:
                self.sock.sendto(packet, (target, BACNET_PORT))
            except OSError:
                pass
        # Aangemeld als Foreign Device? Dan moet de Who-Is ook *naar de BBMD*
        # als Forwarded-NPDU (BVLC 0x04). Een lokale broadcast komt daar nooit:
        # de BBMD luistert op zijn eigen subnet, niet op het onze.
        fd = self.fd
        if fd and fd.get("local_ip") and fd["local_ip"] != "0.0.0.0":
            orig = socket.inet_aton(fd["local_ip"]) \
                + struct.pack(">H", self.sock.getsockname()[1])
            forwarded = bytes([0x81, BVLC_FORWARDED_NPDU]) \
                + struct.pack(">H", len(npdu) + 4 + 6) + orig + npdu
            try:
                self.sock.sendto(forwarded, (fd["ip"], fd["port"]))
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
            # Alleen verzamelen: het verrijken (naam/model) kost tot 1,6 s per
            # toestel en mag het ontvangstvenster niet opeten. Anders verlies je
            # precies de toestellen die als tweede antwoorden — bij een BBMD is
            # dat steevast het echte toestel na de BBMD zelf.
            found[dev] = {"device": dev, "ip": src[0], "vendor": vendor,
                          "name": "", "model": ""}
        for dev, entry in found.items():
            info = self._device_entry(entry["ip"], dev, entry["vendor"])
            entry["name"], entry["model"] = info["name"], info["model"]
        return sorted(found.values(), key=lambda d: d["device"])

    def read_property(self, ip: str, obj_type: int, instance: int, prop: int,
                      index: int | None = None, timeout: float | None = None):
        body = _ctx(0, _obj_id(obj_type, instance)) + _ctx(1, _uint_bytes(prop))
        if index is not None:
            body += _ctx(2, _uint_bytes(index))
        what = f"lezen {OBJ_ABBR.get(obj_type, obj_type)} {instance} · property {prop}"
        if index is not None:
            what += f"[{index}]"
        rest = self._confirmed(ip, 0x0C, body, timeout, what=what)
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
        what = f"schrijven {OBJ_ABBR.get(obj_type, obj_type)} {instance} · property {prop}"
        self._confirmed(ip, 0x0F, body, timeout=max(self.timeout, 3.0), what=what)

    # ---------------------------------------------------------------- EDE
    @staticmethod
    def _as_oid(oid) -> int | None:
        """Object-id kan als int, als ("ctx", bytes) of als bytes binnenkomen."""
        if isinstance(oid, tuple) and len(oid) == 2 and isinstance(oid[1], (bytes, bytearray)):
            oid = oid[1]
        if isinstance(oid, (bytes, bytearray)) and len(oid) == 4:
            return int.from_bytes(oid, "big")
        return oid if isinstance(oid, int) else None

    def _object_list(self, ip: str, device: int, count: int, timeout: float | None) -> list[int]:
        """Lees de object-list in één verzoek; val terug op per-element als dat niet gaat.

        Eén keer de array lezen is niet enkel sneller: een toestel dat niet kan segmenteren
        antwoordt soms helemaal niet op losse indexen, terwijl de volledige array (130 ids
        ≈ 520 bytes) wél in één APDU past.
        """
        try:
            whole = self.read_property(ip, 8, device, PROP_OBJECT_LIST, None, timeout)
            items = whole if isinstance(whole, list) else [whole]
            oids = [self._as_oid(x) for x in items]
            oids = [o for o in oids if o is not None]
            if oids:
                return oids[:count or len(oids)]
        except BacnetError:
            pass
        out = []
        for i in range(1, min(count, 400) + 1):
            try:
                oid = self._as_oid(self.read_property(ip, 8, device, PROP_OBJECT_LIST, i, timeout))
            except BacnetError:
                break
            if oid is None:
                continue
            out.append(oid)
        return out

    def objects(self, ip: str, device: int, timeout: float | None = None) -> list[dict]:
        count = self.read_property(ip, 8, device, PROP_OBJECT_LIST, 0, timeout)
        if not isinstance(count, int):
            raise BacnetError("object-list niet leesbaar")
        out = []
        for oid in self._object_list(ip, device, count, timeout):
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
            _ede_row(["AUTHOR_OF_LAST_CHANGE", _ede_clean(author or "FlexPoll")]),
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
