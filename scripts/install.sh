#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
#
# FlexPoll installeren of bijwerken op een Linux-doos (Pi, LXC, gewone pc).
#
#   sudo scripts/install.sh                 # kant-en-klare binary voor deze arch
#   sudo scripts/install.sh --source        # uit de git-bron (venv + pyserial)
#   sudo scripts/install.sh --update        # zelfde kanaal, nieuwste versie
#   sudo scripts/install.sh --uninstall     # service weg, data blijft
#
# Standaard wordt de release-tarball van GitHub gedownload: geen Python, geen
# venv, enkel de binary + static/ + VERSION. `--source` kloont de repo en maakt
# een venv — nodig op een architectuur zonder kant-en-klare build.
#
# Wat het doet: installeren in /opt/flexpoll, systemd-unit schrijven, service
# enablen en starten, URL printen. De config blijft in <dir>/data en overleeft
# een update of een herinstallatie.
set -euo pipefail

DIR="${FLEXPOLL_DIR:-/opt/flexpoll}"
PORT="${FLEXPOLL_PORT:-8099}"
USERNAME="${FLEXPOLL_USER:-${SUDO_USER:-$(id -un)}}"
SERVICE="flexpoll"
REPO="${FLEXPOLL_REPO:-https://github.com/FreeVN/FlexPoll.git}"
BRANCH="${FLEXPOLL_BRANCH:-main}"
API="${FLEXPOLL_API:-https://api.github.com/repos/FreeVN/FlexPoll/releases/latest}"
MODE="install"
CHANNEL="binary"

for arg in "$@"; do
  case "$arg" in
    --source) CHANNEL="source" ;;
    --binary) CHANNEL="binary" ;;
    --update) MODE="update" ;;
    --uninstall) MODE="uninstall" ;;
    --help|-h) sed -n '5,16p' "$0"; exit 0 ;;
    *) echo "onbekend argument: $arg" >&2; exit 1 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "graag met sudo (systemd-unit schrijven)" >&2
  exit 1
fi

write_unit() {
  local exec_start
  if [[ "$CHANNEL" == "source" ]]; then
    exec_start="$DIR/.venv/bin/python $DIR/app.py"
  else
    exec_start="$DIR/flexpoll"
  fi
  cat > "/etc/systemd/system/$SERVICE.service" <<UNIT
[Unit]
Description=FlexPoll — Modbus RTU / TCP / BACnet Diagnostic Suite
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USERNAME
WorkingDirectory=$DIR
ExecStart=$exec_start --host 0.0.0.0 --port $PORT --no-browser
Restart=always
RestartSec=2
Environment=PYTHONUNBUFFERED=1
Environment=FLEXPOLL_DATA=$DIR/data

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
}

# x86_64 -> x64, aarch64 -> arm64. 32-bit ARM heeft geen build; dan liever
# eerlijk stoppen met de verwijzing naar --source dan een verkeerde tarball.
asset_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo "x64" ;;
    aarch64|arm64) echo "arm64" ;;
    *) return 1 ;;
  esac
}

fetch_binary() {
  local arch url tmp
  arch="$(asset_arch)" || {
    echo "geen kant-en-klare build voor $(uname -m) — gebruik --source" >&2
    exit 1
  }
  command -v curl >/dev/null || { echo "curl ontbreekt: apt install curl" >&2; exit 1; }

  if [[ -n "${FLEXPOLL_VERSION:-}" ]]; then
    local tag="v${FLEXPOLL_VERSION#v}"
    url="https://github.com/FreeVN/FlexPoll/releases/download/$tag/FlexPoll-$tag-linux-$arch.tar.gz"
  else
    command -v python3 >/dev/null || { echo "python3 nodig om de laatste versie op te vragen" >&2; exit 1; }
    url="$(curl -fsSL "$API" | python3 -c '
import json,sys
d=json.load(sys.stdin); arch=sys.argv[1]
a=[x for x in d["assets"] if x["name"].endswith(f"linux-{arch}.tar.gz")]
print(a[0]["browser_download_url"] if a else "")' "$arch")"
    [[ -n "$url" ]] || { echo "geen linux-$arch-asset in de laatste release" >&2; exit 1; }
  fi

  echo "== downloaden: $url"
  tmp="$(mktemp -d)"
  # ${tmp:-}: bij `set -u` klaagt de EXIT-trap anders dat de lokale var weg is.
  trap 'rm -rf "${tmp:-}"' EXIT
  curl -fsSL "$url" -o "$tmp/flexpoll.tar.gz"
  tar -xzf "$tmp/flexpoll.tar.gz" -C "$tmp"
  mkdir -p "$DIR"
  # De tarball bevat één map FlexPoll/ met daarin flexpoll + _internal/.
  cp -a "$tmp"/FlexPoll/. "$DIR"/
  chmod +x "$DIR/flexpoll"
  # PyInstaller legt VERSION in _internal/; naast de binary is het leesbaarder
  # (het script en de gebruiker kijken daar).
  if [[ -f "$DIR/_internal/VERSION" ]]; then
    cp -f "$DIR/_internal/VERSION" "$DIR/VERSION"
  fi
  echo "== uitgepakt in $DIR"
}

