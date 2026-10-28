# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Gezel HVAC+ (https://gezel.be)
"""Module-definities, meetplannen en acties voor de Modbus-testbank."""

from __future__ import annotations

import struct

from modbus_rtu import Bus, ModbusError, ModbusException

# --------------------------------------------------------------------------- meta
TYPES: dict[str, dict] = {
    "em18r": {
        "name": "Siemens EM1.8R",
        "brand": "Siemens",
        "group": "Siemens",
        "kind": "Desigo Essentials",
        "sub": "8 relaissuitgangen",
        "desc": "DO 1-8 · FC1/FC5",
        "icon": "relay",
        "accent": "#E4002B",
        "baud_hint": "9600 8N1",
    },
    "em18d": {
        "name": "Siemens EM1.8D",
        "brand": "Siemens",
        "group": "Siemens",
        "kind": "Desigo Essentials",
        "sub": "8 digitale ingangen",
        "desc": "DI 1-8 · FC2",
        "icon": "input",
        "accent": "#E4002B",
        "baud_hint": "9600 8N1",
    },
    "em18u": {
        "name": "Siemens EM1.8U",
        "brand": "Siemens",
        "group": "Siemens",
        "kind": "Desigo Essentials",
        "sub": "8 universele I/O",
        "desc": "UIO 1-8 · FC3/FC6",
        "icon": "universal",
        "accent": "#E4002B",
        "baud_hint": "9600 8N1",
    },
    "belimo": {
        "name": "Belimo VAV",
        "brand": "Belimo",
        "group": "Belimo",
        "kind": "VAV-Compact MOD",
        "sub": "volumeregelaar",
        "desc": "debiet · stand · override",
        "icon": "vav",
        "accent": "#2271b1",
        "baud_hint": "19200 8E1",
    },
    "grundfos": {
        "name": "Grundfos CIM 200",
        "brand": "Grundfos",
        "group": "Pompen",
        "kind": "E-pump / MAGNA3",
        "sub": "pompregeling",
        "desc": "aan/uit · modus · setpunt",
        "icon": "pump",
        "accent": "#135e96",
        "baud_hint": "9600 8E1",
    },
    "wilo_stratos": {
        "name": "Wilo Stratos MAXO",
        "brand": "Wilo",
        "group": "Pompen",
        "kind": "IF-Module Modbus",
        "sub": "hoogrendementspomp",
        "desc": "aan/uit · regelfunctie · setpunt",
        "icon": "wilo",
        "accent": "#0f766e",
        "baud_hint": "19200 8E1",
    },
    "lg_ub40": {
        "name": "LG UB40",
        "brand": "LG",
        "group": "Warmtepomp",
        "kind": "Therma V R290",
        "sub": "warmtepomp buitenunit",
        "desc": "aanvoer · modus · setpunten",
        "icon": "heatpump",
        "accent": "#b91c1c",
        "baud_hint": "9600 8N1",
    },
    "belimo_ev": {
        "name": "Belimo Energy Valve",
        "brand": "Belimo",
        "group": "Belimo",
        "kind": "Energy Valve V3",
        "sub": "energiemeter + regelaar",
        "desc": "debiet · vermogen · ΔT",
        "icon": "valve_ev",
        "accent": "#2271b1",
        "baud_hint": "38400 8E1",
        "overrides": {0: "Auto", 1: "Dicht", 2: "Open", 3: "Vnom", 4: "Vmax", 5: "Motorstop", 6: "Pnom", 7: "Pmax"},
    },
    "belimo_epiv2": {
        "name": "Belimo 2-weg EPIV",
        "brand": "Belimo",
        "group": "Belimo",
        "kind": "EPIV V4",
        "sub": "drukonafhankelijke regelkraan",
        "desc": "debiet · stand · override",
        "icon": "valve2",
        "accent": "#2271b1",
        "baud_hint": "38400 8E1",
        "overrides": {0: "Auto", 1: "Open", 2: "Dicht", 3: "Minimum debiet", 5: "Maximum debiet", 6: "Nominaal debiet", 10: "Motorstop"},
    },
    "belimo_epiv6": {
        "name": "Belimo 6-weg EPIV",
        "brand": "Belimo",
        "group": "Belimo",
        "kind": "EPIV V4.1",
        "sub": "omschakelklep warm/koud",
        "desc": "debiet · sequentie · override",
        "icon": "valve6",
        "accent": "#2271b1",
        "baud_hint": "38400 8E1",
        "overrides": {0: "Auto", 1: "Seq 1 open", 2: "Seq 2 open", 3: "Dicht", 6: "Max seq 1", 7: "Max seq 2", 8: "Nominaal seq 1", 9: "Nominaal seq 2", 10: "Motorstop"},
    },
    "generic": {
        "name": "Algemene deelnemer",
        "brand": "Algemeen",
        "group": "Algemeen",
        "kind": "vrij te mappen",
        "sub": "eigen registers",
        "desc": "FC1/2/3/4 · schaal · bitvolgorde",
        "icon": "generic",
        "accent": "#5B6B7C",
        "baud_hint": "vrij",
    },
    "carrier_sms": {
        "name": "Carrier AWHP (SMS)",
        "brand": "Carrier",
        "group": "Warmtepomp",
        "kind": "AWHP004 · SMS 275A",
        "sub": "cascade-regeling, 1-4 pompen",
        "desc": "Modbus TCP · unit 1",
        "icon": "heatpump",
        "accent": "#0099D8",
        "transport": "tcp",
        "baud_hint": "TCP 502",
    },
    "clivet": {
        "name": "Clivet WiSAN-YSE",
        "brand": "Clivet",
        "group": "Warmtepomp",
        "kind": "WiSAN-YSE / YME",
        "sub": "lucht-water warmtepomp",
        "desc": "modus · setpunt · watertemp",
        "icon": "heatpump",
        "accent": "#0B7A75",
        "baud_hint": "9600 8N1",
    },
    "clivet_slave": {
        "name": "Clivet WiSAN slave",
        "brand": "Clivet",
        "group": "Warmtepomp",
        "kind": "WiSAN-YSE · slave 1-8",
        "sub": "via de master, enkel lezen",
        "desc": "Tw · Twi · Two per unit",
        "icon": "heatpump",
        "accent": "#3E8E7E",
        "baud_hint": "9600 8N1",
        "readonly": True,
    },
    "daikin": {
        "name": "Daikin EWWT/EWLT-Q",
        "brand": "Daikin",
        "group": "Warmtepomp",
        "kind": "POL468.65 · PROXIMA",
        "sub": "lucht-water, 1 of 2 circuits",
        "desc": "modus · setpunt · verdamper",
        "icon": "heatpump",
        "accent": "#00A0E1",
        "baud_hint": "framing op controller",
    },
}

