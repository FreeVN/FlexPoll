# Aan de handleiding werken

Deze site wordt **uit de repo gebouwd** (MkDocs Material) en automatisch
gepubliceerd naar GitHub Pages bij elke push naar `main` die `docs/` of
`mkdocs.yml` raakt.

Waarom geen GitHub Wiki? Omdat een wiki een aparte git-repo is: hij staat los van
de code, heeft geen review, geen versiegeschiedenis naast de releases, en hij
veroudert zodra iemand de UI aanpast. Documentatie hoort bij de code die ze
beschrijft.

## Lokaal bekijken

```bash
python3 -m venv .venv-docs
.venv-docs/bin/pip install -r requirements-docs.txt
.venv-docs/bin/mkdocs serve      # http://127.0.0.1:8000
```

## Schermafbeeldingen met aantekeningen

De opnames komen uit de **simulator**, niet uit een echte installatie — zo staan
er geen klantgegevens, serienummers of IP-adressen van derden op.

```
docs/shots/raw/       # ruwe opnames (1440 px breed)
docs/shots/annotate.py  # zet de genummerde cirkels
docs/assets/          # wat de handleiding gebruikt
```

Opnieuw genereren na een UI-wijziging:

1. Start de app met de demo-config:

   ```bash
   FLEXPOLL_DATA=/tmp/flexpoll-docs flexpoll --simulate --port 18096
   ```

2. Zet de modules op de lijn (EM1.8U op 3, EM1.8R op 4, EM1.8D op 5, Belimo VAV
   op 6) — of laat ze uit je testconfig staan.
3. Maak opnames van 1440×900 en bewaar ze in `docs/shots/raw/` met dezelfde naam
   (`01-overview.png`, `02-scan.png`, …).
4. `python3 docs/shots/annotate.py` — de cijfers komen uit `SPECS` in dat script.
   Verschuift een knop, dan pas je alleen die coördinaat aan.

!!! tip "Cijfers in de tekst moeten kloppen met de cijfers op het beeld"
    Elke genummerde lijst onder een afbeelding verwijst naar de cirkels. Voeg je
    een stap toe, dan hoort daar een nieuw nummer bij — anders leest de
    handleiding als een puzzel.

## Stijl

- **Nederlands, informeel-technisch.** "Je klikt", niet "de gebruiker dient te
  klikken".
- **Wat de gebruiker ziet** is de bron van waarheid: knoplabels tussen
  **vet**, in dezelfde spelling als de UI.
- **Geen verkooppraat.** Wel eerlijk zijn over wat de tool niet kan.
- **Bèta blijft bèta**: nieuwe pagina's beginnen niet met "FlexPoll is een
  geavanceerde, toonaangevende…". Gewoon wat het doet.

## Wat updaten bij een nieuwe versie?

| Wijziging | Documentatie |
|---|---|
| Nieuwe knop of veld | Screenshot opnieuw + `SPECS` aanpassen + de bijhorende lijst |
| Nieuwe toestel-ondersteuning | Juiste protocolpagina (RTU/TCP/BACnet) aanvullen |
| Nieuwe installatiewijze | `installatie.md` + README |
| Bugfix zonder UI-wijziging | Meestal niets; hooguit `problemen.md` |

De versie zelf staat niet in de tekst maar in de badge op de startpagina
(`img.shields.io`), zodat ze nooit kan verouderen.
