# SPDX-License-Identifier: AGPL-3.0-only
# Copyright 2026 Free van Nieuwenhove
"""Zet genummerde aanduidingen op de schermafbeeldingen van de handleiding.

    python3 docs/shots/annotate.py

Leest de ruwe opnames uit `docs/shots/raw/` en schrijft de bewerkte versies
naar `docs/assets/`. De coördinaten staan hieronder: pas je de UI aan, dan
verschuif je enkel het cijfer — niet de hele handleiding.

Waarom niet in de screenshot zelf tekenen (bv. in een fotobewerker)? Omdat
de cijfers dan bij elke UI-wijziging opnieuw met de hand gezet moeten worden,
en niemand weet welke versie de juiste is. Zo is het één bestand met alle
coördinaten, in de repo, met geschiedenis.
"""

from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "docs" / "shots" / "raw"
OUT = ROOT / "docs" / "assets"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Per afbeelding: (crop-box of None, [(nummer, x, y), ...]).
# Coördinaten zijn in de oorspronkelijke opname (1440 px breed).
SPECS = {
    "01-overview": (
        (0, 60, 1440, 900),
        [
            (1, 49, 215),       # adapter kiezen
            (2, 353, 215),      # baudrate
            (3, 481, 215),      # pariteit
            (4, 725, 215),      # verbinden
            (5, 981, 215),      # scanbereik
            (6, 1119, 215),     # framing zoeken
            (7, 1234, 215),     # adressen scannen
            (8, 382, 350),      # modulekaart
            (9, 353, 878),      # buslog
        ],
    ),
    "02-scan": (
        (0, 200, 1440, 330),
        [
            (1, 60, 232),       # kop van de scanbalk
            (2, 185, 232),      # gevonden toestel + confidence
            (3, 330, 232),      # direct toevoegen
        ],
    ),
    "03-tcp": (
        (0, 60, 1440, 700),
        [
            (1, 30, 272),       # palet met TCP-toestellen
            (2, 365, 190),      # leeg canvas
        ],
    ),
    "04-bacnet": (
        (0, 60, 1440, 320),
        [
            (1, 85, 192),       # subnet-broadcast
            (2, 288, 192),      # zoeken
            (3, 438, 205),      # automatisch gevonden broadcast
        ],
    ),
}


def draw_number(d: ImageDraw.ImageDraw, n: int, x: int, y: int) -> None:
    r = 13
    # Witte rand zodat het cijfer ook op een donkere knop leesbaar blijft.
    d.ellipse((x - r - 3, y - r - 3, x + r + 3, y + r + 3), fill=(255, 255, 255))
    d.ellipse((x - r, y - r, x + r, y + r), fill=(200, 16, 46), outline=(255, 255, 255), width=2)
    font = ImageFont.truetype(FONT, 18)
    txt = str(n)
    box = d.textbbox((0, 0), txt, font=font)
    d.text((x - (box[2] - box[0]) / 2 - box[0], y - (box[3] - box[1]) / 2 - box[1]),
           txt, font=font, fill=(255, 255, 255))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (crop, marks) in SPECS.items():
        src = RAW / f"{name}.png"
        if not src.exists():
            print(f"  ! ontbreekt: {src}")
            continue
        img = Image.open(src).convert("RGB")
        if crop:
            img = img.crop(crop)
            marks = [(n, x - crop[0], y - crop[1]) for n, x, y in marks]
        d = ImageDraw.Draw(img)
        for n, x, y in marks:
            draw_number(d, n, x, y)
        dest = OUT / f"{name}.png"
        img.save(dest, optimize=True)
        print(f"  {dest.relative_to(ROOT)}  {img.size[0]}×{img.size[1]}")


if __name__ == "__main__":
    main()
