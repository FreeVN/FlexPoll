# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
#
# FlexPoll als container. De config hoort in een volume, anders ben je bij elke
# recreate je opstelling kwijt. Draai vanuit de repo-root (de context is de
# repo, niet deze map):
#
#   docker build -f docker/Dockerfile -t flexpoll .
#   docker run -d --name flexpoll -p 8099:8099 \
#     --device /dev/ttyUSB0 --group-add dialout \
#     -v flexpoll-data:/data flexpoll
#
# Seriële poort: geef het device mee (`--device`) én de groep waar de poort
# bij hoort (`--group-add dialout` op Debian/Ubuntu, `uucp` op Arch). Zonder dat
# tweede kan de container de poort zien maar niet openen.
# BACnet/IP heeft `--network host` nodig, anders gaan de UDP-broadcasts de deur
# niet uit en zie je geen toestellen.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FLEXPOLL_DATA=/data

WORKDIR /opt/flexpoll

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py devices.py modbus_rtu.py modbus_tcp.py bacnet.py sim.py ./
COPY VERSION LICENSE NOTICE README.md ./
COPY static ./static

RUN useradd --system --uid 10001 --no-create-home flexpoll \
 && mkdir -p /data && chown flexpoll:flexpoll /data

USER flexpoll
EXPOSE 8099
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8099/api/state',timeout=2).status==200 else 1)"

CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "8099"]
