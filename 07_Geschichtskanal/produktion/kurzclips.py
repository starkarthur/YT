"""Schneidet aus einem fertigen Langvideo Hochkant-Kurzclips (1080x1920) für TikTok, Reels und Shorts.

Aufruf: python kurzclips.py <video.mp4> <zielordner> <titel> <von-bis,von-bis,...>   (Sekunden, z. B. 129.27-147.97)
Aufbau: unscharfer, abgedunkelter Hintergrund aus dem Video, darüber das Bild in 135 % Breite (Ränder beschnitten),
oben der Titel in zwei Zeilen, unten der Hinweis auf das ganze Video. Kein Upload.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SCHRIFT = "Montserrat ExtraBold"
HINWEIS = "Full video on YouTube  |  Echoes of Earth"


def titelzeilen(titel: str) -> tuple[str, str]:
    """„Why You'd Never Survive Pompeii“ → („WHY YOU'D NEVER“, „SURVIVE POMPEII“)."""
    w = titel.upper().split()
    return (" ".join(w[:3]), " ".join(w[3:])) if len(w) > 3 else (titel.upper(), "")


def befehl(video: Path, ziel: Path, a: float, b: float, texte: Path) -> list[str]:
    t = lambda n: (texte / n).as_posix().replace(":", "\\:")
    schrift = f"font='{SCHRIFT}':fontcolor=0xEFE3C8:borderw=4:bordercolor=0x14101A"
    vf = (
        "[0:v]split=2[h][v];"
        "[h]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:4,eq=brightness=-0.28:saturation=0.8[hg];"
        "[v]scale=1458:-2,crop=1080:ih[vg];"
        "[hg][vg]overlay=0:(H-h)/2,"
        f"drawtext=textfile='{t('z1.txt')}':{schrift}:fontsize=76:x=(w-text_w)/2:y=300,"
        f"drawtext=textfile='{t('z2.txt')}':{schrift}:fontsize=96:x=(w-text_w)/2:y=392,"
        f"drawtext=textfile='{t('cta.txt')}':{schrift}:fontsize=40:x=(w-text_w)/2:y=1500,"
        "fade=t=in:st=0:d=0.25[out]"
    )
    d = b - a
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{a:.3f}", "-t", f"{d:.3f}", "-i", str(video),
            "-filter_complex", vf, "-map", "[out]", "-map", "0:a",
            "-af", f"afade=t=in:st=0:d=0.2,afade=t=out:st={max(d - 0.35, 0):.2f}:d=0.35,loudnorm=I=-14:TP=-1.5:LRA=11",
            "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "8M", "-bufsize", "16M",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(ziel)]


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(__doc__)
        return 2
    video, ordner, titel, bereiche = Path(argv[0]), Path(argv[1]), argv[2], argv[3]
    if not re.fullmatch(r"[A-Za-z0-9' ]{3,80}", titel):
        print("Titel: nur Buchstaben, Ziffern, Leerzeichen und Apostroph")
        return 2
    teile = []
    for stueck in bereiche.split(","):
        m = re.fullmatch(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)", stueck.strip())
        if not m or not 5 <= float(m[2]) - float(m[1]) <= 60:
            print(f"Bereich ungültig (5–60 s): {stueck}")
            return 2
        teile.append((float(m[1]), float(m[2])))
    ordner.mkdir(parents=True, exist_ok=True)
    z1, z2 = titelzeilen(titel)
    for name, text in (("z1.txt", z1), ("z2.txt", z2), ("cta.txt", HINWEIS)):
        (ordner / name).write_text(text, encoding="utf-8")
    for n, (a, b) in enumerate(teile, 1):
        ziel = ordner / f"kurzclip_{n}.mp4"
        subprocess.run(befehl(video, ziel, a, b, ordner), check=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{(b - a) / 2:.2f}", "-i", str(ziel),
                        "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "4", str(ordner / f"kurzclip_{n}.jpg")], check=True)
        print(f"kurzclip_{n}.mp4: {b - a:.1f} s, {ziel.stat().st_size / 1e6:.1f} MB")
    for name in ("z1.txt", "z2.txt", "cta.txt"):
        (ordner / name).unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
