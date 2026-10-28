# FlexPoll

**Modbus & BACnet Diagnostic Suite** — een grafische testbank voor de werkbank en
de werf. Eén Python-proces, een browser als front-end, geen cloud.

Gemaakt door **Free van Nieuwenhove**, met de hulp van **Luc** (AI-copiloot).

*A graphical diagnostic bench for HVAC fieldbuses — Modbus RTU over RS-485,
Modbus TCP/IP and BACnet/IP. Stand-alone: Python standard library plus
`pyserial`, no framework, no build step, no cloud.*

![FlexPoll — Modbus RTU-tab met drie modules op de simulator](docs/screenshot.png)

---

## Wat het doet

**Modbus RTU (RS-485)**
- Lijn samenstellen uit sleepbare modules: Siemens EM1.8x, Belimo VAV/EV/EPIV,
  Grundfos CIM 200, Wilo, LG, Carrier, Clivet (master/slave), Daikin.
- Scannen met confidence-percentage en framing-zoektocht (baud/pariteit/stopbits).
- Actuatoren bedienen, meetwaarden volgen, busverkeer loggen.
- Algemene deelnemer: eigen registers definiëren (FC 1–4, u16/s16/u32/s32/
  float32/bit, woord- en bytevolgorde, schaling, offset, lezen/schrijven).

**Modbus TCP/IP**
- Dezelfde tegel per toestel: IP + poort + unit-id, geen gedeelde lijn.

**BACnet/IP**
- Who-Is in het subnet (broadcast automatisch afgeleid van de eigen interface,
  plus een limited broadcast — geen hardcoded subnet).
- Objecten lezen en schrijven (analoog, binair, multi-state).
- **EDE-export volgens B.I.G.-EU layout 2.3**: vier CSV-bestanden in één zip
  (`_EDE`, `_ObjTypes`, `_StateTexts`, `_Units`), puntkomma, CRLF, UTF-8 BOM.

## Installatie

```bash
git clone <repo-url> flexpoll
cd flexpoll
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

sudo cp -r . /opt/flexpoll          # of draai rechtstreeks uit de clone
sudo cp flexpoll.service /etc/systemd/system/
sudo systemctl enable --now flexpoll
```

Open `http://<host>:8099`.

Zonder systemd:

```bash
.venv/bin/python app.py --host 0.0.0.0 --port 8099
.venv/bin/python app.py --version
```

De configuratie staat in `data/config.json`. Die map staat in `.gitignore` — ze
bevat de echte opstelling (poorten, IP's, modulelijsten) en gaat nooit mee in een
release.

## Zonder hardware

```bash
MODBUS_SIM=1 .venv/bin/python app.py --port 8098   # RTU-simulator
.venv/bin/python modbus_tcp_slave.py               # Modbus TCP-testslave :5020
.venv/bin/python tests/bacnet_slave.py             # BACnet/IP-testslave :47808
```

De simulator is de nep-bus achter de RTU-tab; de twee slaves zijn echte
tegenpartijen voor de TCP- en BACnet-tab.

## Bestanden

| Bestand | Rol |
|---|---|
| `app.py` | HTTP-server, polling-lus, REST-API |
| `devices.py` | moduleprofielen, registers, decoders, schrijfacties |
| `modbus_rtu.py` | RTU-master (CRC16, framing, tracer) |
| `modbus_tcp.py` | Modbus TCP-client (MBAP) |
| `bacnet.py` | BACnet/IP-client, error-PDU-decodering, EDE-export |
| `sim.py` | RTU-simulator |
| `modbus_tcp_slave.py`, `tests/bacnet_slave.py` | testslaves |
| `static/` | front-end (vanilla JS, geen build-stap) |
| `scripts/deploy.sh` | deploy naar een remote Pi (tar over ssh) |

## Ontwikkelen

```bash
make check    # syntaxis + versie-consistentie + licentieheaders
make smoke    # simulator starten, /api/state bevragen, opruimen
```

Zie [`CONTRIBUTING.md`](CONTRIBUTING.md). De CI draait dezelfde controles op elke
push en pull request.

## Versiebeheer

[Semantic Versioning](https://semver.org/lang/nl/), één bron van waarheid in
[`VERSION`](VERSION). De UI toont de versie in de footer, `app.py --version`
geeft ze op de commandolijn, en de git-tag is `v<VERSION>`. Wat er per versie
veranderd is, staat in [`CHANGELOG.md`](CHANGELOG.md).

Een release maken:

```bash
scripts/release.sh 1.1.0     # VERSION + CHANGELOG-kop bijwerken, commit, tag
git push --follow-tags
```

## Licentie

Code: **GNU Affero General Public License v3.0** (`AGPL-3.0-only`) — zie
[`LICENSE`](LICENSE).

FlexPoll is een netwerkdienst, dus **§13** is van toepassing: wie een gewijzigde
versie host en andere gebruikers laat interageren, moet hun de broncode van die
gewijzigde versie aanbieden. Intern gebruik binnen één organisatie is geen
verspreiding — je eigen testbank draaien mag dus zonder meer.

De naam **FlexPoll** en het schild-logo vallen **niet** onder de licentie
(AGPL §7(e)). Zie [`NOTICE`](NOTICE).

BACnet is een gedeponeerd merk van ASHRAE, Modbus van Schneider Electric. Dit
project is niet verbonden aan of goedgekeurd door beide.
