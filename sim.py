# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Gezel HVAC+ (https://gezel.be)
"""Gesimuleerde RS-485 bus — enkel voor demo's en UI-tests (MODBUS_SIM=1)."""

from __future__ import annotations

import math
import time

from modbus_rtu import ModbusException, ModbusTimeout


class SimBus:
    def __init__(self, *args, **kwargs):
        self.port = "simulated"
        self.baud = 9600
        self.parity = "N"
        self.stopbits = 1
        self.timeout = 0.2
        self.t0 = time.time()
        self.coils = {4: [0] * 8}
        self.di = {5: [1, 0, 1, 1, 0, 0, 1, 0]}
        self.regs: dict[tuple[int, int], int] = {}
        for i, v in enumerate([1, 6, 1, 10, 0, 0, 0, 0]):
            self.regs[(3, 99 + i)] = v
        for i, v in enumerate([0, 10000, 0, 0]):
            self.regs[(3, i)] = v
        for i, v in enumerate([4520, 0, 0, 2, 4230, 65, 7800, 195, 640]):
            self.regs[(6, i)] = v
        self.regs[(6, 100)] = 0x1A2B
        self.regs[(6, 101)] = 0x3C4D
        self.regs[(6, 102)] = 0x5E6F
        self.regs[(6, 103)] = 308
        self.regs[(6, 110)] = 250
        self.regs[(6, 105)] = 2000     # Vmin 20 %
        self.regs[(6, 106)] = 8000     # Vmax 80 %
        self.regs[(6, 108)] = 0        # bus-failstand: laatste setpunt
        self.regs[(6, 116)] = 1        # regelmodus: debietsturing
        self.regs[(6, 117)] = 1        # eenheid: m³/h
        self.regs[(6, 118)] = 1        # setpuntbron: bus
        self.regs[(7, 100)] = 1
        self.regs[(7, 101)] = 6
        self.regs[(7, 102)] = 0
        self.regs[(7, 103)] = 7800
        self.regs[(7, 200)] = 0b0000001100100011

        # --- extra testapparaten (8 Wilo, 9 LG, 10 EV, 11 EPIV2, 12 EPIV6) ---
        self.extra_hr = {
            8: {1: 150, 40: 1, 41: 0, 42: 4, 300: 1},
            9: {0: 4, 1: 1, 2: 345, 3: 210, 4: 0, 5: 0, 6: 0, 7: 0, 8: 480, 9: 0, 24: 90},
            10: {0: 4500, 1: 0, 2: 0, 3: 4, 4: 4230, 6: 7800, 9: 1200, 10: 0,
                 16: 352, 18: 298, 20: 54, 23: 72, 26: 3400, 27: 0,
                 105: 0, 106: 10000, 110: 42,
                 100: 0x1111, 101: 0x2222, 102: 0x3333, 103: 308, 140: 1},
            11: {0: 5000, 1: 0, 2: 0, 3: 2, 4: 4230, 6: 7800, 7: 750, 11: 5000,
                 100: 0xAAAA, 101: 0xBBBB, 102: 0xCCCC, 103: 401,
                 116: 1, 117: 1, 118: 1},
            20: {0: 2, 1: 45, 4: 50, 239: 44, 240: 3, 241: 1, 242: 50, 244: 39, 245: 44,
                 246: 41, 247: 9, 248: 62, 249: 41, 250: 45, 272: 0,
                 # slave-blokken: basis + 100 x intern adres (244 -> 344/444/544)
                 339: 42, 340: 3, 341: 1, 342: 48, 344: 36, 345: 41, 346: 38,
                 347: 11, 348: 58, 349: 38, 350: 42, 372: 0,
                 439: 40, 440: 1, 441: 1, 442: 48, 444: 32, 445: 33, 446: 32,
                 447: 11, 448: 0, 449: 0, 450: 0, 472: 0,
                 539: 49, 540: 2, 541: 1, 542: 47, 544: 29, 545: 35, 546: 31,
                 547: 11, 548: 71, 549: 44, 550: 48, 572: 0},
            30: {0: 215, 1: 65000, 2: 0x4236, 3: 0x0000, 4: 1, 5: 0, 6: 0, 7: 0,
                 8: 0, 9: 0, 10: 1234, 11: 0, 12: 0, 13: 0, 14: 0, 15: 0},
            21: {0: 0, 1: 1, 4: 0, 7: 1, 10: 3, 11: 452, 12: 78, 14: 3, 15: 382, 16: 451,
                 30: 0, 31: 0, 32: 0, 34: 70, 36: 452, 299: 3, 304: 1},
            12: {0: 5000, 1: 0, 2: 0, 3: 5, 4: 3100, 6: 6200, 9: 900, 10: 0, 16: 2,
                 100: 0x1234, 101: 0x5678, 102: 0x9ABC, 103: 410,
                 105: 4500, 106: 6000, 110: 0, 116: 1, 117: 1, 118: 1,
                 207: 10000, 208: 90, 212: 10000, 213: 60},
        }
        self.extra_ir = {
            8: {1: 62, 2: 123, 3: 0, 4: 340, 5: 100, 6: 15, 7: 2870, 8: 2941,
                9: 0, 10: 4, 35: 0, 36: 0, 37: 0, 38: 3, 39: 0},
            9: {0: 0, 1: 2, 2: 312, 3: 358, 4: 352, 5: 472, 6: 0, 7: 211, 8: 128,
                9: 0, 10: 0, 11: 0, 12: 83, 13: 16, 9997: 1, 9998: 2},
        }
        self.extra_coils = {9: [1, 1, 0, 0, 0, 0, 0], 30: [1, 0, 1, 0, 0, 0, 0, 0]}
        self.extra_di = {9: [0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]}

    def open(self):
        pass

    def close(self):
        pass

    def is_open(self):
        return True

    def _known(self, addr):
        if addr not in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 20, 21, 30):
            raise ModbusTimeout(f"geen antwoord van adres {addr}")

    def _tick(self, base, amp, period):
        return int(base + amp * (0.5 + 0.5 * math.sin((time.time() - self.t0) / period)))

    def read_coils(self, addr, start, qty):
        self._known(addr)
        if addr in self.extra_coils:
            bits = self.extra_coils[addr]
            return [bits[i] if i < len(bits) else 0 for i in range(start, start + qty)]
        if addr != 4:
            raise ModbusException(1)
        return list(self.coils[4][start:start + qty])

    def read_discrete_inputs(self, addr, start, qty):
        self._known(addr)
        if addr in self.extra_di:
            bits = self.extra_di[addr]
            return [bits[i] if i < len(bits) else 0 for i in range(start, start + qty)]
        if addr != 5:
            raise ModbusException(1)
        return list(self.di[5][start:start + qty])

    def read_holding(self, addr, start, qty):
        self._known(addr)
        if addr in self.extra_hr:
            regs = self.extra_hr[addr]
            if all((start + i) not in regs for i in range(qty)):
                raise ModbusException(2)
            return [regs.get(start + i, 0) for i in range(qty)]
        if addr == 3:
            if start == 0:
                vals = [self._tick(2150, 120, 40), 1, 0, self._tick(5000, 900, 25),
                        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 32762, 32762]
                return vals[:qty]
            if start == 99:
                return [self.regs[(3, 99 + i)] for i in range(qty)]
            raise ModbusException(2)
        if addr == 6:
            if start == 0:
                vals = [self.regs[(6, i)] for i in range(9)]
                vals[6] = self._tick(7800, 400, 30)
                vals[7] = int(vals[6] * 2.5 / 100)
                return vals[:qty]
            if 100 <= start <= 118:
                return [self.regs.get((6, start + i), 0) for i in range(qty)]
            raise ModbusException(2)
        if addr == 7:
            regs = dict(self.regs)
            regs[(7, 200)] = 0x0323 if self.regs[(7, 100)] & 2 else 0x0121
            regs[(7, 202)] = self.regs.get((7, 101), 3)
            regs[(7, 203)] = self.regs[(7, 102)]
            # 003xx-blok volgens de Grundfos CIM 200 manual (register X = telegram X-1)
            regs[(7, 300)] = self._tick(4520, 60, 45)    # 00301 Head            0.001 bar
            regs[(7, 301)] = self._tick(120, 12, 33)     # 00302 VolumeFlow      0.1 m³/h
            regs[(7, 302)] = self._tick(8300, 300, 50)   # 00303 RelPerformance  0.01 %
            regs[(7, 303)] = self._tick(2870, 40, 50)    # 00304 Speed           1 rpm
            regs[(7, 304)] = self._tick(480, 6, 50)      # 00305 Frequency       0.1 Hz
            regs[(7, 307)] = self._tick(4700, 200, 25)   # 00308 ActualSetpoint  0.01 %
            regs[(7, 308)] = self._tick(35, 3, 55)       # 00309 MotorCurrent    0.1 A
            regs[(7, 317)] = 29515                       # 00318 PowerElectronicTemp 0.01 K (295,15 K)
            regs[(7, 318)] = 31855                       # 00319 MotorTemp
            regs[(7, 320)] = 29315                       # 00321 ElectronicTemp (293,15 K)
            regs[(7, 321)] = self._tick(28865, 200, 60)  # 00322 PumpLiquidTemp (288,65 K)
            regs[(7, 337)] = self.regs[(7, 103)]
            if start == 200:
                return [regs.get((7, 200 + i), 0) for i in range(qty)]
            if start == 300:
                return [regs.get((7, 300 + i), 0) for i in range(qty)]
            if start in (317, 319):
                return [regs.get((7, start + i), 0) for i in range(qty)]
            if start == 337:
                return [regs.get((7, 337), 0)][:qty]
            if 100 <= start < 110:
                return [regs.get((7, start + i), 0) for i in range(qty)]
            raise ModbusException(2)
        raise ModbusTimeout("geen antwoord")

    def read_input(self, addr, start, qty):
        self._known(addr)
        if addr in self.extra_ir:
            regs = self.extra_ir[addr]
            if all((start + i) not in regs for i in range(qty)):
                raise ModbusException(2)
            return [regs.get(start + i, 0) for i in range(qty)]
        return self.read_holding(addr, start, qty)

    def write_coil(self, addr, coil, value):
        self._known(addr)
        if addr in self.extra_coils:
            self.extra_coils[addr][coil] = 1 if value else 0
            return
        self.coils[4][coil] = 1 if value else 0

    def write_register(self, addr, register, value):
        self._known(addr)
        if addr == 21:                       # Daikin: commando's laten doorwerken
            regs = self.extra_hr[21]
            if register == 8:
                regs[1] = 1 if value else 0
                regs[14] = 3 if value else 1
            elif register == 33:
                regs[10] = 3 if value else 2
            elif register in (34, 36):
                regs[11] = value
        if addr in self.extra_hr:
            self.extra_hr[addr][register] = value
            return
        if addr == 7 and 100 <= register <= 103:
            self.regs[(7, register)] = value
            if register == 101:
                self.regs[(7, 202)] = value      # actuele regelmethode volgt
            if register == 103:
                self.regs[(7, 337)] = value      # UserSetpoint volgt
            return
        self.regs[(addr, register)] = value

    def write_registers(self, addr, start, values):
        for i, v in enumerate(values):
            self.write_register(addr, start + i, v)
