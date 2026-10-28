#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
#
# FlexPoll installeren of bijwerken op een Linux-doos (Pi, LXC, gewone pc).
#
#   sudo scripts/install.sh                 # installeert in /opt/flexpoll, poort 8099
#   sudo scripts/install.sh --update        # git pull + herstart
#   sudo scripts/install.sh --uninstall     # service weg, data blijft
#
# Wat het doet: repo klonen (of pullen), venv + pyserial, systemd-unit schrijven,
# service enablen en starten, en de URL printen. De config blijft in
# <dir>/data en overleeft een update of een herinstallatie.
set -euo pipefail

DIR="${FLEXPOLL_DIR:-/opt/flexpoll}"
PORT="${FLEXPOLL_PORT:-8099}"
USERNAME="${FLEXPOLL_USER:-${SUDO_USER:-$(id -un)}}"
SERVICE="flexpoll"
REPO="${FLEXPOLL_REPO:-https://github.com/fvannieuwenhove/flexpoll.git}"
BRANCH="${FLEXPOLL_BRANCH:-main}"
MODE="install"

for arg in "$@"; do
  case "$arg" in
    --update) MODE="update" ;;
    --uninstall) MODE="uninstall" ;;
    --help|-h) sed -n '5,12p' "$0"; exit 0 ;;
    *) echo "onbekend argument: $arg" >&2; exit 1 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "graag met sudo (systemd-unit schrijven)" >&2
  exit 1
fi

write_unit() {
  cat > "/etc/systemd/system/$SERVICE.service" <<UNIT
[Unit]
Description=FlexPoll — Modbus RTU / TCP / BACnet Diagnostic Suite
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USERNAME
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python $DIR/app.py --host 0.0.0.0 --port $PORT --no-browser
Restart=always
RestartSec=2
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
}

if [[ "$MODE" == "uninstall" ]]; then
  systemctl disable --now "$SERVICE" 2>/dev/null || true
  rm -f "/etc/systemd/system/$SERVICE.service"
  systemctl daemon-reload
  echo "service weg. De config staat er nog: $DIR/data — zelf opruimen mag."
  exit 0
fi

if [[ "$MODE" == "update" ]]; then
  [[ -d "$DIR/.git" ]] || { echo "$DIR is geen git-checkout" >&2; exit 1; }
  cd "$DIR"
  git pull --ff-only
  "$DIR/.venv/bin/pip" -q install -r requirements.txt
  write_unit
  systemctl restart "$SERVICE"
  sleep 2
  systemctl is-active "$SERVICE"
  curl -s -o /dev/null -w "HTTP %{http_code}\n" "http://127.0.0.1:$PORT/" || true
  echo "bijgewerkt naar $(cat "$DIR/VERSION") op http://$(hostname -I | awk '{print $1}'):$PORT"
  exit 0
fi

# --- verse installatie -------------------------------------------------------
command -v git >/dev/null || { echo "git ontbreekt: apt install git" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 ontbreekt: apt install python3 python3-venv" >&2; exit 1; }

if [[ -d "$DIR/.git" ]]; then
  echo "== bestaande checkout bijwerken =="
  git -C "$DIR" pull --ff-only
else
  echo "== klonen naar $DIR =="
  mkdir -p "$(dirname "$DIR")"
  git clone --branch "$BRANCH" "$REPO" "$DIR"
fi

echo "== venv =="
[[ -d "$DIR/.venv" ]] || python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" -q install --upgrade pip
"$DIR/.venv/bin/pip" -q install -r "$DIR/requirements.txt"

echo "== rechten =="
# De config hoort van de service-gebruiker te zijn, niet van root: anders kan de
# app na een update niet meer schrijven en valt je opstelling stil terug.
mkdir -p "$DIR/data"
chown -R "$USERNAME":"$USERNAME" "$DIR/data" 2>/dev/null || true

echo "== service =="
write_unit
systemctl enable --now "$SERVICE"
sleep 2

echo
systemctl is-active "$SERVICE"
curl -s -o /dev/null -w "HTTP %{http_code}\n" "http://127.0.0.1:$PORT/" || true
echo "FlexPoll $(cat "$DIR/VERSION") draait op http://$(hostname -I | awk '{print $1}'):$PORT"
echo
echo "Seriële poort? Voeg $USERNAME toe aan de juiste groep:"
echo "  sudo usermod -aG dialout $USERNAME && sudo systemctl restart $SERVICE"
