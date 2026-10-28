#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
"""Rooktest: start de app met de simulator, bevraag de API, en ruim op.

Bewijst dat het proces opstart, dat de statische bestanden geserveerd worden en
dat /api/state een versie en een gevulde config teruggeeft. Geen hardware nodig,
geen poort 8099 — gebruikt een vrije poort.

    python3 scripts/smoke.py [--port 8098]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def get(path: str, port: int) -> tuple[int, bytes]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=3) as resp:
        return resp.status, resp.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0, help="0 = vrije poort kiezen")
    args = parser.parse_args()
    port = args.port or free_port()

    # Eigen, lege config-map: de rooktest mag nooit de echte opstelling laden of
    # overschrijven (die van de gebruiker of die van de CI-cache).
    data_dir = tempfile.mkdtemp(prefix="flexpoll-smoke-")
    env = {**os.environ, "MODBUS_SIM": "1", "PYTHONUNBUFFERED": "1",
           "FLEXPOLL_DATA": data_dir}
    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "app.py"), "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    try:
        state = None
        for _ in range(60):
            if proc.poll() is not None:
                print("app stopte met code", proc.returncode)
                print(proc.stdout.read() if proc.stdout else "")
                return 1
            try:
                status, body = get("/api/state", port)
                if status == 200:
                    state = json.loads(body)
                    break
            except OSError:
                pass
            time.sleep(0.25)

        if state is None:
            print("FAIL: /api/state antwoordde niet binnen 15 s")
            return 1

        status, html = get("/", port)
        checks = [
            ("api/state 200", status == 200 and "<title>FlexPoll" in html.decode("utf-8", "replace")),
            ("versie aanwezig", bool(state.get("version"))),
            ("simulator actief", state.get("simulate") is True),
            ("config geladen", isinstance(state.get("modules"), list)),
            ("busblok aanwezig", isinstance(state.get("bus"), dict)),
        ]
        for name, ok in checks:
            print(("ok   " if ok else "FAIL ") + name)
        if not all(ok for _, ok in checks):
            return 1

        print(f"smoke ok — FlexPoll {state['version']}, "
              f"{len(state['modules'])} module(s), poort {port}")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
