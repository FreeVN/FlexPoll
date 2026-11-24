# AGENTS.md — FlexPoll

Dit project valt onder de multi-agent pipeline. De volledige regels staan in
`/root/dev-orchestrator/AGENTS.md`; hieronder de projectspecifieke aanvulling.

## Project
- Naam: FlexPoll
- Remote: http://luc:mx600@192.168.20.40:3000/luc/flexpoll.git
- Hoofdbranch: main

## Werkwijze
- Elke taak: branch `feat|fix/<T-xxx>-<naam>` vanuit `main`.
- Architect plant, Coder implementeert in een worktree, Reviewer keurt read-only.
- Geen sub-agent pusht; merge alleen door Luc na APPROVED.

## Tests
- Commando: `.venv/bin/python -m pytest -q`
- Verplicht groen voor een commit van de Coder en voor elke merge.
