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

### Fixed

- **MS/TP-poortlijst zegt nu waarom ze leeg is.** Zonder aangesloten
  USB-RS485-adapter stond er een lege dropdown, wat op een kapotte UI lijkt. Nu
  staat er "geen adapter gevonden" met de hint om de stick in te pluggen, plus een
  ↻-knop om de poorten opnieuw te zoeken zonder de pagina te herladen.

## [1.5.0] — 2026-11-01

### Added

- **BACnet MS/TP (master).** Nieuwe tab voor BACnet over RS-485: eigen framing
  (preamble, header-CRC-8, data-CRC-16/X.25), token-cyclus, Poll-For-Master,
  Who-Is/I-Am, object-list en Present_Value lezen/schrijven. Getest tegen een
  gesimuleerde peer (`make mstp-test`, via een pty) en met de frame-voorbeelden
  uit de standaard — **niet** tegen een echt toestel; dat staat ook zo in de UI.
  Verbinden zet de Modbus-polling op pauze en geeft de poort vrij, want één
  poort kan maar één protocol tegelijk dragen.

## [1.4.0] — 2026-11-01

### Added

- **Handleiding voor eindgebruikers** in `docs/`, gebouwd met MkDocs Material en
  gepubliceerd op <https://freevn.github.io/FlexPoll/>: installeren, eerste
  meting op de simulator, Modbus RTU, Modbus TCP, BACnet/IP en
  probleemoplossing. Schermafbeeldingen komen uit de simulator en krijgen
  genummerde aanduidingen via `docs/shots/annotate.py` (één `SPECS`-tabel met
  coördinaten, dus bij een UI-wijziging verschuif je alleen het cijfer).
  Publicatie loopt via `.github/workflows/docs.yml` bij elke wijziging aan
  `docs/`; `mkdocs build --strict` faalt op een kapotte verwijzing.

### Added

- **Polling zelf sturen.** Interval instelbaar van **1 tot 60 s** (was 2–60) met
  een invoerveld naast de metingsteller, plus **play / pauze / stop**. Pauzeren
  laat de poort open, stoppen geeft ze vrij zodat een andere tool de adapter kan
  gebruiken. De modus wordt bewaard in `config.json` (`bus.mode`).
- **Footer met wegwijzers.** Links naar de handleiding en de repo, en een knop
  **Controleer updates** die `/api/update` bevraagt: laatste GitHub-release
  (5 s time-out, 1 uur cache), met `newer`-vlag. Offline geeft dat een nette
  melding in plaats van een fout.

## [1.3.0] — 2026-10-31

### Added

- **Windows onefile-exe als extra download.** `flexpoll-onefile.spec` +
  `make dist-onefile` bouwen dezelfde app als één bestand van ±9 MB; de
  release-workflow levert het als `FlexPoll-vX.Y.Z-windows-x64-onefile.exe`
  naast de zip. Sneller even neergezet, maar trager starten (uitpakken naar
  `%TEMP%`) en meer antivirusruis — de zip blijft de aanbevolen weg.

## [1.2.1] — 2026-10-31

### Changed

- **CI moderniseert.** Alle actions naar hun Node 24-versies (checkout v7, setup-python v7, upload-artifact v7, download-artifact v8, Docker-actions v4/v6/v7), zodat de deprecation-waarschuwingen weg zijn. De Linux-builds zijn **vastgepind op Ubuntu 22.04** in plaats van `ubuntu-latest`: die schuift naar Ubuntu 26 en dan eist de binary een glibc die te nieuw is voor Debian 12 en Raspberry Pi OS. Gemeten vloer van de binaries: **glibc 2.35**.

### Changed

- **README opent nu met een bèta-waarschuwing** en een Engelse samenvatting, zodat
  een internationale bezoeker in drie regels ziet wat het is (en dat het nog niet
  af is). GitHub-onderwerpen (topics) en de repo-omschrijving staan op de termen
  waarop mensen zoeken: modbus, modbus-rtu, bacnet, bacnet-ip, rs485, fieldbus,
  hvac, building-automation, diagnostic-tool.

