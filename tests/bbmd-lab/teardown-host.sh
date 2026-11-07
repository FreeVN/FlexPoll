#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
#
# Verwijdert alle host-regels die setup-host.sh toevoegde (herkenbaar aan de
# comment-tag). Draai dit vóór `docker compose down`, of erna — de regels
# verwijzen enkel naar subnetten, niet naar interfaces.
set -eu

TAG=flexpoll-bbmd-lab
removed=0

for pair in "ip raw PREROUTING" "ip filter DOCKER-ISOLATION-STAGE-2" "ip nat POSTROUTING"; do
    set -- $pair
    family=$1; table=$2; chain=$3
    handles=$(nft -a list chain "$family" "$table" "$chain" 2>/dev/null \
        | grep "$TAG" | sed -n 's/.*# handle \([0-9]*\).*/\1/p')
    for h in $handles; do
        nft delete rule "$family" "$table" "$chain" handle "$h"
        echo "  - $family $table $chain handle $h"
        removed=$((removed + 1))
    done
done

echo "opgeruimd ($removed regels)"
