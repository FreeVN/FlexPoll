# FlexPoll

**Modbus & BACnet Diagnostic Suite** — een grafische testbank voor de werkbank en de werf.
Gebouwd door [Gezel HVAC+](https://gezel.be) voor het uitmeten van RS-485-bussen,
Modbus TCP-koppelingen en BACnet/IP-installaties.

FlexPoll is bewust **stand-alone**: geen cloud, geen abonnement, geen LLM, geen
externe API's. Eén Python-proces met een browser als front-end.

## Wat het doet

**Modbus RTU (RS-485)**
- Lijn samenstellen uit sleepbare modules: Siemens EM1.8x, Belimo VAV/EV/EPIV,
  Grundfos, Wilo, LG, Carrier, Clivet, Daikin.
- Scannen met confidence-percentage en framing-zoektocht (baud/pariteit/stopbits).
- Actuatoren bedienen, meetwaarden volgen, busverkeer loggen.
- Algemene deelnemer: zelf registers toevoegen (FC 1–4, u16/s16/u32/s32/float32/bit,
  woord- en bytevolgorde, schaling, offset, lezen/schrijven).

**Modbus TCP/IP**
- Zelfde functionaliteit per toestel: IP + poort + unit, geen gedeelde lijn.

**BACnet/IP**
- Who-Is in het subnet (broadcast automatisch afgeleid van de eigen interface).
- Objecten lezen en schrijven (analoog, binair, multi-state).
- **EDE-export volgens B.I.G.-EU layout 2.3**: vier CSV-bestanden in één zip
  (`_EDE`, `_ObjTypes`, `_StateTexts`, `_Units`), met puntkomma, CRLF en UTF-8 BOM.

## Installatie

```bash
sudo apt install python3 python3-serial
cp -r . /opt/flexpoll
sudo cp flexpoll.service /etc/systemd/system/
sudo systemctl enable --now flexpoll
```

Open `http://<host>:8099`. De configuratie staat in `data/config.json`
en wordt niet mee verspreid (staat in `.gitignore`).

Draaien zonder hardware:

```bash
python3 app.py --simulate          # RTU-simulator met alle moduletypes
python3 modbus_tcp_slave.py        # Modbus TCP-testslave op poort 5020
python3 bacnet_slave.py            # BACnet/IP-testslave op UDP 47808
```

## Bestanden

| Bestand | Rol |
|---|---|
| `app.py` | HTTP-server, polling-lus, API |
| `devices.py` | moduleprofielen, registers, decoders |
| `modbus_rtu.py` | RTU-master (CRC16, framing, tracer) |
| `modbus_tcp.py` | Modbus TCP-client (MBAP) |
| `bacnet.py` | BACnet/IP-client + EDE-export (stdlib) |
| `sim.py` | RTU-simulator |
| `modbus_tcp_slave.py`, `bacnet_slave.py` | testslaves |
| `static/` | front-end (geen build-stap, geen frameworks) |

## Licentie

Code: **Apache License 2.0** (zie `LICENSE`).

De namen **Gezel**, **Gezel HVAC+** en **FlexPoll**, en de bijbehorende logo's,
vallen **niet** onder die licentie. Zie `NOTICE`.