if [[ "$MODE" == "uninstall" ]]; then
  systemctl disable --now "$SERVICE" 2>/dev/null || true
  rm -f "/etc/systemd/system/$SERVICE.service"
  systemctl daemon-reload
  echo "service weg. De config staat er nog: $DIR/data — zelf opruimen mag."
  exit 0
fi

if [[ "$MODE" == "update" ]]; then
  if [[ -d "$DIR/.git" ]]; then
    cd "$DIR"
    git pull --ff-only
    "$DIR/.venv/bin/pip" -q install -r requirements.txt
    CHANNEL="source"
  elif [[ -x "$DIR/flexpoll" ]]; then
    fetch_binary
    CHANNEL="binary"
  else
    echo "$DIR is geen FlexPoll-installatie (geen git-checkout, geen binary)" >&2
    exit 1
  fi
  write_unit
  systemctl restart "$SERVICE"
  sleep 2
  systemctl is-active "$SERVICE"
  curl -s -o /dev/null -w "HTTP %{http_code}\n" "http://127.0.0.1:$PORT/" || true
  echo "bijgewerkt naar $(cat "$DIR/VERSION" 2>/dev/null || echo '?') op http://$(hostname -I | awk '{print $1}'):$PORT"
  exit 0
fi

# --- verse installatie -------------------------------------------------------
mkdir -p "$DIR/data"
if [[ "$CHANNEL" == "source" ]]; then
  command -v git >/dev/null || { echo "git ontbreekt: apt install git" >&2; exit 1; }
  command -v python3 >/dev/null || { echo "python3 ontbreekt: apt install python3 python3-venv" >&2; exit 1; }

  if [[ -d "$DIR/.git" ]]; then
    echo "== bestaande checkout bijwerken =="
    git -C "$DIR" pull --ff-only
  else
    echo "== klonen naar $DIR =="
    mkdir -p "$(dirname "$DIR")"
    # --depth 1: de volledige geschiedenis heeft een testbank niet nodig.
    git clone --depth 1 --branch "$BRANCH" "$REPO" "$DIR"
  fi

  echo "== venv =="
  [[ -d "$DIR/.venv" ]] || python3 -m venv "$DIR/.venv"
  "$DIR/.venv/bin/pip" -q install --upgrade pip
  "$DIR/.venv/bin/pip" -q install -r "$DIR/requirements.txt"
else
  fetch_binary
fi

echo "== rechten =="
# De config hoort van de service-gebruiker te zijn, niet van root: anders kan de
# app na een update niet meer schrijven en valt je opstelling stil terug.
chown -R "$USERNAME":"$USERNAME" "$DIR/data" 2>/dev/null || true

echo "== service =="
write_unit
systemctl enable --now "$SERVICE"
sleep 2

echo
systemctl is-active "$SERVICE"
curl -s -o /dev/null -w "HTTP %{http_code}\n" "http://127.0.0.1:$PORT/" || true
echo "FlexPoll $(cat "$DIR/VERSION" 2>/dev/null || echo '?') draait op http://$(hostname -I | awk '{print $1}'):$PORT"
echo
echo "Seriële poort? Voeg $USERNAME toe aan de juiste groep:"
echo "  sudo usermod -aG dialout $USERNAME && sudo systemctl restart $SERVICE"
