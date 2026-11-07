# SPDX-License-Identifier: AGPL-3.0-only
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir bacpypes3 pyserial
WORKDIR /app