SIGNAL_TYPES = {
    0: ("Niet gebruikt", "", None),
    1: ("Ni1000", "°C", 0.01),
    2: ("Pt1000", "°C", 0.01),
    3: ("NTC10K", "°C", 0.01),
    4: ("R 10 kΩ", "Ω", 100.0),
    5: ("R 1 kΩ", "Ω", 0.1),
    6: ("Digitaal", "", None),
    7: ("0-20 mA", "mA", 0.001),
    8: ("4-20 mA", "mA", 0.001),
    9: ("0-10 V", "V", 0.001),
    10: ("Uitgang 0-10 V", "V", 0.001),
}

RELIABILITY = {
    0: "OK",
    32762: "n.v.t.",
    32763: "geen sensor",
    32764: "onder bereik",
    32765: "kortsluiting",
    32766: "over bereik",
}

BELIMO_OVERRIDE = {
    0: "Auto",
    1: "Volledig open",
    2: "Volledig sluiten",
    3: "Minimum debiet",
    4: "Mid (Vmid)",
    5: "Maximum debiet",
    6: "Snel open",
    7: "Snel dicht",
}

# Reg 118 — in welke eenheid het toestel absolute debieten toont
BELIMO_UNITS = {0: "m³/s", 1: "m³/h", 2: "l/s", 3: "l/min", 4: "l/h", 5: "gpm", 6: "cfm"}

GRUNDFOS_MODES = {0: "Auto", 4: "Minimum", 6: "Maximum"}

# Wilo Stratos MAXO — Control Function (holding 42)
WILO_CONTROL = {
    1: "Constante snelheid",
    3: "Δp-c (constant)",
    4: "Δp-v (proportioneel)",
    6: "Δp-c = f(T)",
    9: "Constante temperatuur",
    10: "Constant temperatuurverschil",
    37: "Dynamic Adapt (verwarming)",
    38: "Constant debiet (verwarming)",
    80: "Dynamic Adapt (algemeen)",
    81: "Constant debiet (algemeen)",
    140: "PID-regelaar",
}

# LG UB40 — Mode Heating/Cooling (holding 0)
LG_MODES = {0: "Koelen", 3: "Auto", 4: "Verwarmen"}

# Carrier AWHP via SMS 275A — Modbus TCP, unit 1
CARRIER_MODES = {1: "Koelen", 2: "Verwarmen", 3: "Automatisch"}
CARRIER_PROD = {1: "Naar buffervat", 2: "Naar verwarming"}
CARRIER_ALARM = {1: "Normaal", 2: "Deelalarm", 3: "Uitgeschakeld"}
CARRIER_UNIT = {1: "Uit", 2: "In bedrijf", 3: "Stopt", 4: "Wacht"}

# Clivet WiSAN-YSE — 9600 8N1
CLIVET_MODES = {1: "Koelen", 2: "Verwarmen", 4: "DHW", 8: "UIT"}
CLIVET_ODU = {1: "Uit", 2: "Koelen", 3: "Verwarmen", 4: "DHW"}

# Daikin EWWT/EWLT/EWHT-Q (POL468.65 / PROXIMA)
DAIKIN_MODES = {1: "Ice", 2: "Koelen", 3: "Verwarmen", 4: "Test"}
DAIKIN_STATUS = {1: "Uit", 2: "Start", 3: "In bedrijf", 4: "Voorstop", 5: "Service"}

WILO_BUS_CMD = {
    1: "OFF — lokaal geblokkeerd (remote)",
    2: "SET — lockout gestart",
    3: "ACTIVE — lockout loopt",
    4: "RESET — lokaal actief",
    5: "MANUAL — lokaal + remote",
    6: "SET_PRESET",
    7: "ACTIVE_PRESET",
    8: "RESET_PRESET",
    9: "MANUAL_PRESET",
    10: "INVALID",
}

BELIMO_CONTROLMODES = {0: "Positiesturing", 1: "Debietsturing", 2: "Vermogenssturing"}

# ControlMode (reg 00102) — welke regelmethode de pomp volgt.
GRUNDFOS_CONTROL_MODES = {
    0: "Constante snelheid",
    1: "Constante frequentie",
    3: "Constante opvoerhoogte",
    4: "Constante druk",
    5: "Constant drukverschil",
    6: "Proportionele druk",
    7: "Constant debiet",
    8: "Constante temperatuur",
    9: "Constant temperatuurverschil",
    10: "Constant niveau",
    128: "AUTO ADAPT",
    129: "FLOW ADAPT",
    130: "Gesloten lus (sensor)",
    131: "AUTO ADAPT (CP)",
}


class ActionError(Exception):
    pass


BAUD_NAMES = {0: "Auto", 1: "9600", 2: "19200", 3: "38400", 4: "115200"}
FORMAT_NAMES = {0: "8E1", 1: "8O1", 2: "8N1", 3: "8N2"}


def _siemens_comm(bus: Bus, addr: int) -> dict:
    """Lees 4x0310/4x0311: staat de module op Auto of vast? (read-only)"""
    out = {"comm_baud_reg": None, "comm_format_reg": None, "comm_text": "framing onbekend"}
    try:
        regs = bus.read_holding(addr, 309, 2)
    except ModbusError:
        return out
    baud, fmt = regs[0], regs[1]
    out["comm_baud_reg"] = baud
    out["comm_format_reg"] = fmt
    baud_txt = BAUD_NAMES.get(baud, f"code {baud}")
    fmt_txt = FORMAT_NAMES.get(fmt, f"code {fmt}")
    out["comm_text"] = f"{baud_txt} {fmt_txt}" + ("" if baud == 0 else " (vast)")
    return out


# --------------------------------------------------------------------------- helpers
def _u16_list(values: list[int]) -> list[int]:
    return [int(v) for v in values]


def _siemens_serial() -> str | None:
    # EM1.8x heeft geen serienummerregister in het Modbus-beeld.
    return None


# --------------------------------------------------------------------------- readers
def read_em18r(bus: Bus, mod: dict) -> dict:
    coils = bus.read_coils(mod["address"], 0, 8)
    values = {"do": coils}
    values.update(_siemens_comm(bus, mod["address"]))
    return {"serial": _siemens_serial(), "values": values}


def read_em18d(bus: Bus, mod: dict) -> dict:
    di = bus.read_discrete_inputs(mod["address"], 0, 8)
    values = {"di": di}
    values.update(_siemens_comm(bus, mod["address"]))
    return {"serial": _siemens_serial(), "values": values}


def read_em18u(bus: Bus, mod: dict) -> dict:
    raw = bus.read_holding(mod["address"], 0, 16)
    types = bus.read_holding(mod["address"], 99, 8)
    channels = []
    for i in range(8):
        stype = types[i]
        name, unit, scale = SIGNAL_TYPES.get(stype, (f"type {stype}", "", None))
        value = raw[i]
        rel = raw[8 + i]
        if scale is None:
            shown = value if stype == 6 else None
        else:
            shown = round(value * scale, 3)
        channels.append({
            "ch": i + 1,
            "type": stype,
            "type_name": name,
            "unit": unit,
            "raw": value,
            "value": shown,
            "rel": rel,
            "rel_txt": RELIABILITY.get(rel, f"code {rel}"),
        })
    values = {"channels": channels}
    values.update(_siemens_comm(bus, mod["address"]))
    return {"serial": _siemens_serial(), "values": values}


