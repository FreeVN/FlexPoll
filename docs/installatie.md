# Installeren

Kies je platform. De kant-en-klare builds hebben **geen Python** nodig.

## Linux (Raspberry Pi, LXC, pc)

Eén commando, als root:

```bash
curl -fsSL https://raw.githubusercontent.com/FreeVN/FlexPoll/main/scripts/install.sh \
  | sudo bash -s --
```

Het script downloadt de binary voor jouw architectuur (x64 of arm64), zet hem in
`/opt/flexpoll`, schrijft een systemd-unit en start de service. Daarna staat de UI
op `http://<ip-van-de-doos>:8099`.

```bash
sudo scripts/install.sh --update      # nieuwe versie
sudo scripts/install.sh --uninstall   # service weg, config blijft
```

Zet je gebruiker één keer in de `dialout`-groep, anders kan de tool de
USB-adapter niet openen:

```bash
sudo usermod -aG dialout "$USER" && sudo systemctl restart flexpoll
```

## Windows

Download `FlexPoll-vX.Y.Z-windows-x64.zip` van de
[releases-pagina](https://github.com/FreeVN/FlexPoll/releases), pak uit (bv. in
`C:\Tools\FlexPoll`) en start `flexpoll.exe`.

- Niet in `C:\Program Files` uitpakken: daar mag de app niet schrijven.
- SmartScreen waarschuwt omdat de build niet ondertekend is → **Meer informatie**
  → **Toch uitvoeren**.
- Liever één bestand? Er is ook `…-windows-x64-onefile.exe`. Die start trager
  (pakt zichzelf elke keer uit) maar je hebt geen map.

## macOS

`FlexPoll-vX.Y.Z-macos-arm64.zip` uitpakken en `FlexPoll/flexpoll` starten. Eerste
keer blokkeert Gatekeeper: rechtsklik → **Open**. De build is niet genotariseerd.

## Docker

```bash
docker run -d --name flexpoll -p 8099:8099 \
  --device /dev/serial/by-id/usb-FTDI_...-if00-port0:/dev/ttyUSB0 \
  --group-add dialout -v flexpoll-data:/data \
  ghcr.io/freevn/flexpoll:latest
```

Het image staat voorlopig **privé** op GHCR: bouw lokaal met
`docker build -f docker/Dockerfile -t flexpoll .` of log in met een token dat
`read:packages` mag.

## Vanuit de bron

```bash
git clone https://github.com/FreeVN/FlexPoll.git && cd FlexPoll
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python app.py --port 8099
```

## Waar staat mijn configuratie?

De app schrijft zijn opstelling **niet** naast de binary maar in de gegevensmap
van de gebruiker:

| Platform | Pad |
|---|---|
| Linux | `~/.local/share/FlexPoll/config.json` (service: `/opt/flexpoll/data/`) |
| Windows | `%APPDATA%\FlexPoll\config.json` |
| macOS | `~/Library/Application Support/FlexPoll/config.json` |

Die map kopiëren is dus genoeg om je opstelling mee te nemen naar een andere pc.
