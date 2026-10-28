# Changelog

Alle noemenswaardige wijzigingen aan FlexPoll staan hier. Het formaat volgt
[Keep a Changelog](https://keepachangelog.com/nl/1.1.0/) en de versie nummering
volgt [Semantic Versioning](https://semver.org/lang/nl/): `MAJOR.MINOR.PATCH`.

- **MAJOR** — een wijziging die bestaande configuraties of de API breekt.
- **MINOR** — nieuwe functionaliteit, achterwaarts compatibel.
- **PATCH** — foutoplossingen en kleine verbeteringen.

De versie staat in [`VERSION`](VERSION); die ene regel is de bron van waarheid
voor de UI, `python3 app.py --version` en de git-tag.

## [Unreleased]

### Added

- **Distributiekanalen.** Naast de broninstallatie nu ook:
  - `scripts/install.sh` — Linux in één commando (klonen, venv, systemd-unit,
    `--update`, `--uninstall`);
  - `Dockerfile` + `docker-compose.yml` (image op GHCR bij elke tag);
  - zelfstandige builds via PyInstaller (`flexpoll.spec`): Windows `.exe`, Linux
    en macOS, gebouwd door `.github/workflows/release.yml` en aan de release
    gehangen;
  - `make dist` en `make docker` voor lokaal gebruik.
- **Configuratiepad buiten de installatiemap** bij een ingepakte build: `data/`
  gaat naar `%APPDATA%\FlexPoll`, `~/Library/Application Support/FlexPoll` of
  `~/.local/share/FlexPoll`. Te overschrijven met `FLEXPOLL_DATA`. Een
  broninstallatie blijft `data/` naast de code gebruiken — bestaande opstellingen
  merken niets.
- **Ingepakte builds openen de browser zelf**; `--no-browser` zet dat uit.
- De opstartregel toont nu de versie én het pad van de configuratie.

## [1.0.0] — 2026-10-28

Eerste publieke release. FlexPoll is geschreven op de werf en heeft daar op echte
hardware gedraaid: Siemens EM1.8x-modules, een Belimo VAV-Compact, een Grundfos
CIM 200 en twee BACnet/IP-toestellen.

### Added

- **Modbus RTU (RS-485)** — grafische lijn met sleepbare modules, scan met
  confidence-score, framing-zoektocht (baud/pariteit/stopbits), busverkeer-tracer
  en een algemene deelnemer waarin je zelf registers definieert (FC 1–4, u16/s16/
  u32/s32/float32/bit, woord- en bytevolgorde, schaling, offset, lezen/schrijven).
- **Moduleprofielen** — Siemens EM1.8U/EM1.8R, Belimo VAV/EV/EPIV, Grundfos
  CIM 200, Wilo, LG, Carrier, Clivet (master/slave) en Daikin.
- **Belimo VAV-Compact** — Vmin/Vmax instellen in m³/h (de tool rekent met qnom
  terug naar de 0,01 %-registers), setpunt met vertaling naar de band
  Vmin…Vmax, override-bediening inclusief `Mid (Vmid)`, regelmodus en
  bus-failstand.
- **Modbus TCP/IP** — dezelfde tegel per toestel, met IP + poort + unit-id in
  plaats van een gedeelde lijn.
- **BACnet/IP** — Who-Is met automatisch afgeleid broadcastadres, objecten lezen
  en schrijven (analoog, binair, multi-state), en **EDE-export volgens
  B.I.G.-EU layout 2.3**: vier CSV's in één zip, puntkomma, CRLF, UTF-8 BOM.
- **Simulator** (`--simulate` / `MODBUS_SIM=1`) plus twee testslaves voor Modbus
  TCP en BACnet/IP, zodat de tool zonder hardware te testen is.
- **Self-contained** — Python-stdlib + `pyserial`, geen framework, geen
  build-stap, geen cloud. Eén proces met een browser als front-end.

### Fixed

- **BACnet-fouten werden platgeslagen** tot "toestel weigert het verzoek". De
  client decodeert nu error-class en error-code uit de error/reject/abort-PDU en
  toont ze met een hint; er wordt niet opnieuw geprobeerd op een error-PDU, enkel
  op een timeout.
- **Confirmed-Request-header** stond verkeerd (invoke-id en max-APDU omgedraaid),
  waardoor een toestel dat niet kan segmenteren elk groot antwoord weigerde met
  `communication / 54`. Kleine leesacties werkten wel — vandaar dat het op een
  toestelprobleem leek.
- **Object-list** wordt in één leesactie opgehaald in plaats van per index.
- **Niet elk BACnet-object heeft een present-value**; die worden niet langer als
  fout getoond.
- **Tabwissel lekte RS-485-informatie**: scanresultaten en de busbar bleven
  zichtbaar op de TCP- en BACnet-tab.
- **Status liegt niet meer**: een module is pas online als minstens één leesactie
  echt slaagde, en geconfigureerde punten blijven zichtbaar als het toestel
  offline is.

### Changed

- **Licentie** van Apache-2.0 naar **AGPL-3.0-only** (28-10-2026). FlexPoll wordt
  over het netwerk geserveerd, dus §13 is van toepassing.
- **Branding**: geen Gezel-logo of -naam meer in de interface, `NOTICE`,
  SPDX-headers en systemd-omschrijving. © 2026 Free van Nieuwenhove.
- **Versienummer** zichtbaar in de footer en via `--version`.