def read_belimo(bus: Bus, mod: dict) -> dict:
    addr = mod["address"]
    regs = bus.read_holding(addr, 0, 9)
    ident = bus.read_holding(addr, 100, 4)
    try:
        qnom = bus.read_holding(addr, 110, 1)[0]
    except ModbusError:
        qnom = None
    try:
        lim = bus.read_holding(addr, 105, 2)   # 4x0106/4x0107 = Vmin/Vmax
    except ModbusError:
        lim = [0, 10000]
    # 4x0109 = bus-failstand, 4x0117 = regelmodus, 4x0118 = eenheid, 4x0119 = setpuntbron.
    # Adres 108 is de bus-failstand; 115/116 zijn leeg (65535) en worden overgeslagen.
    try:
        svc = bus.read_holding(addr, 108, 1) + bus.read_holding(addr, 116, 3)
    except ModbusError:
        svc = [None, None, None, None]
    bus_fail, control_mode, unit_sel, sp_source = (list(svc) + [None] * 4)[:4]
    bus_fail = None if bus_fail == 65535 else bus_fail
    control_mode = None if control_mode == 65535 else control_mode
    unit_sel = None if unit_sel == 65535 else unit_sel
    sp_source = None if sp_source == 65535 else sp_source

    serial = f"{(ident[0] << 32) | (ident[1] << 16) | ident[2]:012X}"
    fw = ident[3]
    setpoint = round(regs[0] / 100.0, 2)
    vmin = round(lim[0] / 100.0, 2)
    vmax = round(lim[1] / 100.0, 2)
    # Reg 1 is GEEN absoluut debiet maar een percentage dat het toestel tussen Vmin en
    # Vmax schaalt: 0 % = Vmin, 100 % = Vmax. Zonder die vertaling leest "50 %" bij
    # Vmin 13 / Vmax 20 als de helft van qnom, terwijl het toestel 16,6 % vraagt.
    sp_target = round(vmin + (setpoint / 100.0) * (vmax - vmin), 2) if vmax > vmin else setpoint
    return {
        "serial": serial,
        "values": {
            "setpoint": setpoint,
            "override": regs[1],
            "override_txt": BELIMO_OVERRIDE.get(regs[1], f"code {regs[1]}"),
            "actuator_type": regs[3],
            "position": round(regs[4] / 100.0, 2),
            "angle": regs[5],
            "flow_rel": round(regs[6] / 100.0, 2),
            "flow": regs[7],
            "sensor_mv": regs[8],
            "qnom": qnom,
            "vmin": vmin,
            "vmax": vmax,
            "sp_target": sp_target,
            "sp_flow": round(qnom * sp_target / 100.0, 1) if qnom else None,
            "control_mode": control_mode,
            "control_mode_txt": BELIMO_CONTROLMODES.get(control_mode, ""),
            "unit_sel": unit_sel,
            "unit_txt": BELIMO_UNITS.get(unit_sel, ""),
            "sp_source": sp_source,
            "sp_source_txt": {0: "Analoog", 1: "Bus"}.get(sp_source, ""),
            "bus_fail": bus_fail,
            "bus_fail_txt": {0: "Laatste setpunt", 1: "Snel dicht", 2: "Snel open",
                             3: "Mid-stand (Vmid)"}.get(bus_fail, ""),
            "firmware": f"{fw // 100}.{fw % 100:02d}",
            # Vmid is géén Modbus-register bij de VAV-Compact (map stopt op 4x0119).
            # Het staat als vaste parameter in het toestel (ZTH EU / PC-Tool) en wordt
            # enkel gebruikt door override 4 en bus-failstand 3 — daarom tonen we het
            # als 'geparametreerd', niet als meetwaarde.
            "vmid": "geparametreerd",
        },
    }


def _grundfos_base(bus: Bus, mod: dict, rt: dict) -> int:
    if "gf_base" in rt:
        return rt["gf_base"]
    last = None
    for base in (100, 101):
        try:
            probe = bus.read_holding(mod["address"], base, 4)
        except ModbusError as exc:
            last = exc
            continue
        if probe[3] <= 10000 and probe[1] <= 140 and probe[2] in (0, 4, 6):
            rt["gf_base"] = base
            return base
    raise ModbusError(
        "CIM 200 registerbeeld niet herkend"
        + (f" ({last})" if last else "")
    )


def read_grundfos(bus: Bus, mod: dict) -> dict:
    rt = mod.setdefault("_rt", {})
    base = _grundfos_base(bus, mod, rt)
    ctl = bus.read_holding(mod["address"], base, 4)      # 00101..00104
    status = bus.read_holding(mod["address"], 200, 8)    # 00201..00208
    data = bus.read_holding(mod["address"], 300, 12)     # 00301..00312
    try:
        temps = bus.read_holding(mod["address"], 317, 6)  # 00318..00323
    except ModbusError:
        temps = [0] * 6
    try:
        user_sp = bus.read_holding(mod["address"], 337, 1)[0]
    except ModbusError:
        user_sp = ctl[3]
    st = status[0]
    # 0,01 K — Kelvin, niet Celsius: eerst /100, dan 273,15 eraf.
    t_elec = round(temps[3] / 100.0 - 273.15, 1) if temps[3] else None      # 00321
    t_liquid = round(temps[4] / 100.0 - 273.15, 1) if temps[4] else None    # 00322
    return {
        "serial": None,
        "values": {
            "on": bool(st >> 9 & 1),
            "remote": bool(st >> 8 & 1),
            "remote_req": bool(ctl[0] & 0x0001),
            "alarm": bool(st >> 10 & 1),
            "warning": bool(st >> 11 & 1),
            "alarm_code": status[4],
            "warning_code": status[5],
            # 003xx-blok. Register X staat in de telegram op X-1, dus
            # read(300, n) levert 00301.. — niet nog eens opschuiven.
            "head": round(data[0] / 1000.0, 3),           # 00301 Head, 0.001 bar
            "flow": round(data[1] / 10.0, 2),             # 00302 VolumeFlow, 0.1 m³/h
            "rel_perf": round(data[2] / 100.0, 1),        # 00303 RelativePerformance, 0.01 %
            "rpm": data[3],                               # 00304 Speed, 1 rpm
            "freq": round(data[4] / 10.0, 1),             # 00305 Frequency, 0.1 Hz
            "actual_setpoint": round(data[7] / 100.0, 1), # 00308 ActualSetpoint, 0.01 %
            "current": round(data[8] / 10.0, 1),          # 00309 MotorCurrent, 0.1 A
            "temp_electronics": t_elec,
            "temp_liquid": t_liquid,
            "setpoint": round(user_sp / 100.0, 1),        # 00338 UserSetpoint, 0.01 %
            "controlmode": ctl[1],
            "controlmode_actual": status[2],
            "controlmode_txt": GRUNDFOS_CONTROL_MODES.get(status[2], GRUNDFOS_CONTROL_MODES.get(ctl[1], f"code {ctl[1]}")),
            "mode": ctl[2],
            "mode_txt": GRUNDFOS_MODES.get(ctl[2], f"code {ctl[2]}"),
            "base": base,
        },
    }




