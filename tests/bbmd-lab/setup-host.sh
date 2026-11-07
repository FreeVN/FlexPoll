#!/bin/sh
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
#
# Host-voorbereiding voor de BBMD-labtest. Draai dit NA `docker compose up -d`
# (de bruggen moeten bestaan) en met root-rechten.
#
# Waarom dit nodig is:
#  * Docker zet op de `ip raw`-hook een drop-regel per container-IP
#    ("direct access": verkeer van buiten de eigen brug naar dat IP wordt
#    geweigerd). Zonder uitzondering geraakt een gerouteerd BACnet-pakket nooit
#    bij het toestel — je ziet timeouts terwijl het netwerk klopt.
#  * Tussen twee gebruiker-netwerken staat Docker-isolatie in de weg; die
#    moeten we voor deze twee subnetten doorlaten.
#  * Docker masseert verkeer tussen netwerken standaard (SNAT naar de
#    brug-gateway). BACnet/BBMD werkt met IP-adressen in de payload, dus NAT
#    breekt de registratie: de BBMD ziet de foreign device als 172.28.20.1.
#    Daarom een `return` vóór de masquerade-regel.
set -eu

A=172.28.10.0/24
B=172.28.20.0/24
TAG=flexpoll-bbmd-lab

add() {
    tag=$1; family=$2; table=$3; chain=$4; shift 4
    if nft -a list chain "$family" "$table" "$chain" | grep -q "$TAG-$tag"; then
        echo "  = $tag bestaat al"
        return
    fi
    nft insert rule "$family" "$table" "$chain" "$@" comment "$TAG-$tag"
    echo "  + $tag: $*"
}

echo "host-regels voor de BBMD-lab"
add raw-ab ip raw    PREROUTING               ip saddr $A ip daddr $B counter accept
add raw-ba ip raw    PREROUTING               ip saddr $B ip daddr $A counter accept
add iso-ab ip filter DOCKER-ISOLATION-STAGE-2 ip saddr $A ip daddr $B accept
add iso-ba ip filter DOCKER-ISOLATION-STAGE-2 ip saddr $B ip daddr $A accept
add nat-ab ip nat    POSTROUTING              ip saddr $A ip daddr $B counter return
add nat-ba ip nat    POSTROUTING              ip saddr $B ip daddr $A counter return

echo "klaar — test met: curl -s localhost:18099/api/state"
