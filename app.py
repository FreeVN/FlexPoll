#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
"""FlexPoll — grafische testbank voor Modbus RTU, Modbus TCP/IP en BACnet/IP (Siemens EM1.8x, Belimo VAV,
Grundfos CIM 200. Draait zonder externe web-framework dependencies.

    python3 app.py --host 0.0.0.0 --port 8099
    MODBUS_SIM=1 python3 app.py --port 8099     # demo-bus zonder hardware
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import devices
from devices import ActionError, TYPES
from modbus_rtu import Bus, BusDown, ModbusError, ModbusException, ModbusTimeout


def _read_version() -> str:
    """Versie uit het VERSION-bestand naast dit script — één bron van waarheid
    voor UI, `--version` en de git-tag. Ontbreekt het bestand (bv. ingebedde
    kopie), dan blijft de app bruikbaar maar zegt ze het eerlijk."""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(here, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip() or "0.0.0-dev"
    except OSError:
        return "0.0.0-dev"


APP_VERSION = _read_version()

REPO_URL = "https://github.com/FreeVN/FlexPoll"
RELEASES_URL = f"{REPO_URL}/releases"
DOCS_URL = "https://freevn.github.io/FlexPoll/"


def _version_tuple(v: str) -> tuple[int, ...]:
    """'1.2.10' -> (1, 2, 10); rommel levert (0,) op zodat vergelijken nooit klapt."""
    parts = []
    for chunk in str(v or "").lstrip("v").split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts) or (0,)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _data_dir() -> str:
    """Waar de configuratie leeft.

    - In de repo of een service-installatie: `data/` naast de code (gedrag van
      oudsher, de systemd-unit rekent erop).
    - In een ingepakte build (PyInstaller): naast de code bestaat die map niet
      schrijfbaar of ze verdwijnt bij de volgende start, dus gaan we naar de
      gebruiker zijn gegevensmap. Overschrijfbaar met FLEXPOLL_DATA.
    """
    env = os.environ.get("FLEXPOLL_DATA")
    if env:
        return env
    if getattr(sys, "frozen", False):
        if os.name == "nt":
            root = os.environ.get("APPDATA") or os.path.expanduser("~")
        elif sys.platform == "darwin":
            root = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
        else:
            root = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
        return os.path.join(root, "FlexPoll")
    return os.path.join(BASE_DIR, "data")


DATA_DIR = _data_dir()
STATIC_DIR = os.path.join(BASE_DIR, "static")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

DEFAULT_BUS = {
    "port": "",
    "baud": 9600,
    "parity": "N",
    "stopbits": 1,
    "timeout": 0.5,
    "interval": 10,
    # run = pollen, pause = bus blijft open maar er wordt niet gelezen,
    # stop = ook de poort wordt vrijgegeven (voor een ander programma).
    "mode": "run",
    "debug": False,
}

BAUD_CHOICES = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]


# --------------------------------------------------------------------------- helpers
def now() -> float:
    return time.time()


def atomic_write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def udev_info(dev: str) -> dict:
    try:
        out = subprocess.run(
            ["udevadm", "info", "-q", "property", "-n", dev],
            capture_output=True, text=True, timeout=2,
        ).stdout
    except Exception:
        return {}
    info = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k] = v
    return info


def _linux_ports() -> list[dict]:
    """Linux: by-id-links (stabiel over reboots) + rauwe ttyUSB/ttyACM."""
    ports: list[dict] = []
    seen: set[str] = set()
    for link in sorted(glob.glob("/dev/serial/by-id/*")):
        real = os.path.realpath(link)
        info = udev_info(real)
        model = info.get("ID_MODEL", "") or os.path.basename(real)
        model = model.replace("_", " ")
        serial = info.get("ID_SERIAL_SHORT", "")
        label = model + (f" · {serial}" if serial else "")
        ports.append({
            "path": link,
            "real": real,
            "label": label,
            "detail": os.path.basename(link),
            "present": os.path.exists(real),
        })
        seen.add(real)
    for dev in sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")):
        if dev in seen:
            continue
        ports.append({
            "path": dev,
            "real": dev,
            "label": os.path.basename(dev),
            "detail": "seriële poort",
            "present": True,
        })
    return ports


def _comports() -> list[dict]:
    """Windows (en als vangnet elk ander OS): pyserial's eigen enumeratie.

    Windows levert `COM3` + een beschrijving uit de driver ("USB-SERIAL CH340").
    Zonder deze tak is de poortlijst op Windows altijd leeg: `glob("/dev/...")`
    bestaat daar niet. `present` is hier altijd True — een verdwenen COM-poort
    komt niet in de lijst, en een oude config houdt zijn pad via de UI.
    """
    out: list[dict] = []
    seen: set[str] = set()
    try:
        from serial.tools import list_ports as comports
    except ImportError:          # pyserial ontbreekt: geen poorten, geen crash
        return out
    for info in comports.comports():
        path = (info.device or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        desc = (info.description or "").strip()
        if desc.lower() in ("n/a", "none"):
            desc = ""
        if not desc or desc.lower() == path.lower():
            desc = os.path.basename(path)
        # Op Windows is `real` hetzelfde als het pad; de UI toont "label — real",
        # dus het label blijft de beschrijving (anders staat COM3 er twee keer).
        out.append({
            "path": path,
            "real": path,
            "label": desc,
            "detail": (info.hwid or "").strip() or "seriële poort",
            "present": True,
        })
    return out


def list_ports() -> list[dict]:
    """Alle seriële poorten van dit OS, in de vorm die de UI verwacht."""
    if sys.platform.startswith("linux"):
        ports = _linux_ports()
        if ports:
            return ports
        # Geen by-id en geen ttyUSB/ttyACM (bv. een exotische driver): pyserial
        # als vangnet, maar zonder de ttyS0..31-ruis van de moederbordpoorten.
        return [p for p in _comports()
                if "ttyS" not in os.path.basename(p["path"])]
    return _comports()


# --------------------------------------------------------------------------- app
GEN_TYPES = ("u16", "s16", "u32", "s32", "f32", "bit")


def _norm_points(raw) -> list[dict]:
    out = []
    for p in (raw or [])[:40]:
        if not isinstance(p, dict):
            continue
        fc = int(p.get("fc") or 3)
        if fc not in (1, 2, 3, 4):
            fc = 3
        ptype = str(p.get("type") or ("bit" if fc in (1, 2) else "u16"))
        if ptype not in GEN_TYPES:
            ptype = "u16"
        try:
            scale = float(p.get("scale", 1))
        except (TypeError, ValueError):
            scale = 1.0
        try:
            offset = float(p.get("offset", 0))
        except (TypeError, ValueError):
            offset = 0.0
        out.append({
            "id": str(p.get("id") or uuid.uuid4().hex[:6]),
            "name": str(p.get("name") or "")[:32],
            "fc": fc,
            "addr": max(0, min(65535, int(p.get("addr") or 0))),
            "type": ptype,
            "order": "BA" if p.get("order") == "BA" else "AB",
            "swap": bool(p.get("swap")),
            "scale": scale if scale else 1.0,
            "offset": offset,
            "unit": str(p.get("unit") or "")[:8],
            "rw": bool(p.get("rw")),
            "ctrl": "button" if p.get("ctrl") == "button" else "input",
        })
    return out


class App:
    def __init__(self, simulate: bool = False):
        self._bn = None
        self.lock = threading.RLock()
        self.simulate = simulate
        self.wake = threading.Event()
        self.log: deque = deque(maxlen=400)
        self.states: dict[str, dict] = {}
        self.rt: dict[str, dict] = {}
        self.bus: Bus | None = None
        self._tcp: dict = {}
        self.bus_status: dict = {"open": False, "error": None, "last_ok": None}
        self.last_poll: float | None = None
        self.next_poll: float | None = None
        self.polling = False
        self.scanning = False
        self.scan_progress = None
        self._ports_cache = (0.0, [])
        self._update_cache: tuple[float, dict] | None = None
        self.config = self._load_config()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ config
    def _default_config(self) -> dict:
        ports = list_ports()
        preferred = ""
        for p in ports:
            # FTDI eerst: dat is de adapter die op de bank hangt (VID 0403).
            # Op Windows staat "FTDI" niet in het pad of de beschrijving, maar
            # wel in de hwid — vandaar alle velden samen.
            blob = " ".join(str(p.get(k, "")) for k in ("path", "label", "detail")).upper()
            if "FTDI" in blob or "0403:" in blob:
                preferred = p["path"]
                break
        if not preferred and ports:
            preferred = ports[0]["path"]
        cfg = {
            "bus": {**DEFAULT_BUS, "port": preferred},
            "modules": [],
        }
        if preferred:
            cfg["modules"].append({
                "id": uuid.uuid4().hex[:8],
                "type": "em18u",
                "address": 3,
                "label": "",
            })
        return cfg

    def _load_config(self) -> dict:
        if not os.path.exists(CONFIG_PATH):
            cfg = self._default_config()
            atomic_write(CONFIG_PATH, json.dumps(cfg, indent=2, ensure_ascii=False))
            return cfg
        try:
            with open(CONFIG_PATH, encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception as exc:
            self.add_log("error", f"config onleesbaar ({exc}) — standaardconfig gebruikt")
            return self._default_config()
        return self._normalize(raw)

    def _normalize(self, raw: dict) -> dict:
        bus = {**DEFAULT_BUS, **(raw.get("bus") or {})}
        bus["baud"] = int(bus.get("baud") or 9600)
        if bus["baud"] not in BAUD_CHOICES:
            bus["baud"] = 9600
        bus["parity"] = bus.get("parity") if bus.get("parity") in ("N", "E", "O") else "N"
        bus["stopbits"] = 2 if int(bus.get("stopbits") or 1) == 2 else 1
        bus["timeout"] = min(3.0, max(0.1, float(bus.get("timeout") or 0.5)))
        bus["interval"] = min(60, max(1, int(bus.get("interval") or 10)))
        bus["mode"] = bus.get("mode") if bus.get("mode") in ("run", "pause", "stop") else "run"
        bus["debug"] = bool(bus.get("debug"))
        modules = []
        used_ids = set()
        for mod in (raw.get("modules") or [])[:32]:
            mtype = mod.get("type")
            if mtype not in TYPES:
                continue
            try:
                address = int(mod.get("address", 1))
            except (TypeError, ValueError):
                address = 1
            address = min(247, max(1, address))
            mid = str(mod.get("id") or uuid.uuid4().hex[:8])
            if mid in used_ids:
                mid = uuid.uuid4().hex[:8]
            used_ids.add(mid)
            entry = {
                "id": mid,
                "type": mtype,
                "address": address,
                "label": str(mod.get("label") or "")[:40],
                "release": bool(mod.get("release")),
                "transport": "tcp" if (mod.get("transport") == "tcp" or TYPES[mtype].get("transport") == "tcp") else "rtu",
            }
            if entry["transport"] == "tcp":
                entry["ip"] = str(mod.get("ip") or "").strip()[:64]
                entry["port"] = min(65535, max(1, int(mod.get("port") or 502)))
            if mtype == "generic":
                entry["points"] = _norm_points(mod.get("points"))
            if mtype == "clivet_slave":
                try:
                    unit = int(mod.get("unit") or 1)
                except (TypeError, ValueError):
                    unit = 1
                entry["unit"] = min(8, max(1, unit))
            modules.append(entry)
        return {"bus": bus, "modules": modules}

    def save_config(self) -> None:
        atomic_write(CONFIG_PATH, json.dumps(self.config, indent=2, ensure_ascii=False))

    # ------------------------------------------------------------------ log
    def add_log(self, level: str, msg: str) -> None:
        self.log.appendleft({"ts": now(), "level": level, "msg": msg})
        if len(self.log) > 400:
            self.log.pop()

    # ------------------------------------------------------------------ bus
    def _bus_kwargs(self) -> dict:
        b = self.config["bus"]
        return dict(
            port=b["port"], baud=b["baud"], parity=b["parity"],
            stopbits=b["stopbits"], timeout=b["timeout"],
        )

    def _desired_bus_signature(self) -> tuple:
        b = self.config["bus"]
        return (b["port"], b["baud"], b["parity"], b["stopbits"], b["timeout"])

    def ensure_bus(self) -> Bus:
        """Open (of heropen) de seriële poort volgens de config. Caller holds lock."""
        want = self._desired_bus_signature()
        if self.simulate:
            if self.bus is None:
                from sim import SimBus
                self.bus = SimBus()  # type: ignore[assignment]
                self._instrument(self.bus)
                self.bus_status = {"open": True, "error": None, "last_ok": now()}
                self.add_log("info", "Gesimuleerde bus gestart (demo-modus)")
            return self.bus
        if self.bus is not None and self.bus.is_open() and getattr(self.bus, "_sig", None) == want:
            self.bus.tracer = self._on_frame if self.config["bus"].get("debug") else None
            return self.bus
        if self.bus is not None:
            try:
                self.bus.close()
            except Exception:
                pass
            self.bus = None
        kwargs = self._bus_kwargs()
        if not kwargs["port"]:
            raise BusDown("geen seriële poort gekozen")
        if not os.path.exists(kwargs["port"]):
            raise BusDown(f"poort {kwargs['port']} bestaat niet")
        bus = Bus(**kwargs)
        bus.open()  # type: ignore[attr-defined]
        bus._sig = want  # type: ignore[attr-defined]
        bus.tracer = self._on_frame if self.config["bus"].get("debug") else None
        self.bus = bus
        self.bus_status["open"] = True
        self.bus_status["error"] = None
        self.bus_status["last_ok"] = now()
        self.add_log("info", f"Poort open: {kwargs['port']} @ {kwargs['baud']} 8{kwargs['parity']}{kwargs['stopbits']}")
        return bus

    def ensure_tcp_bus(self, mod: dict):
        host = (mod.get("ip") or "").strip()
        if not host:
            raise ModbusError("geen IP-adres ingesteld")
        port = int(mod.get("port") or 502)
        unit = int(mod.get("address") or 1)
        key = (host, port, unit)
        with self.lock:
            bus = self._tcp.get(key)
            if bus is not None and bus.is_open():
                return bus
        from modbus_tcp import TcpBus
        bus = TcpBus(host, port, unit=unit, timeout=self.config["bus"]["timeout"])
        bus.open()
        with self.lock:
            self._tcp[key] = bus
        self.add_log("info", f"Modbus TCP verbonden: {host}:{port} (unit {unit})")
        return bus

    def bus_for(self, mod: dict):
        if mod.get("transport") == "tcp":
            return self.ensure_tcp_bus(mod)
        return self.ensure_bus()

    def close_bus(self) -> None:
        for bus in list(self._tcp.values()):
            try:
                bus.close()
            except Exception:
                pass
        self._tcp.clear()
        with self.lock:
            if self.bus is not None:
                try:
                    self.bus.close()
                except Exception:
                    pass
                self.bus = None
            self.bus_status["open"] = False

    def _instrument(self, bus) -> None:
        """Frame-logging voor een bus die het zelf niet doet (SimBus)."""
        specs = {
            "read_coils": 1, "read_discrete_inputs": 2, "read_holding": 3, "read_input": 4,
            "write_coil": 5, "write_register": 6, "write_registers": 16,
        }
        for name, fc in specs.items():
            orig = getattr(bus, name, None)
            if orig is None or getattr(orig, "_traced", False):
                continue

            def make(orig=orig, fc=fc, name=name):
                def wrapper(*args, **kwargs):
                    t0 = time.perf_counter()
                    try:
                        res = orig(*args, **kwargs)
                    except ModbusError as exc:
                        self._emit(fc, name, args, t0, exc)
                        raise
                    self._emit(fc, name, args, t0, None, res)
                    return res
                wrapper._traced = True  # type: ignore[attr-defined]
                return wrapper

            setattr(bus, name, make())

    def _emit(self, fc: int, name: str, args: tuple, t0: float,
              err: Exception | None, res=None) -> None:
        if not self.config["bus"].get("debug"):
            return
        start, qty, val = 0, 1, None
        if name == "write_registers" and len(args) >= 3:
            start, qty = int(args[1]), len(args[2])
        elif name in ("write_coil", "write_register") and len(args) >= 3:
            start, val = int(args[1]), int(args[2])
        elif len(args) >= 3:
            start, qty = int(args[1]), int(args[2])
        self._on_frame({
            "addr": int(args[0]) if args else 0, "fc": fc, "start": start, "qty": qty,
            "ms": int((time.perf_counter() - t0) * 1000),
            "err": str(err) if err else None, "val": val,
        })

    # ------------------------------------------------------------------ trace
    FC_INFO = {
        1: ("FC1", "0x"), 2: ("FC2", "1x"), 3: ("FC3", "4x"), 4: ("FC4", "3x"),
        5: ("FC5", "0x"), 6: ("FC6", "4x"), 15: ("FC15", "0x"), 16: ("FC16", "4x"),
    }

    def _on_frame(self, ev: dict) -> None:
        """Debugregel per Modbus-frame: FC, registertype en -bereik."""
        name, prefix = self.FC_INFO.get(ev["fc"], (f"FC{ev['fc']}", "?"))
        first = ev["start"] + 1
        last = ev["start"] + ev["qty"]
        span = f"{prefix}{first:04d}" + (f"–{prefix}{last:04d} ({ev['qty']})" if ev["qty"] > 1 else "")
        if ev["fc"] in (5, 6, 15, 16) and ev.get("val") is not None:
            span += f" = {ev['val']}"
        msg = f"Adres {ev['addr']} · {name} {span} · {ev['ms']} ms"
        if ev.get("err"):
            msg += f" → {ev['err']}"
        self.add_log("frame", msg)

    # ------------------------------------------------------------------ polling
    def poll_once(self) -> None:
        with self.lock:
            if self.polling:
                return
            self.polling = True
        try:
            with self.lock:
                mods = list(self.config["modules"])
            rtu = [m for m in mods if m.get("transport") != "tcp" and not m.get("release")]
            serial_bus = None
            if rtu:
                try:
                    serial_bus = self.ensure_bus()
                except Exception as exc:
                    with self.lock:
                        self.bus_status["open"] = False
                        self.bus_status["error"] = str(exc)
                        for mod in rtu:
                            self.states[mod["id"]] = {
                                "ok": False, "error": str(exc), "ts": now(), "ms": 0,
                            }
                    self.add_log("error", f"Bus: {exc}")
            time.sleep(0.02)
            debug = bool(self.config["bus"].get("debug"))
            for mod in mods:
                if mod.get("release"):
                    continue          # framing vrijgegeven: niet pollen, anders lockt de module weer
                if mod.get("transport") == "tcp":
                    try:
                        bus = self.ensure_tcp_bus(mod)
                    except Exception as exc:
                        with self.lock:
                            self.states[mod["id"]] = {
                                "ok": False, "error": str(exc), "ts": now(), "ms": 0,
                            }
                        continue
                else:
                    bus = serial_bus
                    if bus is None:
                        continue
                bus.tracer = self._on_frame if debug else None
                self._poll_module(bus, mod)
            with self.lock:
                self.last_poll = now()
                self.next_poll = self.last_poll + self.config["bus"]["interval"]
        finally:
            with self.lock:
                self.polling = False

    def _poll_module(self, bus, mod: dict) -> None:
        started = time.perf_counter()
        try:
            with self.lock:
                rt = self.rt.setdefault(mod["id"], {})
                target = {**mod, "_rt": rt}
                try:
                    result = devices.read_module(bus, target)
                except ModbusTimeout:
                    # Clivet/Carel missen de eerste frame die volgt op andermans
                    # verkeer; één retry na een korte stilte volstaat. Pas als
                    # ook die faalt, melden we het toestel als offline.
                    time.sleep(0.05)
                    result = devices.read_module(bus, target)
            elapsed = int((time.perf_counter() - started) * 1000)
            with self.lock:
                old = self.states.get(mod["id"]) or {}
                self.states[mod["id"]] = {
                    "ok": True,
                    "error": None,
                    "ts": now(),
                    "ms": elapsed,
                    "serial": result.get("serial"),
                    "values": result.get("values", {}),
                }
                self.bus_status["last_ok"] = now()
                self.bus_status["error"] = None
                if not old.get("ok"):
                    self.add_log("ok", f"Adres {mod['address']} ({TYPES[mod['type']]['name']}) antwoordt — {elapsed} ms")
        except ModbusException as exc:
            self._module_failed(mod, f"Adres {mod['address']}: {exc}", str(exc))
        except ModbusTimeout as exc:
            self._module_failed(mod, f"Adres {mod['address']}: geen antwoord", str(exc))
        except BusDown as exc:
            self._module_failed(mod, f"Bus weg: {exc}", str(exc))
            with self.lock:
                self.bus_status["open"] = False
                self.bus_status["error"] = str(exc)
        except ModbusError as exc:
            self._module_failed(mod, f"Adres {mod['address']}: {exc}", str(exc))
        except Exception as exc:  # pragma: no cover - defensief
            self._module_failed(mod, f"Adres {mod['address']}: {exc}", str(exc))

    def _module_failed(self, mod: dict, msg: str, err: str) -> None:
        with self.lock:
            old = self.states.get(mod["id"]) or {}
            self.states[mod["id"]] = {"ok": False, "error": err, "ts": now(), "ms": 0}
            if old.get("error") != err:
                self.add_log("warn", msg)

    def _poll_loop(self) -> None:
        # eerste ronde meteen
        while True:
            mode = self.config["bus"].get("mode", "run")
            if mode == "run":
                try:
                    self.poll_once()
                except Exception as exc:  # pragma: no cover
                    self.add_log("error", f"Poll-lus: {exc}")
                wait = self.config["bus"]["interval"]
            else:
                # Gestopt: de poort vrijgeven zodat bv. de leverancier zijn tool
                # kan aansluiten. Gepauzeerd: bus blijft open, enkel niet lezen.
                if mode == "stop" and self.bus is not None:
                    self.close_bus()
                # Kort wachten zodat play/pause meteen reageert.
                wait = 1.0
            self.wake.wait(wait)
            self.wake.clear()

    # ------------------------------------------------------------------ state
    def ports(self) -> list[dict]:
        ts, cached = self._ports_cache
        if now() - ts < 15:
            return cached
        ports = list_ports()
        self._ports_cache = (now(), ports)
        return ports

    # ------------------------------------------------------------------ BACnet
    def bacnet_client(self):
        import bacnet

        with self.lock:
            if self._bn is None:
                self._bn = bacnet.BacnetClient(timeout=2.0, delay=0.02)
            return self._bn

    def bn_whois(self, subnet: str) -> list[dict]:
        import bacnet

        client = self.bacnet_client()
        nets = [subnet] if subnet else bacnet.local_broadcasts()
        return client.whois(timeout=3.0, subnets=nets)

    def bn_points(self, ip: str, device: int, limit: int = 80) -> dict:
        import bacnet

        client = self.bacnet_client()
        objs = client.objects(ip, device)
        rows = []
        for o in objs[:limit]:
            row = {"type": o["type"], "inst": o["inst"], "abbr": o["abbr"],
                   "name": "", "value": None, "unit": "", "ok": False, "error": None}
            try:
                name = client.read_property(ip, o["type"], o["inst"], bacnet.PROP_OBJECT_NAME) or ""
                # Legacy-toestellen leveren de naam met een leidende NUL
                row["name"] = str(name).replace("\x00", "").strip()
            except bacnet.BacnetError:
                pass
            if o["type"] not in bacnet.PV_OBJECT_TYPES:
                # device, file, group, trend-log, vendor-types: geen present-value.
                # Een error opvragen zou hier een fout tonen die er geen is.
                row["ok"] = True
            else:
                try:
                    value = client.read_property(ip, o["type"], o["inst"], bacnet.PROP_PRESENT_VALUE)
                    row["value"] = round(value, 3) if isinstance(value, float) else value
                    row["ok"] = True
                except bacnet.BacnetError as exc:
                    row["error"] = str(exc)
            if o["type"] in (0, 1, 2):
                try:
                    unit = client.read_property(ip, o["type"], o["inst"], bacnet.PROP_UNITS)
                    if isinstance(unit, (int, float)) and not isinstance(unit, bool):
                        name = bacnet.UNITS.get(int(unit), f"unit-{int(unit)}")
                        row["unit"] = bacnet.UNIT_SYMBOLS.get(name, name)
                except bacnet.BacnetError:
                    pass
            rows.append(row)
        return {"ip": ip, "device": device, "points": rows}

    def bn_write(self, ip: str, obj_type: int, instance: int, value):
        import bacnet

        client = self.bacnet_client()
        client.write_property(ip, int(obj_type), int(instance), bacnet.PROP_PRESENT_VALUE, value)
        return client.read_property(ip, int(obj_type), int(instance), bacnet.PROP_PRESENT_VALUE)

    def bn_ede(self, ip: str, device: int) -> list[dict]:
        return self.bacnet_client().ede(ip, device)

    def bn_ede_package(self, ip: str, device: int, project: str = "") -> dict:
        return self.bacnet_client().ede_package(ip, device, project=project)

    # ------------------------------------------------------------------ polling-besturing
    def set_poll(self, body: dict) -> dict:
        """Interval en modus (run/pause/stop) van de poll-lus aanpassen."""
        with self.lock:
            bus = self.config["bus"]
            if body.get("interval") is not None:
                try:
                    value = int(body["interval"])
                except (TypeError, ValueError):
                    raise ActionError("interval moet een getal zijn") from None
                bus["interval"] = max(1, min(60, value))
            mode = body.get("mode")
            if mode is not None:
                if mode not in ("run", "pause", "stop"):
                    raise ActionError("mode moet run, pause of stop zijn")
                bus["mode"] = mode
                if mode == "stop":
                    self.close_bus()
                if mode == "run":
                    self.last_poll = None       # anders lijkt de meting meteen oud
        self.save_config()
        self.wake.set()                         # poll-lus meteen wakker maken
        return self.state()

    def check_update(self) -> dict:
        """Laatste release op GitHub opvragen (5 s time-out, 1 uur cache).

        De app werkt volledig offline; dit is enkel de knop in de footer en mag
        dus nooit blokkeren of een exception naar de UI laten lekken.
        """
        cached = self._update_cache
        if cached and time.time() - cached[0] < 3600:
            return cached[1]
        out: dict = {"current": APP_VERSION, "latest": None, "newer": False,
                     "url": RELEASES_URL, "ok": False, "error": None}
        try:
            import json as _json
            import urllib.request

            req = urllib.request.Request(
                "https://api.github.com/repos/FreeVN/FlexPoll/releases/latest",
                headers={"User-Agent": f"FlexPoll/{APP_VERSION}",
                         "Accept": "application/vnd.github+json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json.load(resp)
            latest = str(data.get("tag_name") or "").lstrip("v")
            if latest:
                out["latest"] = latest
                out["url"] = data.get("html_url") or out["url"]
                out["newer"] = _version_tuple(latest) > _version_tuple(APP_VERSION)
                out["ok"] = True
        except Exception as exc:                        # noqa: BLE001
            out["error"] = str(exc)[:140]
        self._update_cache = (time.time(), out)
        return out

    def state(self) -> dict:
        with self.lock:
            modules = []
            for mod in self.config["modules"]:
                modules.append({
                    **mod,
                    "type_meta": TYPES[mod["type"]],
                    "state": self.states.get(mod["id"]) or {"ok": False, "error": "nog niet gelezen", "ts": None},
                })
            b = self.config["bus"]
            return {
                "bus": {
                    **b,
                    "open": self.bus_status["open"],
                    "error": self.bus_status["error"],
                    "last_ok": self.bus_status["last_ok"],
                    "ports": self.ports(),
                    "baud_choices": BAUD_CHOICES,
                },
                "modules": modules,
                "last_poll": self.last_poll,
                "next_poll": self.next_poll,
                "polling": self.polling,
                "scanning": self.scanning,
                "scan_progress": getattr(self, "scan_progress", None),
                "now": now(),
                "log": list(self.log)[:60],
                "simulate": self.simulate,
                "version": APP_VERSION,
            }

    # ------------------------------------------------------------------ actions
    def apply_config(self, payload: dict) -> dict:
        new = self._normalize(payload)
        with self.lock:
            old_sig = self._desired_bus_signature()
            self.config = new
            self.save_config()
            valid_ids = {m["id"] for m in new["modules"]}
            for mid in list(self.states):
                if mid not in valid_ids:
                    self.states.pop(mid, None)
                    self.rt.pop(mid, None)
            for mid in list(self.rt):
                if mid not in valid_ids:
                    self.rt.pop(mid, None)
        if new_bus_changed(old_sig, new):
            self.close_bus()
            self.add_log("info", "Businstellingen gewijzigd — poort wordt heropend")
        self.wake.set()
        return self.state()

    def action(self, module_id: str, op: str, data: dict) -> dict:
        with self.lock:
            mod = next((m for m in self.config["modules"] if m["id"] == module_id), None)
            if mod is None:
                raise ActionError("module niet gevonden")
            bus = self.bus_for(mod)
            rt = self.rt.setdefault(module_id, {})
            target = {**mod, "_rt": rt}
            if op == "resume":
                mod["release"] = False
                self.save_config()
                self.add_log("info", f"Adres {mod['address']}: terug in polling (framing wordt weer vastgezet)")
            else:
                try:
                    note = devices.perform(bus, target, op, data)
                except ModbusError as exc:
                    self.add_log("error", f"Actie mislukt (adres {mod['address']}): {exc}")
                    raise
                self.add_log("action", f"Adres {mod['address']} ({TYPES[mod['type']]['name']}): {note}")
                if op == "baud_auto":
                    # niet verder pollen: het eerste frame zou de module weer vastzetten
                    mod["release"] = True
                    self.save_config()
        if mod.get("release"):
            with self.lock:
                self.states[module_id] = {
                    "ok": False, "ts": now(), "ms": 0, "released": True,
                    "error": "framing vrijgegeven — module wordt niet gepolld",
                }
                return dict(self.states[module_id])
        # meteen teruglezen zodat de UI de nieuwe toestand toont
        self._poll_module(bus, mod)
        with self.lock:
            return self.states.get(module_id, {})

    def scan(self, start: int, end: int) -> list[dict]:
        start = max(1, min(247, int(start)))
        end = max(start, min(247, int(end)))
        found: list[dict] = []
        with self.lock:
            self.scanning = True
            self.scan_progress = {"current": start, "end": end}
        try:
            with self.lock:
                bus = self.ensure_bus()
                old_timeout = getattr(bus, "timeout", 0.5)
                bus.timeout = 0.06
                try:
                    if getattr(bus, "serial", None) is not None:
                        bus.serial.timeout = 0.06
                except Exception:
                    pass
            try:
                for addr in range(start, end + 1):
                    # lock per adres: de UI/poller blijft tussendoor leefbaar
                    with self.lock:
                        self.scan_progress = {"current": addr, "end": end}
                        hit = self._probe_address(bus, addr)
                    if hit:
                        found.append(hit)
            finally:
                with self.lock:
                    bus.timeout = old_timeout
                    try:
                        if getattr(bus, "serial", None) is not None:
                            bus.serial.timeout = old_timeout
                    except Exception:
                        pass
            self.add_log("info", f"Scan {start}-{end}: {len(found)} module(s) gevonden")
        finally:
            with self.lock:
                self.scanning = False
        self.scan_progress = None
        return found

    FRAMINGS = [
        (9600, "N", 1), (9600, "E", 1), (19200, "E", 1), (19200, "N", 1),
        (38400, "E", 1), (115200, "E", 1), (4800, "E", 1),
    ]

    def framing_scan(self, addr: int) -> dict:
        """Probeer alle gangbare baud/pariteit/stopbits op één adres."""
        addr = max(1, min(247, int(addr)))
        port = self.config["bus"]["port"]
        hits: list[dict] = []
        with self.lock:
            self.close_bus()
            for baud, parity, stop in self.FRAMINGS:
                probe = Bus(port=port, baud=baud, parity=parity, stopbits=stop, timeout=0.25)
                answered = False
                try:
                    probe.open()
                    probe.read_holding(addr, 0, 1)
                    answered = True
                except ModbusException:
                    answered = True          # slave antwoordt, adres/register bestaat niet
                except Exception:
                    answered = False
                finally:
                    try:
                        probe.close()
                    except Exception:
                        pass
                if answered:
                    hits.append({"baud": baud, "parity": parity, "stopbits": stop})
            if hits:
                best = hits[0]
                self.config["bus"].update({
                    "baud": best["baud"], "parity": best["parity"], "stopbits": best["stopbits"],
                })
                self.save_config()
                self.add_log("info", f"Framing gevonden voor adres {addr}: "
                                     f"{best['baud']} 8{best['parity']}{best['stopbits']}")
            else:
                self.add_log("warn", f"Geen framing gevonden voor adres {addr} "
                                     f"({len(self.FRAMINGS)} combinaties geprobeerd)")
        self.wake.set()
        return {"address": addr, "found": hits, "applied": hits[0] if hits else None}

    def _probe_address(self, bus, addr: int) -> dict | None:
        """Herken het moduletype aan de hand van unieke registerblokken.

        Eerst één snelle liveness-check (FC3 op 0..1), anders kost elk leeg
        adres zeven timeouts en duurt een scan van 32 adressen 20 seconden.
        """
        alive = False
        try:
            bus.read_holding(addr, 0, 2)
            alive = True
        except ModbusException:
            alive = True
        except ModbusError:
            alive = False

        if not alive:
            # EM1.8R / EM1.8D antwoorden alleen op FC1 / FC2
            try:
                bus.read_coils(addr, 0, 8)
                return self._hit(addr, "em18r", confidence=90,
                                 reason="antwoordt op FC1 (coils), niet op FC3")
            except ModbusError:
                pass
            try:
                bus.read_discrete_inputs(addr, 0, 8)
                return self._hit(addr, "em18d", confidence=90,
                                 reason="antwoordt op FC2 (discrete inputs), niet op FC3")
            except ModbusError:
                pass
            return None

        # 1) Grundfos CIM 200 — pumpstatus 00201..00205 bestaat alleen daar
        for base in (100, 101):
            try:
                bus.read_holding(addr, 200, 5)
                ctl = bus.read_holding(addr, base, 4)
            except ModbusError:
                continue
            if ctl[1] <= 140 and ctl[2] in (0, 4, 6) and ctl[3] <= 10000:
                return self._hit(addr, "grundfos", base=base, confidence=97,
                                 reason="pompstatus-blok 200–205 antwoordt + plausibel control-blok")

        # 2) Siemens EM1.8U — 4x0100..4x0107 zijn SignalType-codes (0..10)
        try:
            types = bus.read_holding(addr, 99, 8)
            if all(v <= 10 for v in types):
                configured = any(v > 0 for v in types)
                return self._hit(addr, "em18u", confidence=96 if configured else 82,
                                 reason="SignalType-blok 99–106, alle waarden ≤ 10"
                                        + ("" if configured else " (nog geen enkel kanaal geconfigureerd)"))
        except ModbusError:
            pass

        # 3) Belimo — actuator type (reg 3) bepaalt de variant
        regs = None
        try:
            regs = bus.read_holding(addr, 0, 9)
        except ModbusError:
            pass
        if regs is not None:
            try:
                qnom = bus.read_holding(addr, 110, 1)[0]
            except ModbusError:
                qnom = 0
            if regs[3] in (1, 2, 3, 4, 5) or qnom:
                if regs[3] == 4:
                    return self._hit(addr, "belimo_ev", confidence=97, reason="actuatortype reg 3 = 4 (Energy Valve)")
                if regs[3] == 5:
                    return self._hit(addr, "belimo_epiv6", confidence=97, reason="actuatortype reg 3 = 5 (6-weg EPIV)")
                return self._hit(addr, "belimo", confidence=62,
                                 reason=f"actuatortype reg 3 = {regs[3]} — VAV of 2-weg EPIV, niet te onderscheiden")

        # 4) LG UB40 — FC4-blok met watertemperaturen en druk
        try:
            inp = bus.read_input(addr, 0, 14)
            if inp[1] in (0, 1, 2) and 0 < inp[13] < 200:
                return self._hit(addr, "lg_ub40", confidence=93,
                                 reason="FC4-blok 30001–30014 + plausibele waterdruk")
        except ModbusError:
            pass

        # 5) Wilo Stratos MAXO — regelfunctie 42 + invoerregisters
        try:
            hr = bus.read_holding(addr, 40, 3)
            ir = bus.read_input(addr, 1, 3)
            if hr[2] <= 140 and ir[1] < 9999 and ir[0] < 60000:
                return self._hit(addr, "wilo_stratos", confidence=85,
                                 reason="regelfunctie HR42 ≤ 140 + invoerregisters 1–3")
        except ModbusError:
            pass

        # 6) relaismodule / digitale ingangen die wél op FC3 antwoorden
        try:
            bus.read_coils(addr, 0, 8)
            return self._hit(addr, "em18r", confidence=88,
                             reason="coil-blok leesbaar naast FC3")
        except ModbusError:
            pass
        return None

    def _hit(self, addr: int, mtype: str, base: int | None = None,
             confidence: int = 80, reason: str = "") -> dict:
        meta = TYPES[mtype]
        hit = {
            "address": addr,
            "type": mtype,
            "name": meta["name"],
            "confidence": confidence,
            "reason": reason,
        }
        if base is not None:
            hit["base"] = base
        return hit


def new_bus_changed(old_sig: tuple, new: dict) -> bool:
    b = new["bus"]
    return old_sig != (b["port"], b["baud"], b["parity"], b["stopbits"], b["timeout"])


# --------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "ModbusLab/1.0"
    app: App

    def log_message(self, fmt, *args):  # stil blijven in de journal
        pass

    # ------------------------------------------------------------------ helpers
    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _error(self, code: int, msg: str) -> None:
        self._json(code, {"error": msg})

    # ------------------------------------------------------------------ routes
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/state":
            return self._json(200, self.app.state())
        if path == "/api/ports":
            return self._json(200, {"ports": self.app.ports()})
        if path == "/api/types":
            return self._json(200, {
                "types": TYPES,
                "signal_types": {str(k): {"name": v[0], "unit": v[1]} for k, v in devices.SIGNAL_TYPES.items()},
                "belimo_override": devices.BELIMO_OVERRIDE,
                "grundfos_modes": devices.GRUNDFOS_MODES,
                "grundfos_control_modes": devices.GRUNDFOS_CONTROL_MODES,
                "wilo_control": devices.WILO_CONTROL,
                "lg_modes": devices.LG_MODES,
                "baud_choices": BAUD_CHOICES,
            })
        if path == "/api/update":
            # Staat hier (GET) en niet bij de POST-routes: de UI haalt hem op
            # zonder body, en de cache van een uur zit in check_update().
            return self._json(200, self.app.check_update())
        if path == "/api/bacnet/subnets":
            import bacnet

            nets = bacnet.local_broadcasts()
            return self._json(200, {"broadcasts": nets, "source": bacnet.LAST_SOURCE})
        if path == "/api/bacnet/whois":
            q = parse_qs(urlparse(self.path).query)
            subnet = (q.get("subnet") or [""])[0]
            try:
                return self._json(200, {"devices": self.app.bn_whois(subnet)})
            except Exception as exc:                       # noqa: BLE001
                return self._error(502, f"BACnet: {exc}")
        if path == "/api/bacnet/ede.zip":
            q = parse_qs(urlparse(self.path).query)
            ip = (q.get("ip") or [""])[0]
            dev = int((q.get("device") or ["0"])[0] or 0)
            project = (q.get("project") or [""])[0]
            try:
                pack = self.app.bn_ede_package(ip, dev, project)
            except Exception as exc:                       # noqa: BLE001
                return self._error(502, f"BACnet: {exc}")
            import io
            import zipfile

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for name, data in pack["files"].items():
                    zf.writestr(name, data)
            blob = buf.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition",
                             f'attachment; filename="{pack["prefix"]}_EDE.zip"')
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)
            return None
        if path == "/api/bacnet/ede":
            q = parse_qs(urlparse(self.path).query)
            ip = (q.get("ip") or [""])[0]
            dev = int((q.get("device") or ["0"])[0] or 0)
            try:
                rows = self.app.bn_ede(ip, dev)
            except Exception as exc:                       # noqa: BLE001
                return self._error(502, f"BACnet: {exc}")
            import csv
            import io

            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=["ObjectType", "ObjectInstance", "ObjectName",
                                                     "Description", "PresentValue", "Units"])
            writer.writeheader()
            writer.writerows(rows)
            data = buf.getvalue().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="EDE_{ip.replace(".", "_")}_{dev}.csv"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return None
        if path == "/api/log":
            return self._json(200, {"log": list(self.app.log)})
        if path == "/health":
            return self._json(200, {"ok": True})
        return self._static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._body()
        try:
            if path == "/api/config":
                return self._json(200, self.app.apply_config(body))
            if path == "/api/action":
                mid = body.get("id")
                op = body.get("op")
                if not mid or not op:
                    return self._error(400, "id en op zijn verplicht")
                state = self.app.action(mid, op, body)
                return self._json(200, {"state": state})
            if path == "/api/scan":
                found = self.app.scan(int(body.get("start", 1)), int(body.get("end", 16)))
                return self._json(200, {"found": found})
            if path == "/api/framing":
                res = self.app.framing_scan(int(body.get("address", 1)))
                return self._json(200, {**res, "state": self.app.state()})
            if path == "/api/reconnect":
                self.app.close_bus()
                self.app.wake.set()
                return self._json(200, self.app.state())
            if path == "/api/bacnet/points":
                ip = str(body.get("ip") or "")
                if not ip:
                    return self._error(400, "ip verplicht")
                try:
                    return self._json(200, self.app.bn_points(ip, int(body.get("device") or 0),
                                                              int(body.get("limit") or 80)))
                except Exception as exc:                   # noqa: BLE001
                    return self._error(502, f"BACnet: {exc}")
            if path == "/api/bacnet/write":
                ip = str(body.get("ip") or "")
                try:
                    value = self.app.bn_write(ip, int(body.get("type")), int(body.get("inst")),
                                              body.get("value"))
                    return self._json(200, {"ok": True, "value": value})
                except Exception as exc:                   # noqa: BLE001
                    return self._error(502, f"BACnet: {exc}")
            if path == "/api/poll":
                return self._json(200, self.app.set_poll(body))
            if path == "/api/update":
                return self._json(200, self.app.check_update())
            if path == "/api/clear-log":
                self.app.log.clear()
                return self._json(200, {"ok": True})
            return self._error(404, "onbekende API-route")
        except ActionError as exc:
            return self._error(400, str(exc))
        except ModbusException as exc:
            return self._error(502, str(exc))
        except ModbusTimeout as exc:
            return self._error(504, str(exc))
        except ModbusError as exc:
            return self._error(502, str(exc))
        except Exception as exc:
            return self._error(500, str(exc))

    # ------------------------------------------------------------------ static
    def _static(self, path: str):
        if path in ("/", ""):
            path = "/index.html"
        rel = path.lstrip("/")
        if rel.startswith("static/"):
            rel = rel[len("static/"):]
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".woff2": "font/woff2",
            ".ico": "image/x-icon",
        }.get(os.path.splitext(full)[1].lower(), "application/octet-stream")
        with open(full, "rb") as fh:
            data = fh.read()
        return self._send(200, data, ctype)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--version", action="version", version=f"FlexPoll {APP_VERSION}")
    parser.add_argument("--no-browser", action="store_true",
                        help="start geen browser (enkel bij een ingepakte build)")
    args = parser.parse_args()

    simulate = args.simulate or os.environ.get("MODBUS_SIM") == "1"
    app = App(simulate=simulate)
    Handler.app = app
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{args.port}"
    print(f"FlexPoll {APP_VERSION} op {url}  (sim={simulate})", flush=True)
    print(f"config: {CONFIG_PATH}", flush=True)
    if getattr(sys, "frozen", False) and not args.no_browser:
        # Ingepakte build: de gebruiker start een programma, geen server.
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.close_bus()


if __name__ == "__main__":
    main()