def _u32(lo: int, hi: int) -> int:
    return (hi << 16) | lo


def _s16(value: int) -> int:
    return value - 0x10000 if value >= 0x8000 else value


def _write_reg(bus: Bus, addr: int, register: int, value: int) -> None:
    """Schrijf één register en val terug op FC16 als de slave FC6 weigert.

    Clivet/Carel-controllers antwoorden op FC6 (write single register) met
    exception 1 "illegale functie" en accepteren alleen FC16 (write multiple),
    ook voor één register. Andere fouten worden gewoon doorgegooid.
    """
    try:
        bus.write_register(addr, register, value)
    except ModbusException as exc:
        if exc.code != 1:
            raise
        bus.write_registers(addr, register, [value])


def _belimo_ident(words: list[int]) -> tuple[str, str]:
    serial = f"{(words[0] << 32) | (words[1] << 16) | words[2]:012X}"
    return serial, f"{words[3] // 100}.{words[3] % 100:02d}"


def read_belimo_ev(bus: Bus, mod: dict) -> dict:
    """Belimo Energy Valve V3: 0..27 in één read, dan identificatie en regelmode."""
    r = bus.read_holding(mod["address"], 0, 28)
    ident = bus.read_holding(mod["address"], 100, 4)
    cm = bus.read_holding(mod["address"], 140, 1)[0]
    try:
        lim = bus.read_holding(mod["address"], 105, 2)   # V'min / V'max [%]
    except ModbusError:
        lim = [0, 10000]
    try:
        vnom = bus.read_holding(mod["address"], 110, 1)[0]   # [l/s], alleen lezen
    except ModbusError:
        vnom = None
    serial, fw = _belimo_ident(ident)
    overrides = TYPES["belimo_ev"]["overrides"]
    ov = r[1]
    return {
        "serial": serial,
        "values": {
            "setpoint": round(r[0] / 100.0, 2),
            "override": ov,
            "override_txt": overrides.get(ov, f"code {ov}"),
            "actuator_type": r[3],
            "position": round(r[4] / 100.0, 2),
            "flow_rel": round(r[6] / 100.0, 2),
            "flow": round(_u32(r[9], r[10]) * 0.001 * 3.6, 2),
            "t1": round(_s16(r[16]) / 10.0, 1),
            "t2": round(_s16(r[18]) / 10.0, 1),
            "dt": round(_s16(r[20]) / 10.0, 1),
            "power": round(_u32(r[26], r[27]) * 0.001, 2),
            "power_rel": r[23],
            "vmin": round(lim[0] / 100.0, 2),
            "vmax": round(lim[1] / 100.0, 2),
            "vnom_ls": round(vnom * 0.01, 2) if vnom is not None else None,
            "vnom": round(vnom * 0.036, 2) if vnom is not None else None,   # l/s (0,01) -> m³/h
            "controlmode": cm,
            "controlmode_txt": BELIMO_CONTROLMODES.get(cm, f"code {cm}"),
            "firmware": fw,
        },
    }


def read_belimo_epiv2(bus: Bus, mod: dict) -> dict:
    """Belimo 2-weg EPIV V4."""
    r = bus.read_holding(mod["address"], 0, 19)
    ident = bus.read_holding(mod["address"], 100, 4)
    cm = bus.read_holding(mod["address"], 116, 3)
    serial, fw = _belimo_ident(ident)
    overrides = TYPES["belimo_epiv2"]["overrides"]
    ov = r[1]
    return {
        "serial": serial,
        "values": {
            "setpoint": round(r[0] / 100.0, 2),
            "override": ov,
            "override_txt": overrides.get(ov, f"code {ov}"),
            "actuator_type": r[3],
            "position": round(r[4] / 100.0, 2),
            "flow_rel": round(r[6] / 100.0, 2),
            "flow": round(r[7] * 0.01 * 3.6, 2),
            "analog_sp": round(r[11] / 100.0, 2),
            "controlmode": cm[0],
            "controlmode_txt": BELIMO_CONTROLMODES.get(cm[0], f"code {cm[0]}"),
            "unit": cm[1],
            "setpoint_source": cm[2],
            "firmware": fw,
        },
    }


def read_belimo_epiv6(bus: Bus, mod: dict) -> dict:
    """Belimo 6-weg EPIV V4.1 — twee sequenties, actieve sequentie in reg 16."""
    r = bus.read_holding(mod["address"], 0, 17)
    ident = bus.read_holding(mod["address"], 100, 19)   # 100..118
    try:
        lim = bus.read_holding(mod["address"], 207, 10)  # 207..216
    except ModbusError:
        lim = None
    serial, fw = _belimo_ident(ident[:4])
    overrides = TYPES["belimo_epiv6"]["overrides"]
    ov = r[1]
    cm = ident[16]
    return {
        "serial": serial,
        "values": {
            "setpoint": round(r[0] / 100.0, 2),
            "override": ov,
            "override_txt": overrides.get(ov, f"code {ov}"),
            "actuator_type": r[3],
            "position": round(r[4] / 100.0, 2),
            "flow_rel": round(r[6] / 100.0, 2),
            "flow": round(_u32(r[9], r[10]) / 1000.0, 2),
            "sequence": r[16],
            "vmax1": round(ident[5] / 100.0, 1),
            "vmax2": round(ident[6] / 100.0, 1),
            "vmax1_ls": round(lim[1] / 100.0, 2) if lim else None,
            "vmax2_ls": round(lim[6] / 100.0, 2) if lim else None,
            "vmax1_pct": round(lim[0] / 100.0, 1) if lim else None,
            "vmax2_pct": round(lim[5] / 100.0, 1) if lim else None,
            "controlmode": cm,
            "controlmode_txt": BELIMO_CONTROLMODES.get(cm, f"code {cm}"),
            "firmware": fw,
        },
    }



# --------------------------------------------------------------------------- warmtepompen
def _f32(hi: int, lo: int) -> float:
    v = struct.unpack(">f", struct.pack(">HH", hi, lo))[0]
    if v != v or abs(v) > 1e7:
        v = struct.unpack(">f", struct.pack(">HH", lo, hi))[0]
    return v


