"""Lädt fehlende Musik und Geräusche aus musik/katalog.json (Feld "download", nur cdn.pixabay.com),
prüft jede Datei mit ffprobe (muss Ton sein, 0,5–600 s) und trägt dauer_s, sha256 und Ladedatum ein.
Läuft im Workflow musik-laden (Cloud), nicht lokal. Aufruf: python musik_laden.py"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

HIER = Path(__file__).resolve().parent
ORDNER = HIER / "musik"
KATALOG = ORDNER / "katalog.json"
ERLAUBT = "https://cdn.pixabay.com/download/audio/"
MAX = 20 * 1024 * 1024


def lade(url: str, ziel: Path) -> None:
    if not url.startswith(ERLAUBT):
        raise ValueError(f"nur Pixabay-CDN erlaubt: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "history-shorts-musik/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        if not r.geturl().startswith("https://cdn.pixabay.com/"):
            raise ValueError("Weiterleitung weg vom Pixabay-CDN")
        daten = r.read(MAX + 1)
    if len(daten) > MAX:
        raise ValueError("Datei zu groß")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(daten)


def dauer(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                          "stream=codec_type:format=duration", "-of", "json", str(p)],
                         check=True, capture_output=True, text=True).stdout
    d = json.loads(out)
    if not d.get("streams") or d["streams"][0].get("codec_type") != "audio":
        raise ValueError(f"{p.name}: keine Tonspur")
    s = float(d["format"]["duration"])
    if not 0.5 <= s <= 600:
        raise ValueError(f"{p.name}: Dauer {s:.1f} s unplausibel")
    return round(s, 1)


def main() -> int:
    k = json.loads(KATALOG.read_text(encoding="utf-8"))
    fehler = 0
    for bereich, unter in (("stuecke", ORDNER), ("geraeusche", ORDNER / "geraeusche")):
        for name, e in k.get(bereich, {}).items():
            ziel = unter / name
            try:
                if not ziel.exists():
                    lade(e["download"], ziel)
                    e["geladen"] = date.today().isoformat()
                e["dauer_s"] = dauer(ziel)
                e["sha256"] = hashlib.sha256(ziel.read_bytes()).hexdigest()
                print(f"ok  {bereich}/{name}  {e['dauer_s']} s")
            except Exception as x:  # eine kaputte Datei stoppt die anderen nicht
                fehler += 1
                ziel.unlink(missing_ok=True)
                print(f"FEHLER {bereich}/{name}: {x}")
    KATALOG.write_text(json.dumps(k, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
