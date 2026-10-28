# FlexPoll — klein houden, niets breken.
# De tool belooft: Python-stdlib + pyserial, geen build-stap. Deze targets
# gebruiken daarom een venv in de repo en doen niets dat je niet zelf kan typen.

PY ?= .venv/bin/python
PORT ?= 8098

.PHONY: help venv check lint smoke run sim release dist docker clean

help:
	@echo "make venv     — .venv aanmaken en pyserial installeren"
	@echo "make check    — syntaxis, versie-consistentie, licentieheaders"
	@echo "make smoke    — simulator starten en /api/state bevragen"
	@echo "make run      — app op :8099 tegen de echte bus"
	@echo "make sim      — app op :$(PORT) met de simulator"
	@echo "make release V=1.1.0 — versie bumpen, changelog, commit, tag"
	@echo "make dist     — zelfstandige build voor dit OS (dist/FlexPoll/)"
	@echo "make docker   — container-image bouwen"

venv:
	python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

check:
	$(PY) -c "import ast,sys; [ast.parse(open(f,encoding='utf-8').read(),f) for f in sys.argv[1:]]" \
		app.py devices.py modbus_rtu.py modbus_tcp.py bacnet.py sim.py modbus_tcp_slave.py tests/bacnet_slave.py
	node --check static/app.js
	@v=$$(cat VERSION); \
	  test "$$($(PY) app.py --version)" = "FlexPoll $$v" || { echo "VERSION wijkt af van --version"; exit 1; }; \
	  grep -q "^## \[$$v\]" CHANGELOG.md || { echo "CHANGELOG mist $$v"; exit 1; }; \
	  echo "versie $$v consistent"
	@test -z "$$(git ls-files '*.py' '*.js' '*.css' | xargs grep -L 'SPDX-License-Identifier: AGPL-3.0-only')" \
	  || { echo "SPDX-header ontbreekt (zie boven)"; exit 1; }
	@echo "check ok"

smoke:
	$(PY) scripts/smoke.py --port 0

run:
	$(PY) app.py --host 0.0.0.0 --port 8099

sim:
	MODBUS_SIM=1 $(PY) app.py --port $(PORT)

release:
	@test -n "$(V)" || { echo "gebruik: make release V=1.1.0"; exit 1; }
	scripts/release.sh $(V)

# Zelfstandige build voor het OS waarop je dit draait (PyInstaller bouwt niet
# cross-platform — de release-workflow doet de drie samen).
dist:
	$(PY) -m pip -q install pyinstaller
	$(PY) -m PyInstaller --noconfirm --clean flexpoll.spec
	@echo "klaar: dist/FlexPoll/"

docker:
	docker build -t flexpoll:$(shell cat VERSION) -t flexpoll:latest .
	@echo "gereden: docker run --rm -p 8099:8099 flexpoll:latest"

clean:
	rm -rf __pycache__ .ruff_cache /tmp/flexpoll-state.json