def _f32r(hi: int, lo: int):
    v = _f32(hi, lo)
    if v != v or abs(v) > 1e6:
        return None
    return round(v, 2)


def _f32_words(value: float) -> list[int]:
    return list(struct.unpack(">HH", struct.pack(">f", value)))


GEN_TYPES = ("u16", "s16", "u32", "s32", "f32", "bit")
GEN_FC = (1, 2, 3, 4)


def _swap_bytes(value: int) -> int:
    return ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)


def _decode_point(regs: list[int] | None, bits: int | None, ptype: str,
                  order: str, swap: bool):
    if ptype == "bit":
        return 1 if bits else 0
    words = [_swap_bytes(w) if swap else w for w in regs or []]
    if ptype in ("u16", "s16"):
        if not words:
            return None
        raw = words[0]
        return _s16(raw) if ptype == "s16" else raw
    if len(words) < 2:
        return None
    hi, lo = (words[0], words[1]) if order != "BA" else (words[1], words[0])
    raw = (hi << 16) | lo
    if ptype == "f32":
        return struct.unpack(">f", struct.pack(">I", raw))[0]
    if ptype == "s32":
        return raw - 0x100000000 if raw >= 0x80000000 else raw
    return raw


def _encode_point(value: float, ptype: str, order: str, swap: bool) -> list[int]:
    if ptype in ("u16", "s16"):
        raw = int(round(value)) & 0xFFFF
        return [_swap_bytes(raw) if swap else raw]
    if ptype == "f32":
        raw = struct.unpack(">I", struct.pack(">f", float(value)))[0]
    else:
        raw = int(round(value)) & 0xFFFFFFFF
    hi, lo = (raw >> 16) & 0xFFFF, raw & 0xFFFF
    if swap:
        hi, lo = _swap_bytes(hi), _swap_bytes(lo)
    return [hi, lo] if order != "BA" else [lo, hi]


def read_generic(bus: Bus, mod: dict) -> dict:
    """Vrij gemapte punten: per punt één leesactie, gecodeerd volgens de config."""
    a = mod["address"]
    out = []
    for p in mod.get("points") or []:
        fc = int(p.get("fc") or 3)
        ptype = p.get("type") or "u16"
        order = p.get("order") or "AB"
        swap = bool(p.get("swap"))
        addr = int(p.get("addr") or 0)
        rec = {"id": p.get("id"), "name": p.get("name") or f"FC{fc} {addr}",
               "unit": p.get("unit") or "", "ok": False, "error": None, "value": None}
        try:
            if fc in (1, 2):
                bits = (bus.read_coils(a, addr, 1)[0] if fc == 1
                        else bus.read_discrete_inputs(a, addr, 1)[0])
                raw = 1 if bits else 0
            else:
                qty = 2 if ptype in ("u32", "s32", "f32") else 1
                regs = (bus.read_holding(a, addr, qty) if fc == 3
                        else bus.read_input(a, addr, qty))
                raw = _decode_point(regs, None, ptype, order, swap)
            if raw is None:
                raise ValueError("geen waarde")
            scale = float(p.get("scale", 1) or 0)
            offset = float(p.get("offset", 0) or 0)
            value = raw * scale + offset
            rec["raw"] = raw
            rec["value"] = round(value, 3) if isinstance(value, float) else value
            rec["ok"] = True
        except ModbusError as exc:
            rec["error"] = str(exc)
        except Exception as exc:                      # noqa: BLE001
            rec["error"] = str(exc)
        out.append(rec)
    if out and not any(r["ok"] for r in out):
        # Alle punten faalden: dan is de verbinding zelf stuk, niet "online met fouten".
        raise ModbusError(out[0].get("error") or "geen enkel punt leesbaar")
    return {"serial": None, "values": {"points": out, "count": len(out)}}


def read_carrier(bus: Bus, mod: dict) -> dict:
    """Carrier AWHP004 via SMS Option 275A — Modbus TCP, unit 1."""
    a = mod["address"]
    ir = bus.read_input(a, 0, 16)          # 300001..300016
    hr = bus.read_holding(a, 0, 8)         # 400001..400008
    t = bus.read_input(a, 100, 10)         # 300101..300110 (FLOAT, 2 regs per waarde)
    tk = bus.read_input(a, 142, 4)         # 300143..300146
    cmd = hr[0]
    return {
        "serial": None,
        "values": {
            "on": cmd == 2,
            "command": cmd,
            "on_txt": {1: "UIT", 2: "AAN", 3: "Volgens schema"}.get(cmd, f"code {cmd}"),
            "mode_cmd": hr[7],
            "mode_cmd_txt": CARRIER_MODES.get(hr[7], f"code {hr[7]}"),
            "prod_mode": ir[0],
            "prod_mode_txt": CARRIER_PROD.get(ir[0], f"code {ir[0]}"),
            "running": ir[1],
            "hp1_status": ir[8],
            "hp1_alarm": ir[14],
            "hp1_alarm_txt": CARRIER_ALARM.get(ir[14], f"code {ir[14]}"),
            "hp1_unit": ir[15],
            "hp1_unit_txt": CARRIER_UNIT.get(ir[15], f"code {ir[15]}"),
            "lwt": _f32r(t[0], t[1]),
            "ewt": _f32r(t[2], t[3]),
            "oat": _f32r(t[4], t[5]),
            "dhw_tank": _f32r(tk[0], tk[1]),
            "buffer": _f32r(tk[2], tk[3]),
        },
    }


def _clivet_status(bus: Bus, a: int, off: int = 0) -> dict:
    """Lees het Clivet-statusblok 239..250 (+offset) en de foutcode.

    `off` is 100 × het interne adres: de master bevraagt de interne bus, dus
    slave 1 verschijnt op 244+100 = 344, slave 2 op 444, enzovoort.
    """
    st = bus.read_holding(a, 239 + off, 12)      # 239..250 · Twi 244 · Two 245 · Tw 246
    try:
        err = bus.read_holding(a, 272 + off, 1)[0]
    except ModbusError:
        err = None                               # slave-blok heeft soms geen foutregister
    return {
        "ts": st[0],
        "mode": st[1],
        "mode_txt": CLIVET_ODU.get(st[1], f"code {st[1]}"),
        "odu_mode": st[1],
        "odu_txt": CLIVET_ODU.get(st[1], f"code {st[1]}"),
        "silent": st[2],
        "t5s": st[3],
        "twi": st[5],
        "two": st[6],
        "tw": st[7],
        "t4": st[8],
        "comp_hz": st[9],
        "comp_a": st[10],
        "fan1": st[11],
        "error": err,
    }


