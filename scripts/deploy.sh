#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
#
# FlexPoll deployen naar een remote host: backup, code overschrijven (zonder
# data/), service herstarten en functioneel controleren.
#
#   DEST_HOST=pi@192.168.1.50 scripts/deploy.sh
#
# Vereist: ssh-toegang zonder wachtwoord, sudo-rechten voor systemctl op de host.
# De config in $DEST/data/ blijft staan — die hoort bij de opstelling, niet bij de code.
set -euo pipefail

SRC="${SRC:-$(cd "$(dirname "$0")/.." && pwd)}"
DEST_HOST="${DEST_HOST:?zet DEST_HOST, bv. DEST_HOST=pi@192.168.1.50}"
DEST="${DEST:-/opt/flexpoll}"
SERVICE="${SERVICE:-flexpoll}"
PORT="${PORT:-8099}"

echo "== bron =="
cd "$SRC"
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  echo "LET OP: werkboom heeft niet-gecommitte wijzigingen — die gaan mee zoals ze zijn."
fi

echo "== backup =="
ssh "$DEST_HOST" "cp -a $DEST $DEST.bak-\$(date +%Y%m%d-%H%M)" 2>/dev/null || true

echo "== code =="
tar czf - --exclude data --exclude __pycache__ --exclude .git --exclude .venv . \
  | ssh "$DEST_HOST" "tar xzf - -C $DEST"

echo "== herstart =="
ssh "$DEST_HOST" "sudo systemctl restart $SERVICE && sleep 3 && systemctl is-active $SERVICE"

echo "== health =="
ssh "$DEST_HOST" "curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:$PORT/ ; curl -s http://127.0.0.1:$PORT/api/state | head -c 120; echo"