### Fixed

- **BACnet/IP op Windows (en macOS) vond geen interfaces.** `local_broadcasts()`
  schraapte enkel de Linux-uitvoer van `ip -4 -o addr show`; die bestaat niet op
  Windows, dus de lijst bleef leeg en de UI zei *"geen IPv4-interface gevonden"*
  terwijl de netwerkkaart er gewoon was. Gevolg: Who-Is ging alleen naar
  255.255.255.255 en vond niets. Nu meerdere bronnen: `psutil` als het er is,
  Windows via `GetIpAddrTable` (IPHLPAPI, ctypes, geen extra dependency), Linux
  via `ip`, en macOS/BSD via `ifconfig`. Loopback, link-local (169.254/16) en
  /31-/32-maskers worden overgeslagen. `/api/bacnet/subnets` meldt nu ook welke
  bron gebruikt is.

## [1.2.0] — 2026-10-31

### Added

- **Linux arm64-build.** De release-matrix bouwt nu ook `linux-arm64` op
  `ubuntu-24.04-arm` (gratis op publieke repo's). Pi's en ARM-servers hoeven dus
  geen Python meer te hebben.
- **`scripts/install.sh` installeert standaard de binary.** Zonder argumenten
  downloadt het de release-tarball voor de eigen architectuur (`x64`/`arm64`),
  pakt uit in `/opt/flexpoll` en schrijft de systemd-unit met
  `FLEXPOLL_DATA=/opt/flexpoll/data`. `--source` doet het oude pad (git clone +
  venv), `--update` volgt het kanaal dat er al staat, `FLEXPOLL_VERSION` pint een
  versie.
- **Handmatige build-run zonder release.** `workflow_dispatch` op de
  release-workflow bouwt en test alle artifacts, maar slaat de release-job over
  (`if: github.event_name == 'push'`) — zo test je de matrix zonder een tag te
  zetten.

### Fixed

- **`install.sh` wees naar de verkeerde repo** (`fvannieuwenhove/flexpoll`), dus
  de broninstallatie klapte er meteen uit. Nu `FreeVN/FlexPoll`, en de clone is
  `--depth 1`.

## [1.1.2] — 2026-10-31

## [1.1.1] — 2026-10-31

## [1.1.0] — 2026-10-31

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

### Changed

- **Docker-bestanden naar `docker/`.** `Dockerfile` en `docker-compose.yml`
  staan niet meer in de root, zodat de repo bovenaan leesbaar blijft. De
  build-context blijft de repo-root (`.dockerignore` hoort daar en blijft daar):
  `docker build -f docker/Dockerfile .` of
  `docker compose -f docker/docker-compose.yml up -d`.

### Fixed

- **Geen hostnaam meer in de HTML-bron.** De `#hostinfo`-placeholder stond hard
  op de naam van de ontwikkel-Pi; die wordt bij de eerste render toch
  overschreven, maar in een publieke repo hoort geen enkele hostnaam te staan.
- **Poortlijst op Windows.** `list_ports()` keek enkel in `/dev/serial/by-id`
  en `/dev/ttyUSB*`; op Windows bestaat dat pad niet, waardoor de keuzelijst
  altijd leeg was en een ingepakte `.exe` zonder poort startte. Niet-Linux
  gebruikt nu `serial.tools.list_ports` (COM-poort + driverbeschrijving), Linux
  houdt zijn by-id-links en valt alleen bij een lege lijst terug op pyserial
  (zonder de `ttyS0..31`-ruis).
- **FTDI-voorkeur** werd gemist wanneer de fabrikant enkel in de hwid stond
  (Windows: "USB Serial Port" + VID 0403). De voorkeurskeuze kijkt nu naar pad,
  label én hwid.

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