def read_clivet(bus: Bus, mod: dict) -> dict:
    """Clivet WiSAN-YSE — 9600 8N1, regs 0-based."""
    a = mod["address"]
    ctl = bus.read_holding(a, 0, 5)        # 0 mode · 1 Tws1 · 4 DHW
    values = {
        "setpoint": ctl[1],
        "dhw_setpoint": ctl[4],
        **_clivet_status(bus, a, 0),
    }
    values["on"] = values["mode"] != 8
    return {"serial": None, "values": values}


def read_clivet_slave(bus: Bus, mod: dict) -> dict:
    """Clivet slave-unit — enkel lezen, via het adres van de master.

    Alle schrijf- en vrijgaveacties blijven op de master; deze tegel toont
    alleen de meetwaarden van de gekozen unit (1..8).
    """
    unit = min(8, max(1, int(mod.get("unit") or 1)))
    values = _clivet_status(bus, mod["address"], unit * 100)
    values["unit"] = unit
    return {"serial": None, "values": values}


def read_daikin(bus: Bus, mod: dict) -> dict:
    """Daikin EWWT/EWLT/EWHT-Q (POL468.65) — 4xxxx, PDU = regnr - 1."""
    a = mod["address"]
    r = bus.read_holding(a, 0, 38)         # 4x0001..4x0038
    st = bus.read_holding(a, 298, 7)       # 4x0299..4x0305
    return {
        "serial": None,
        "values": {
            "source": r[0],
            "source_txt": "Lokaal" if r[0] == 1 else "Netwerk",
            "enabled": r[1],
            "on": bool(r[1]) and r[14] in (2, 3),
            "alarm": bool(r[4]),
            "thermo": r[7],
            "mode": r[10],
            "mode_txt": DAIKIN_MODES.get(r[10], f"code {r[10]}"),
            "active_sp": round(_s16(r[11]) / 10.0, 1),
            "capacity": r[12],
            "status": r[14],
            "status_txt": DAIKIN_STATUS.get(r[14], f"code {r[14]}"),
            "ewt": round(_s16(r[15]) / 10.0, 1),
            "lwt": round(_s16(r[16]) / 10.0, 1),
            "warn": r[30],
            "problem": r[31],
            "fault": r[32],
            "cool_sp": round(_s16(r[34]) / 10.0, 1),
            "heat_sp": round(_s16(r[36]) / 10.0, 1),
            "circuit": st[1],
            "pump": st[6],
        },
    }


def read_wilo(bus: Bus, mod: dict) -> dict:
    """Wilo Stratos MAXO (IF-Module Modbus)."""
    sp = bus.read_holding(mod["address"], 1, 1)[0]        # duty point, schaal 0,5 %
    cmd = bus.read_holding(mod["address"], 40, 3)         # 40 pump command, 42 control function
    ir = bus.read_input(mod["address"], 1, 10)            # 1..10: druk, debiet, vermogen, speed, temp...
    st = bus.read_input(mod["address"], 35, 5)            # 35..39: service, error, status
    try:
        bct = bus.read_holding(mod["address"], 300, 1)[0]  # Bus Command Timer: lokaal/remote
    except ModbusError:
        bct = None
    cm = cmd[2]
    return {
        "serial": None,
        "values": {
            "setpoint": round(sp * 0.5, 1),
            "on": bool(cmd[0] & 0x01),
            "bus_cmd": bct,
            "bus_cmd_txt": WILO_BUS_CMD.get(bct, "onbekend" if bct is None else f"code {bct}"),
            "command": cmd[0],
            "controlmode": cm,
            "controlmode_txt": WILO_CONTROL.get(cm, f"code {cm}"),
            "controlmode_actual": ir[9],
            "head": round(ir[0] * 10 / 100.0, 2),
            "flow": round(ir[1] * 0.1, 2),
            "energy": ir[2],
            "power": ir[3],
            "current": round(ir[5] * 0.1, 2),
            "speed": ir[6],
            "temp": round(ir[7] * 0.1 - 273.15, 1),
            "error": st[2],
            "error_type": st[1],
            "service": st[0],
            "status": st[3],
        },
    }


def read_lg_ub40(bus: Bus, mod: dict) -> dict:
    """LG UB40 (Therma V R29) — officiële map: FC1/FC2/FC3/FC4."""
    coils = bus.read_coils(mod["address"], 0, 7)
    di = bus.read_discrete_inputs(mod["address"], 0, 17)
    hold = bus.read_holding(mod["address"], 0, 10)
    plim = bus.read_holding(mod["address"], 24, 1)[0]
    inp = bus.read_input(mod["address"], 0, 14)
    mode = hold[0]
    return {
        "serial": None,
        "values": {
            "on": bool(coils[0]),
            "dhw_enabled": bool(coils[1]),
            "silent": bool(coils[2]),
            "mode": mode,
            "mode_txt": LG_MODES.get(mode, f"code {mode}"),
            "target": round(_s16(hold[2]) / 10.0, 1),
            "dhw_target": round(_s16(hold[8]) / 10.0, 1),
            "power_limit": round(plim / 10.0, 1),
            "error": inp[0],
            "cycle": inp[1],
            "t_in": round(_s16(inp[2]) / 10.0, 1),
            "t_out": round(_s16(inp[3]) / 10.0, 1),
            "t_dhw": round(_s16(inp[5]) / 10.0, 1),
            "t_outdoor": round(_s16(inp[12]) / 10.0, 1),
            "flow": round(inp[8] / 10.0, 1),
            "pressure": round(inp[13] / 10.0, 2),
            "compressor": bool(di[3]),
            "pump": bool(di[1]),
            "defrost": bool(di[4]),
            "dhw_active": bool(di[5]),
            "cooling": bool(di[8]),
        },
    }


READERS = {
    "em18r": read_em18r,
    "em18d": read_em18d,
    "em18u": read_em18u,
    "belimo": read_belimo,
    "grundfos": read_grundfos,
    "wilo_stratos": read_wilo,
    "lg_ub40": read_lg_ub40,
    "belimo_ev": read_belimo_ev,
    "belimo_epiv2": read_belimo_epiv2,
    "belimo_epiv6": read_belimo_epiv6,
    "generic": read_generic,
    "carrier_sms": read_carrier,
    "clivet": read_clivet,
    "clivet_slave": read_clivet_slave,
    "daikin": read_daikin,
}


def read_module(bus: Bus, mod: dict) -> dict:
    reader = READERS.get(mod["type"])
    if reader is None:
        raise ModbusError(f"onbekend moduletype '{mod['type']}'")
    return reader(bus, mod)


