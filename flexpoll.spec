# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
#
# PyInstaller-spec voor de zelfstandige builds (Windows .exe, Linux binary,
# macOS .app). Onedir, geen onefile: onefile pakt bij elke start uit naar %TEMP%
# en dat geeft valse antivirusmeldingen en trage starts.
#
#   pyinstaller flexpoll.spec
#
# De config komt niet naast de binary maar in de gegevensmap van de gebruiker
# (zie app.py::_data_dir). static/ en VERSION gaan mee in de bundel.

import os

block_cipher = None

datas = [
    ("static", "static"),
    ("VERSION", "."),
    ("LICENSE", "."),
    ("NOTICE", "."),
]
# De server levert ook de iconen en fonts uit static/ — die zitten er via de map
# hierboven al in. docs/ gaat niet mee.

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["serial", "serial.tools.list_ports", "mstp"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Alleen wat zeker ongebruikt is. `email` en `http.cookiejar` hier weggooien
    # breekt http.server en urllib — die imports zijn er indirect.
    excludes=["tkinter", "unittest", "pydoc", "test"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="flexpoll",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # de server print zijn URL en configpad
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="docs/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FlexPoll",
)
