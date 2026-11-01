# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
#
# Zelfde app, maar als één bestand: `flexpoll.exe` van ±9 MB.
#
#   pyinstaller flexpoll-onefile.spec
#
# Voor wie één bestand wil om ergens neer te zetten. De prijs staat in de
# README: bij elke start pakt de exe zichzelf uit naar %TEMP% (trager, meer
# antivirusruis). De onedir-zip blijft de aanbevolen download.
#
# Let op: dit spec wordt alleen op Windows gebruikt. Op Linux/macOS bouwen we
# onedir, omdat een onefile daar niets oplost en `--onefile` met een .ico
# sowieso niets doet.

import os

block_cipher = None

datas = [
    ("static", "static"),
    ("VERSION", "."),
    ("LICENSE", "."),
    ("NOTICE", "."),
]

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["serial", "serial.tools.list_ports", "mstp"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    a.binaries,
    a.datas,
    [],
    name="flexpoll",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,          # de server print zijn URL en configpad
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="docs/icon.ico",
)
