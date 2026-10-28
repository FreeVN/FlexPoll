# Bijdragen aan FlexPoll

Dank dat je meekijkt. FlexPoll is een diagnose-tool voor HVAC-veldbussen: hij
leest en schrijft naar echte toestellen, dus een fout kost iemand een namiddag
op de werf. Wees precies, en liever één bewezen wijziging dan drie plausibele.

## Waar je op let

1. **Status mag nooit liegen.** Groen betekent "dit werkt echt". Een reader die
   fouten per punt opvangt en daarna vrolijk terugkeert, meldt een dode lijn als
   online — dat is de ergste bug die deze tool kan hebben.
2. **Nooit een waarde verzinnen.** Als een toestel iets niet kan (BACnet-Vmid is
   geen Modbus-register), dan zegt de UI dat. Een plausibele schatting die als
   meting wordt getoond, is fout.
3. **Geen nieuwe dependencies** zonder goede reden. De belofte is: Python-stdlib
   plus `pyserial`, één proces, geen build-stap.
4. **Geen transporten mengen.** RTU, TCP en BACnet hebben elk hun eigen tab en
   hun eigen modulelijst.

## Lokaal draaien

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
MODBUS_SIM=1 .venv/bin/python app.py --port 8098    # http://localhost:8098
```

De simulator (`sim.py`) is de nep-bus. Voeg daar een testslave toe in plaats van
naar echte hardware te schrijven, en houd de seeds gelijk aan het echte toestel:
een simulator die andere registers kent dan het toestel verbergt juist de fouten
die je zoekt.

## Voor je een pull request opent

```bash
make check      # syntaxis, versie-consistentie en licentieheaders
make smoke      # simulator starten en /api/state bevragen
```

- Eén onderwerp per PR, met een uitleg *waarom* — niet alleen *wat*.
- Raakt je wijziging een tegel of een transport? Zet in de PR-beschrijving hoe je
  het getest hebt (sim, testslave of echt toestel met merk/type/firmware).
- Wijzig je de versie? Pas `VERSION`, `CHANGELOG.md` en de tag samen aan. De
  CI faalt als die drie uit elkaar lopen.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/nl/):
`fix:`, `feat:`, `docs:`, `refactor:`, `test:`, `chore:`. In de body: wat er
kapot was en hoe je het vaststelde.

## Licentie van je bijdrage

Je bijdrage valt onder **AGPL-3.0-only**, de licentie van het project. Door een
PR te openen verklaar je dat je het recht hebt om die code onder die licentie te
leveren.

## Beleefdheid

Zie [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md). Kort: discussieer over de code,
niet over de persoon.

## Een beveiligingsprobleem?

Niet in een publieke issue — zie [`SECURITY.md`](SECURITY.md).
