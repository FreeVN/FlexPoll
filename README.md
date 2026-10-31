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

Vier wegen, van licht naar zwaar. Ze leveren allemaal hetzelfde: een web-UI op
poort 8099 die met je eigen seriële poort en je eigen netwerk praat.

| Platform | Makkelijkste weg | Python nodig? |
|---|---|---|
| Linux x86_64 / arm64 (Pi, LXC, pc) | install-script of release-tarball | nee |
| Windows 10/11 x64 | release-zip met `flexpoll.exe` | nee |
| macOS (Apple Silicon) | release-zip | nee |
| Docker (Linux) | image of compose | nee |

### Linux — één commando

```bash
curl -fsSL https://raw.githubusercontent.com/FreeVN/FlexPoll/main/scripts/install.sh \
  | sudo bash -s --
```

Dat downloadt de **kant-en-klare binary** voor je architectuur uit de nieuwste
release, zet hem in `/opt/flexpoll`, schrijft een systemd-unit en start de
service. Geen Python, geen venv. Heeft de doos geen internet of wil je uit de
bron: `... | sudo bash -s -- --source`.

Opties (ook bruikbaar als je de repo al hebt):

```bash
sudo scripts/install.sh                 # binary voor deze arch (x64 of arm64)
sudo scripts/install.sh --source        # git clone + venv + pyserial
sudo scripts/install.sh --update        # zelfde kanaal, nieuwste versie
sudo scripts/install.sh --uninstall     # service weg, data blijft staan
sudo FLEXPOLL_PORT=8098 scripts/install.sh   # andere poort
sudo FLEXPOLL_VERSION=1.2.0 scripts/install.sh   # versie pinnen
```

Wat het installatiescript **niet** voor je doet: je gebruiker in de
`dialout`-groep zetten. Doe dat één keer, anders opent de app de adapter niet:

```bash
sudo usermod -aG dialout "$USER" && sudo systemctl restart flexpoll
```

Handmatig, zonder script: download `FlexPoll-vX.Y.Z-linux-x64.tar.gz` (of
`-linux-arm64`) van de [releases](https://github.com/FreeVN/FlexPoll/releases),
pak uit en start:

```bash
tar xzf FlexPoll-v1.2.0-linux-x64.tar.gz
cd FlexPoll && ./flexpoll --port 8099        # data komt in ~/.local/share/FlexPoll
```

32-bit ARM (armv7, bv. een oude Pi) heeft geen kant-en-klare build — gebruik
daar `--source`.

### Windows 10/11 (x64)

1. Download `FlexPoll-vX.Y.Z-windows-x64.zip` van de
   [releases](https://github.com/FreeVN/FlexPoll/releases).
2. Uitpakken — **niet** in `C:\Program Files` (schrijfrechten), wel bv.
   `C:\Tools\FlexPoll`.
3. `flexpoll.exe` dubbelklikken. De console opent, de browser gaat vanzelf naar
   `http://127.0.0.1:8099`.

- De config komt in `%APPDATA%\FlexPoll`, niet naast de exe. Overschrijven kan met
  de omgevingsvariabele `FLEXPOLL_DATA`.
- **SmartScreen**: de build is niet ondertekend. "Meer informatie" → "Toch
  uitvoeren". Wil je die waarschuwing niet, gebruik dan Docker of de
  broninstallatie.
- **USB-driver**: FTDI werkt out-of-the-box. CH340/CP210x hebben een driver van
  de fabrikant nodig (WCH/Silicon Labs); zonder driver verschijnt er geen COM-poort.
- **Firewall**: bij de eerste start vraagt Windows om toestemming voor poorten
  8099 (UI) en 47808/UDP (BACnet). Weiger je dat, dan werkt de UI lokaal maar
  zie je geen BACnet-toestellen.
- Geen `.msi`/installer: het is een map die je uitpakt. Updates = nieuwe zip
  uitpakken; je config in `%APPDATA%` blijft staan.

### macOS (Apple Silicon)

Download `FlexPoll-vX.Y.Z-macos-arm64.zip`, pak uit en start `FlexPoll/flexpoll`
vanuit Terminal. De build is niet genotariseerd: macOS blokkeert de eerste start,
rechtsklik → **Open**, of `xattr -dr com.apple.quarantine FlexPoll`. De config
komt in `~/Library/Application Support/FlexPoll`. Intel-Macs hebben nog geen
build — gebruik daar de broninstallatie.

### Docker

```bash
docker run -d --name flexpoll -p 8099:8099 \
  --device /dev/serial/by-id/usb-FTDI_...-if00-port0:/dev/ttyUSB0 \
  --group-add dialout -v flexpoll-data:/data \
  ghcr.io/freevn/flexpoll:latest
```

Of met compose: `docker compose -f docker/docker-compose.yml up -d` — de
[`docker-compose.yml`](docker/docker-compose.yml) staat in `docker/`, net als de
[`Dockerfile`](docker/Dockerfile). De build-context blijft de repo-root, dus zelf
bouwen gaat met:

```bash
docker build -f docker/Dockerfile -t flexpoll .
```

Voor BACnet/IP-discovery heb je `--network host` nodig: UDP-broadcast over een
brug gaat de deur niet uit. Het GHCR-image is voorlopig **privé**; bouw lokaal of
`docker login ghcr.io` met een token dat `read:packages` mag.

### Vanuit de bron (elk platform met Python 3.10+)

```bash
git clone https://github.com/FreeVN/FlexPoll.git flexpoll && cd flexpoll
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python app.py --port 8099
```

Open `http://<host>:8099`.

> **Let op:** FlexPoll heeft geen authenticatie. Zet hem op een besloten netwerk
> of achter Tailscale/VPN, niet rechtstreeks op het internet.

De configuratie staat in `data/config.json` (bij een broninstallatie) of in de
gegevensmap hierboven (bij een ingepakte build) — overschrijfbaar met
`FLEXPOLL_DATA`. Die map staat in `.gitignore`: ze bevat de echte opstelling
(poorten, IP's, modulelijsten) en gaat nooit mee in een release.

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
| `scripts/install.sh` | Linux: klonen, venv, systemd-unit, update, uninstall |
| `scripts/release.sh` | versie bumpen + changelog-kop + commit + tag |
| `scripts/smoke.py` | rooktest tegen de simulator (ook in CI) |
| `scripts/deploy.sh` | deploy naar een remote host (tar over ssh) |
| `flexpoll.spec` | PyInstaller-recept voor de zelfstandige builds |
| `docker/Dockerfile`, `docker/docker-compose.yml` | container-image met volume voor `data/` (`.dockerignore` blijft in de root: die hoort bij de context) |

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
