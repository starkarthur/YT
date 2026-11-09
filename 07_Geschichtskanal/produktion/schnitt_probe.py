"""Kostenloser Echt-Test des Schnitts mit ffmpeg: künstliche Clips, Stimme, Musik und Geräusche (lavfi),
dann genau die Befehle aus schnitt.befehle. Keine API, keine Kosten. Aufruf: python schnitt_probe.py <ordner>"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import schnitt
from lauf import KONF
from plan_schema import lade_plan

HIER = Path(__file__).resolve().parent


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def main(ziel: Path) -> None:
    ziel.mkdir(parents=True, exist_ok=True)
    plan = lade_plan(HIER / "testdaten" / "Shorts" / "001_Eiffelturm-Kurz_plan.json")
    n = len(plan["einstellungen"])
    zeiten = [(i * 3.0, (i + 1) * 3.0) for i in range(n)]
    clips = []
    for i, e in enumerate(plan["einstellungen"]):
        if e.get("art") == "standbild":
            c = ziel / f"bild_{i}.png"
            ff("-f", "lavfi", "-i", "testsrc2=s=1080x1920", "-frames:v", "1", str(c))
        else:
            c = ziel / f"clip_{i}.mp4"
            ff("-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30", "-t", "5", "-pix_fmt", "yuv420p", str(c))
        clips.append(c)
    stimme, musik = ziel / "stimme.mp3", ziel / "musik.mp3"
    ff("-f", "lavfi", "-i", f"sine=f=220:d={n * 3}", str(stimme))
    ff("-f", "lavfi", "-i", "sine=f=440:d=8", str(musik))
    g1, g2 = ziel / "wind.mp3", ziel / "knall.mp3"
    ff("-f", "lavfi", "-i", "anoisesrc=d=6:c=pink", str(g1))
    ff("-f", "lavfi", "-i", "anoisesrc=d=2:c=brown", str(g2))
    ass = ziel / "untertitel.ass"
    woerter = [{"wort": w, "start": i * 0.4, "ende": i * 0.4 + 0.3} for i, w in enumerate("THIS IS A TEST".split())]
    ass.write_text(schnitt.ass_untertitel(woerter, KONF), encoding="utf-8")
    geraeusche = [g1, None, g2] + [None] * (n - 3)
    final = ziel / "probe_final.mp4"
    for b in schnitt.befehle(plan, zeiten, clips, stimme, musik, ass, final, KONF, geraeusche):
        if b[0] == "#schreibe":
            Path(b[1]).write_text(b[2], encoding="utf-8")
        else:
            subprocess.run(b, check=True, capture_output=True)
    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                           "-of", "json", str(final)], check=True, capture_output=True, text=True).stdout
    d = json.loads(info)
    typen = sorted(s["codec_type"] for s in d["streams"])
    assert typen == ["audio", "video"], typen
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920), v
    print(f"OK: {final.name} {float(d['format']['duration']):.1f} s, 1080x1920, Ton und Bild vorhanden")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "probe_schnitt"))