# --------------------------------------------------------------------------- actions
def perform(bus: Bus, mod: dict, op: str, data: dict) -> str:
    """Voer een actie uit. Geeft een korte melding terug voor de buslog."""
    mtype = mod["type"]
    addr = mod["address"]

    if mtype in ("em18u", "em18r", "em18d") and op in ("baud_auto", "factory_reset"):
        if op == "baud_auto":
            bus.write_register(addr, 309, 0)    # 4x0310 = Auto
            bus.write_register(addr, 310, 0)    # 4x0311 = 1-8-E-1
            bus.write_register(addr, 314, 1)    # 4x0315 = Load -> herstart
            return "framing -> Auto (module herstart, signaaltypes blijven bewaard)"
        bus.write_register(addr, 319, 0xCAFE)   # 4x0320 = factory reset
        bus.write_register(addr, 314, 1)        # 4x0315 = Load -> herstart
        return "factory reset (module herstart, terminalconfiguratie gewist)"

    if mtype == "generic":
        if op != "write_point":
            raise ActionError(f"actie '{op}' niet ondersteund voor algemene deelnemer")
        pid = str(data.get("pid") or "")
        point = next((p for p in (mod.get("points") or []) if str(p.get("id")) == pid), None)
        if point is None:
            raise ActionError("punt niet gevonden")
        if not point.get("rw"):
            raise ActionError("punt is alleen lezen")
        fc = int(point.get("fc") or 3)
        ptype = point.get("type") or "u16"
        scale = float(point.get("scale", 1) or 0)
        offset = float(point.get("offset", 0) or 0)
        try:
            raw_val = (float(data.get("value", 0)) - offset) / (scale or 1)
        except (TypeError, ValueError):
            raise ActionError("ongeldige waarde") from None
        addr_pt = int(point.get("addr") or 0)
        if fc in (1, 5):
            bus.write_coil(addr, addr_pt, bool(int(raw_val)))
            return f"{point.get('name') or pid} -> {'AAN' if raw_val else 'UIT'}"
        regs = _encode_point(raw_val, ptype, point.get("order") or "AB", bool(point.get("swap")))
        if len(regs) == 1:
            bus.write_register(addr, addr_pt, regs[0])
        else:
            bus.write_registers(addr, addr_pt, regs)
        return f"{point.get('name') or pid} -> {data.get('value')}"

    if mtype == "carrier_sms":
        if op == "set_onoff":
            on = bool(int(data.get("value", 0)))
            bus.write_register(addr, 0, 2 if on else 1)      # 400001
            return f"SMS -> {'AAN' if on else 'UIT'}"
        if op == "set_mode":
            val = int(data.get("value", 0))
            if val not in CARRIER_MODES:
                raise ActionError("ongeldige bedrijfsmodus")
            bus.write_register(addr, 7, val)                  # 400008
            return f"regeling -> {CARRIER_MODES[val]}"
        if op == "set_dhw":
            temp = float(data.get("value", -999))
            if not 25 <= temp <= 75:
                raise ActionError("DHW-setpunt moet tussen 25 en 75 °C liggen")
            bus.write_registers(addr, 126, _f32_words(temp))   # 400127 (FLOAT)
            return f"DHW-setpunt -> {temp:.1f} °C"
        raise ActionError(f"actie '{op}' niet ondersteund voor Carrier SMS")

    if mtype == "clivet":
        if op == "set_mode":
            val = int(data.get("value", 0))
            if val not in CLIVET_MODES:
                raise ActionError("ongeldige bedrijfsmodus")
            _write_reg(bus, addr, 0, val)
            return f"modus -> {CLIVET_MODES[val]}"
        if op == "set_setpoint":
            temp = float(data.get("value", -999))
            if not 5 <= temp <= 65:
                raise ActionError("setpunt moet tussen 5 en 65 °C liggen")
            _write_reg(bus, addr, 1, int(round(temp)))
            return f"setpunt -> {temp:.1f} °C"
        if op == "set_dhw":
            temp = float(data.get("value", -999))
            if not 20 <= temp <= 60:
                raise ActionError("DHW-setpunt moet tussen 20 en 60 °C liggen")
            _write_reg(bus, addr, 4, int(round(temp)))
            return f"DHW-setpunt -> {temp:.1f} °C"
        if op == "clear_errors":
            _write_reg(bus, addr, 6, 1)
            return "lock-errors gewist"
        raise ActionError(f"actie '{op}' niet ondersteund voor Clivet WiSAN")

    if mtype == "daikin":
        if op == "set_onoff":
            on = bool(int(data.get("value", 0)))
            bus.write_register(addr, 8, 1 if on else 0)        # 4x0009
            return f"unit -> {'AAN' if on else 'UIT'}"
        if op == "set_mode":
            val = int(data.get("value", -1))
            if val not in (0, 1):
                raise ActionError("modus moet 0 (koelen) of 1 (verwarmen) zijn")
            bus.write_register(addr, 33, val)                  # 4x0034
            return f"regeling -> {'Verwarmen' if val else 'Koelen'}"
        if op == "set_setpoint":
            temp = float(data.get("value", -999))
            if not -15 <= temp <= 60:
                raise ActionError("setpunt buiten bereik (-15…60 °C)")
            mode = bus.read_holding(addr, 10, 1)[0]
            reg = 36 if mode == 3 else 34                      # 4x0037 warm · 4x0035 koud
            bus.write_register(addr, reg, int(round(temp * 10)))
            return f"{'warm' if reg == 36 else 'koud'}-setpunt -> {temp:.1f} °C"
        if op == "clear_alarms":
            bus.write_register(addr, 9, 1)                     # 4x0010
            return "alarmen gewist"
        raise ActionError(f"actie '{op}' niet ondersteund voor Daikin")

    if op == "set_vminmax" and mtype in ("belimo", "belimo_ev"):
        vmin = float(data.get("vmin", -1))
        vmax = float(data.get("vmax", -1))
        if not (0 <= vmin <= 100 and 0 <= vmax <= 100):
            raise ActionError("Vmin/Vmax moeten tussen 0 en 100 % liggen")
        if vmin > vmax:
            raise ActionError("Vmin mag niet groter zijn dan Vmax")
        bus.write_registers(addr, 105, [int(round(vmin * 100)), int(round(vmax * 100))])
        return f"Vmin {vmin:g} % / Vmax {vmax:g} %"

    if op == "set_vmax_seq" and mtype == "belimo_epiv6":
        s1 = float(data.get("seq1", -1))
        s2 = float(data.get("seq2", -1))
        if not (0 <= s1 <= 97.2 and 0 <= s2 <= 97.2):
            raise ActionError("V'max moet tussen 0 en 97,2 l/s liggen")
        bus.write_register(addr, 208, int(round(s1 * 100)))
        bus.write_register(addr, 213, int(round(s2 * 100)))
        return f"V'max seq1 {s1:g} l/s · seq2 {s2:g} l/s"

    if mtype == "em18r":
        if op != "toggle_do":
            raise ActionError(f"actie '{op}' niet ondersteund voor EM1.8R")
        ch = int(data.get("ch", 0))
        if not 1 <= ch <= 8:
            raise ActionError("DO-kanaal moet 1..8 zijn")
        value = bool(int(data.get("value", 1)))
        bus.write_coil(addr, ch - 1, value)
        return f"DO{ch} -> {'AAN' if value else 'UIT'}"

    if mtype == "em18u":
        if op == "set_type":
            ch = int(data.get("ch", 0))
            stype = int(data.get("value", -1))
            if not 1 <= ch <= 8:
                raise ActionError("kanaal moet 1..8 zijn")
            if stype not in SIGNAL_TYPES:
                raise ActionError("ongeldig signaaltype")
            bus.write_register(addr, 98 + ch, stype)
            return f"X{ch} signaaltype -> {SIGNAL_TYPES[stype][0]}"
        if op == "set_ao":
            ch = int(data.get("ch", 0))
            volts = float(data.get("value", -1))
            if not 1 <= ch <= 8:
                raise ActionError("kanaal moet 1..8 zijn")
            if not 0 <= volts <= 10:
                raise ActionError("uitgangswaarde moet tussen 0 en 10 V liggen")
            bus.write_register(addr, ch - 1, int(round(volts * 1000)))
            return f"X{ch} uitgang -> {volts:.2f} V"
        raise ActionError(f"actie '{op}' niet ondersteund voor EM1.8U")

    if mtype in ("belimo", "belimo_ev", "belimo_epiv2", "belimo_epiv6"):
        overrides = TYPES[mtype].get("overrides") or BELIMO_OVERRIDE
        if op == "set_override":
            val = int(data.get("value", -1))
            if val not in overrides:
                raise ActionError("ongeldige override-stand")
            bus.write_register(addr, 1, val)
            return f"override -> {overrides[val]}"
        if op == "set_setpoint":
            pct = float(data.get("value", -1))
            if not 0 <= pct <= 100:
                raise ActionError("setpunt moet tussen 0 en 100 % liggen")
            bus.write_register(addr, 0, int(round(pct * 100)))
            if mtype == "belimo":
                # het toestel schaalt dit percentage tussen Vmin en Vmax
                try:
                    lo, hi = bus.read_holding(addr, 105, 2)
                    tgt = lo / 100.0 + (pct / 100.0) * ((hi - lo) / 100.0)
                    return f"setpunt -> {pct:.1f} % = {tgt:.1f} % van Vnom"
                except ModbusError:
                    pass
            return f"setpunt -> {pct:.1f} %"
        raise ActionError(f"actie '{op}' niet ondersteund voor {TYPES[mtype]['name']}")

    if mtype == "wilo_stratos":
        if op == "set_onoff":
            on = bool(int(data.get("value", 0)))
            cmd = bus.read_holding(addr, 40, 1)[0]
            cmd = (cmd | 0x01) if on else (cmd & ~0x01)
            bus.write_register(addr, 40, cmd)
            return f"pomp -> {'AAN' if on else 'UIT'}"
        if op == "set_controlmode":
            val = int(data.get("value", -1))
            if val not in WILO_CONTROL:
                raise ActionError("ongeldige regelfunctie")
            bus.write_register(addr, 42, val)
            return f"regelfunctie -> {WILO_CONTROL[val]}"
        if op == "set_setpoint":
            pct = float(data.get("value", -1))
            if not 0 <= pct <= 100:
                raise ActionError("setpunt moet tussen 0 en 100 % liggen")
            bus.write_register(addr, 1, int(round(pct / 0.5)))
            return f"setpunt -> {pct:.1f} %"
        if op == "set_remote":
            remote = bool(int(data.get("value", 0)))
            bus.write_register(addr, 300, 1 if remote else 4)   # Bus Command Timer
            return f"aansturing -> {'REMOTE (bus)' if remote else 'LOCAL (pomp)'}"
        raise ActionError(f"actie '{op}' niet ondersteund voor Wilo Stratos MAXO")

    if mtype == "lg_ub40":
        if op == "set_onoff":
            on = bool(int(data.get("value", 0)))
            bus.write_coil(addr, 0, on)
            return f"warmtepomp -> {'AAN' if on else 'UIT'}"
        if op == "set_mode":
            val = int(data.get("value", -1))
            if val not in LG_MODES:
                raise ActionError("ongeldige modus")
            bus.write_register(addr, 0, val)
            return f"modus -> {LG_MODES[val]}"
        if op == "set_setpoint":
            temp = float(data.get("value", -999))
            if not 5 <= temp <= 65:
                raise ActionError("aanvoertemperatuur moet tussen 5 en 65 °C liggen")
            bus.write_register(addr, 2, int(round(temp * 10)))
            return f"aanvoersetpunt -> {temp:.1f} °C"
        if op == "set_dhw":
            temp = float(data.get("value", -999))
            if not 30 <= temp <= 80:
                raise ActionError("DHW-setpunt moet tussen 30 en 80 °C liggen")
            bus.write_register(addr, 8, int(round(temp * 10)))
            return f"DHW-setpunt -> {temp:.1f} °C"
        raise ActionError(f"actie '{op}' niet ondersteund voor LG UB40")

    if mtype == "grundfos":
        rt = mod.setdefault("_rt", {})
        base = _grundfos_base(bus, mod, rt)
        if op == "set_onoff":
            on = bool(int(data.get("value", 0)))
            ctl = bus.read_holding(addr, base, 1)[0]
            ctl = (ctl | 0x0001) & ~0x0002          # remote aan, oude on/off wissen
            if on:
                ctl |= 0x0002
            bus.write_register(addr, base, ctl)
            return f"pomp -> {'AAN' if on else 'UIT'} (remote)"
        if op == "set_controlmode":
            val = int(data.get("value", -1))
            if val not in GRUNDFOS_CONTROL_MODES:
                raise ActionError("ongeldige regelmethode")
            bus.write_register(addr, base + 1, val)
            return f"regelmethode -> {GRUNDFOS_CONTROL_MODES[val]}"
        if op == "set_mode":
            val = int(data.get("value", -1))
            if val not in GRUNDFOS_MODES:
                raise ActionError("ongeldige werkingsmodus")
            bus.write_register(addr, base + 2, val)
            return f"werkingsmodus -> {GRUNDFOS_MODES[val]}"
        if op == "set_setpoint":
            pct = float(data.get("value", -1))
            if not 0 <= pct <= 100:
                raise ActionError("setpunt moet tussen 0 en 100 % liggen")
            bus.write_register(addr, base + 3, int(round(pct * 100)))
            return f"setpunt -> {pct:.1f} %"
        if op == "set_remote":
            remote = bool(int(data.get("value", 0)))
            ctl = bus.read_holding(addr, base, 1)[0]
            ctl = (ctl | 0x0001) if remote else (ctl & ~0x0001)
            bus.write_register(addr, base, ctl)
            return f"aansturing -> {'REMOTE (Modbus)' if remote else 'LOCAL (pomp/DI)'}"
        raise ActionError(f"actie '{op}' niet ondersteund voor Grundfos CIM 200")

    raise ActionError(f"actie '{op}' niet ondersteund")
