# BBMD-lab: bewijst BACnet/IP over een router

Deze opstelling test de **Foreign Device**-kant van FlexPoll tegen een **echte,
onafhankelijke BBMD** (bacpypes3 `BIPBBMD`) en een **echt BACnet-toestel**
(bacpypes3 `Application`, device 2001). Geen simulatie van onszelf.

```
   neta 172.28.10.0/24            host routeert            netb 172.28.20.0/24
   ┌──────────────────┐        (broadcast blijft           ┌──────────────────────┐
   │ flexpoll .10     │ ───────  binnen de brug)  ────────► │ device 2001   .10    │
   │  (foreign dev)   │                                    │ BBMD 3001     .11    │
   └──────────────────┘                                    └──────────────────────┘
```

De twee bruggen zijn twee L2-segmenten: een **broadcast** (Who-Is) geraakt nooit
aan de andere kant, **unicast** (ReadProperty, en de I-Am van het toestel) wel.
Dat is precies de situatie op een werf met VLAN's.

## Draaien

```sh
cd tests/bbmd-lab
docker compose up -d --build
sudo ./setup-host.sh          # Docker-isolatie + SNAT uitzetten voor deze netten
open http://<host>:18099      # BACnet-tab
```

Daarna in de UI:

1. **Toestel op IP** `172.28.20.10` → werkt zonder BBMD (lezen is unicast).
2. **Scannen** zonder BBMD → *geen toestel* (verwacht: broadcast komt niet over).
3. **BBMD** `172.28.20.11`, poort 47808, TTL 60, **Aanmelden** → status
   "aangemeld bij … · nog 60s".
4. Opnieuw **scannen** → device **2001** (en 3001, de BBMD zelf).
5. Punten van 2001 lezen: AI 21.5 °C, AV 22.0 °C, BV aan.

Opruimen: `sudo ./teardown-host.sh && docker compose down`.

## Wat deze test al gevonden heeft

- **Register-Foreign-Device was fout opgebouwd.** Het is een BVLC-functie:
  `81 05 00 06 <ttl 2>` (zes bytes). De eerste versie stuurde
  `81 0A 00 06 05 <ttl>` — original-unicast met 0x05 in de payload. Onze eigen
  fake-BBMD slikte dat, een echte BBMD negeert het volledig → timeout.
- **Na de registratie moet de Who-Is ook naar de BBMD.** Een lokale broadcast
  bereikt hem nooit; de client moet hem als **Forwarded-NPDU** (`0x04`) sturen.
  Zonder die stap vind je niets, ook al is de registratie perfect gelukt.
- **Verrijking mag het ontvangstvenster niet opeten.** Naam/model lezen kost
  tijd; deed je dat binnen de scan-lus, dan viel het tweede (echte) toestel
  buiten de deadline en zag je alleen de BBMD.
- **De BBMD moet zichzelf in zijn BDT hebben** (bacpypes3-eigenschap): anders
  zendt hij een binnengekomen Forwarded-NPDU niet lokaal uit.
- **NAT breekt BBMD.** Met Docker's standaard-SNAT ziet de BBMD de foreign
  device als de brug-gateway (172.28.20.1); de BVLC-Result gaat dan naar de
  host in plaats van naar de container. Vandaar de `return`-regel in
  `setup-host.sh`.

## Grenzen

- Dit is een **handmatige labtest**, geen CI: hij vraagt Docker, root-rechten op
  de host en vrije subnetten `172.28.10.0/24` / `172.28.20.0/24`.
- Eén BBMD, geen BDT tussen meerdere BBMD's en geen NAT-scenario (dat is nu net
  wat niet werkt).
- Draait op een Docker-host, niet in de LXC: daar is geen daemon.
