## Wat en waarom

<!-- Eén onderwerp. Wat was er kapot of wat ontbrak, en waarom deze oplossing. -->

## Hoe getest

<!-- Vink aan wat van toepassing is en vul het toestel in. -->

- [ ] Simulator (`MODBUS_SIM=1`)
- [ ] Testsleuf (`modbus_tcp_slave.py` / `tests/bacnet_slave.py`)
- [ ] Echt toestel — merk/type/firmware:

## Checklist

- [ ] `make check` is groen
- [ ] Status liegt niet: een module is pas online als er echt iets gelezen is
- [ ] Bij een nieuwe tegel: `TYPES` + `READERS`, `_norm_config`, `bodyHTML` + render + handler, en een seed in `sim.py`
- [ ] Geen nieuwe dependencies (behalve met reden in de PR-uitleg)
- [ ] `VERSION` + `CHANGELOG.md` aangepast als dit een release voorbereidt
- [ ] Geen klantgegevens, IP-adressen of `data/` in de diff
