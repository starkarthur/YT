"""Stimmproben für ein Langvideo: derselbe kurze Text mit mehreren ElevenLabs-Stimmen.
Aufruf (nur im Workflow stimmprobe): python stimmprobe.py
Ergebnis: $GK_ARBEIT/stimmprobe/<name>.mp3 und stimmen.txt (verfügbare Stimmen des Kontos, nur Name/ID/Kategorie).
Kosten: ca. 3 × 330 Zeichen aus dem ElevenLabs-Abo, kein Upload.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

from anbieter import AnbieterFehler, ElevenLabs

HIER = Path(__file__).resolve().parent
ARBEIT = Path(os.environ.get("GK_ARBEIT", "arbeit"))
KONF = json.loads((HIER / "konfig.json").read_text(encoding="utf-8"))
MODELL = KONF["stimme"]["modell"]

# L004 Molasse, Szenen 1 und 3 (Skript 07_Geschichtskanal/Shorts/L004_Molasse_Skript.md)
TEXT = ("Picture this. It's lunchtime on Commercial Street, Boston, January 1919. You are standing in the sun. "
        "Behind you is a steel tank, five stories tall. In a few seconds, the steel will tear open. "
        "And a brown wave, reportedly as tall as a two-story house, will come down this street toward you.")
STIMMEN = {
    "1_langvideo_bisher": "j3VVEWUzmXMcWPJl9xAg",   # Langvideo-Stimme seit 11.11.2026 (Pompeji)
    "2_cotard_probe": "pJGEjsYXKNeCU49MF7cD",      # für L002 Cotard vorgesehen
    "3_george_ruhig": "JBFqnCBsd6RMkjVDRZzb",      # ElevenLabs-Standardstimme «George» (ruhiger Erzähler)
}
MAX_ZEICHEN = 400


def stimmen_liste() -> str:
    req = urllib.request.Request("https://api.elevenlabs.io/v1/voices",
                                 headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]})
    with urllib.request.urlopen(req, timeout=60) as r:
        daten = json.load(r)
    zeilen = [f"{v.get('name')}\t{v.get('voice_id')}\t{v.get('category')}\t{(v.get('labels') or {})}" for v in daten.get("voices", [])]
    return "\n".join(zeilen)


def main() -> int:
    if len(TEXT) > MAX_ZEICHEN:
        print("Text zu lang"); return 1
    ziel = ARBEIT / "stimmprobe"
    ziel.mkdir(parents=True, exist_ok=True)
    fehler = 0
    for name, vid in STIMMEN.items():
        try:
            ElevenLabs().sprechen(TEXT, vid, MODELL, ziel / f"{name}.mp3")
            print("ok", name)
        except AnbieterFehler as e:
            fehler += 1
            print("FEHLER", name, e)
    try:
        (ziel / "stimmen.txt").write_text(stimmen_liste(), encoding="utf-8")
    except Exception as e:  # nur Zusatzinfo
        print("Stimmenliste nicht abrufbar:", e)
    return 1 if fehler == len(STIMMEN) else 0


if __name__ == "__main__":
    sys.exit(main())
