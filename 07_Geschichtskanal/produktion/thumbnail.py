"""Baut ein YouTube-Vorschaubild (1280x720) aus einem vorhandenen Bild und zwei Textzeilen.

Aufruf: python thumbnail.py <bild> <ziel.jpg> <zeile1> <zeile2>
Zeile 1 klein in Weiß, Zeile 2 groß in Gelb, beide links unten mit dicker dunkler Kontur. Höchstens 4 Wörter insgesamt,
damit es auch auf dem Handy lesbar bleibt.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SCHRIFT = "Montserrat Black"


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    bild, ziel, z1, z2 = Path(argv[0]), Path(argv[1]), argv[2].upper(), argv[3].upper()
    for z in (z1, z2):
        if not re.fullmatch(r"[A-Z0-9' ]{1,22}", z):
            print("Text: nur Buchstaben, Ziffern, Leerzeichen und Apostroph, höchstens 22 Zeichen je Zeile")
            return 2
    ziel.parent.mkdir(parents=True, exist_ok=True)
    t1, t2 = ziel.with_name("t1.txt"), ziel.with_name("t2.txt")
    t1.write_text(z1, encoding="utf-8")
    t2.write_text(z2, encoding="utf-8")
    pfad = lambda p: p.as_posix().replace(":", "\\:")
    kontur = "borderw=10:bordercolor=0x0B0A10:shadowcolor=black@0.6:shadowx=6:shadowy=6"
    vf = ("scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
          "eq=contrast=1.12:saturation=1.25:brightness=-0.03,vignette=PI/4.5,"
          "drawbox=x=0:y=430:w=1280:h=290:color=black@0.35:t=fill,"
          f"drawtext=textfile='{pfad(t1)}':font='{SCHRIFT}':fontcolor=white:fontsize=92:x=56:y=440:{kontur},"
          f"drawtext=textfile='{pfad(t2)}':font='{SCHRIFT}':fontcolor=0xFFD21E:fontsize=168:x=50:y=532:{kontur}")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(bild), "-vf", vf, "-frames:v", "1",
                    "-q:v", "2", str(ziel)], check=True)
    t1.unlink()
    t2.unlink()
    print(f"{ziel.name}: {ziel.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
