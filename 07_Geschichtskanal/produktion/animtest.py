"""Animationstest: 2,5D-Animation der L001-Bilder + realistische KI-Einschübe (Wan 3.0), ca. 1 Minute.

Schritte (einzeln aufrufbar, der Workflow animtest.yml ruft sie der Reihe nach auf):
  clips   – erzeugt fehlende realistische Clips (Startbild nano-banana-pro 16:9, Video Wan 3.0 16:9, 5 s)
  zeiten  – liest die Szenenwechsel aus L001_final.mp4 (jede Szene blendet aus Schwarz ein)
  frames  – zerlegt die Clips in Einzelbilder für den Browser-Renderer
  mix     – setzt die gerenderten Bilder mit dem Originalton von L001 zu einer MP4 zusammen

Arbeitsordner: $GK_ARBEIT (bilder/, l001/, clips/, frames/). Kein Upload, nur Artefakte.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import lauf
from anbieter import Fal, lade_datei

ARBEIT = Path(os.environ.get("GK_ARBEIT", "arbeit")).resolve()
SID = "A001"            # eigenes Konto im Kostenbuch
LIMIT_USD = 6.0         # harte Grenze für diesen Test
FPS = 30
SZENEN = 14             # Szenen 1–14 von L001 (Ende = Beginn von Szene 15)
KAPITEL2_S = 28  # Kapitelmarke 0:28 (kapitel.txt von L001) = Beginn von Szene 8

STIL = ("photorealistic cinematic film still, 16:9 widescreen, upright camera, level horizon, natural light, "
        "35mm documentary realism, historically plausible 1st century Roman Italy, no modern objects, "
        "no close-up faces, no text, no captions, no watermark")
EINSCHUEBE = {
    "e1": {"szene": 4,
           "bild": "A colossal eruption column of grey-black ash and pumice rising kilometres into the sky from a "
                   "cone-shaped volcano, seen across the red-tiled rooftops of an ancient Roman town in the foreground, "
                   "afternoon light dimming, first ash falling. " + STIL,
           "video": "The ash column billows and expands upward and outward, ash drifts down over the rooftops, "
                    "slow steady push-in, upright camera, level horizon, realistic physics, no cuts."},
    "e2": {"szene": 10,
           "bild": "A busy sunlit street in an ancient Roman town, stone-paved road with raised stepping stones, a wooden "
                   "cart pulled by a mule, townspeople in simple tunics seen from behind and at a distance, shop counters "
                   "under fabric awnings, warm golden light, dust in the air. " + STIL,
           "video": "The cart rolls slowly forward over the paving stones, people walk past, dust floats in the sunlight, "
                    "gentle sideways tracking shot, upright camera, level horizon, no cuts."},
    "e3": {"szene": 13,
           "bild": "Rows of grapevines on a gentle hillside at golden hour, a clay amphora at the edge of the vineyard, "
                   "beyond them the calm blue Bay of Naples and the quiet green cone of Mount Vesuvius without any smoke, "
                   "ancient countryside, no buildings of modern times. " + STIL,
           "video": "Slow cinematic dolly forward over the vines, leaves move in a light breeze, warm sunset light, "
                    "calm sea glittering, upright camera, level horizon, no cuts."},
}
BILD_MODELL, BILD_USD = "fal-ai/nano-banana-pro", 0.15
VIDEO_MODELL, VIDEO_USD_S, CLIP_S = "alibaba/wan-3.0/image-to-video", 0.2, 5


def ff(*args: str, ausgabe: bool = False) -> bytes:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True,
                       stdout=subprocess.PIPE if ausgabe else None)
    return r.stdout or b""


def l001_video() -> Path:
    treffer = sorted((ARBEIT / "l001").rglob("L001_final.mp4"))
    if not treffer:
        sys.exit("L001_final.mp4 fehlt (Artefakt langvideo-produziere)")
    return treffer[0]


def clips() -> None:
    kosten, _, fehler, _ = lauf.buecher()
    fal = Fal()
    ziel = ARBEIT / "clips"
    ziel.mkdir(parents=True, exist_ok=True)
    for name, e in EINSCHUEBE.items():
        mp4 = ziel / f"{name}.mp4"
        if mp4.exists() and mp4.stat().st_size > 100_000:
            print(f"{name}: vorhanden, wird nicht neu bezahlt")
            continue
        if kosten.summe(short=SID) + BILD_USD + VIDEO_USD_S * CLIP_S > LIMIT_USD:
            sys.exit(f"Testgrenze {LIMIT_USD} USD erreicht")
        png = ziel / f"{name}_start.png"
        r = fal._lauf(BILD_MODELL, {"prompt": e["bild"], "aspect_ratio": "16:9", "num_images": 1,
                                    "resolution": "2K", "output_format": "png"})
        kosten.buchen(SID, f"{name}_bild", BILD_USD, "fal")
        url = r["images"][0]["url"]
        lade_datei(url, png)
        probleme = lauf.sicht_pruefen(fal, png, kosten, SID, f"{name}_sicht", fehler, SID)
        if probleme:
            print(f"{name}: Sichtprüfung meldet {probleme} – Clip wird trotzdem erzeugt, bitte im Ergebnis ansehen")
        kosten.buchen(SID, f"{name}_video", VIDEO_USD_S * CLIP_S, "fal")
        v = fal._lauf(VIDEO_MODELL, {"start_image_url": url, "prompt": e["video"], "duration": CLIP_S,
                                     "resolution": "1080p", "aspect_ratio": "16:9", "audio": False,
                                     "enable_prompt_expansion": False}, max_warten_s=900)
        lade_datei(v["video"]["url"], mp4)
        print(f"{name}: fertig ({mp4.stat().st_size // 1024} KB)")
    print(f"Kosten Test: {kosten.summe(short=SID):.2f} USD")


def zeiten() -> None:
    """Jede Szene in L001 beginnt mit fade=in aus Schwarz: Szenenanfang = Bild, das schlagartig dunkel wird."""
    w, h = 64, 36
    roh = ff("-t", "90", "-i", str(l001_video()), "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "pipe:",
             ausgabe=True)
    n = len(roh) // (w * h)
    hell = [sum(roh[i * w * h:(i + 1) * w * h]) / (w * h) for i in range(n)]
    starts = [0.0]
    for i in range(1, n):
        if hell[i] < 0.45 * hell[i - 1] and hell[i - 1] > 20 and i / FPS - starts[-1] > 0.8:
            starts.append(round(i / FPS, 3))
    print("Szenenanfänge:", starts[:SZENEN + 2])
    if len(starts) < SZENEN + 1:
        sys.exit(f"nur {len(starts)} Szenen erkannt")
    if int(starts[7]) != KAPITEL2_S or any(b - a < 1.0 for a, b in zip(starts, starts[1:SZENEN + 1])):
        sys.exit(f"Schnitterkennung unplausibel (Szene 8 bei {starts[7]} s statt 0:{KAPITEL2_S})")
    (ARBEIT / "zeiten.json").write_text(json.dumps(starts[:SZENEN + 1]))


def frames() -> None:
    anzahl = {}
    for name in EINSCHUEBE:
        mp4 = ARBEIT / "clips" / f"{name}.mp4"
        ordner = ARBEIT / "clips" / name
        ordner.mkdir(parents=True, exist_ok=True)
        ff("-i", str(mp4), "-vf", f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps={FPS}",
           "-q:v", "3", str(ordner / "%04d.jpg"))
        anzahl[EINSCHUEBE[name]["szene"]] = {"name": name, "frames": len(list(ordner.glob("*.jpg")))}
    print("Clip-Bilder:", anzahl)
    (ARBEIT / "clips.json").write_text(json.dumps(anzahl))


def mix() -> None:
    ende = json.loads((ARBEIT / "zeiten.json").read_text())[-1]
    ziel = ARBEIT / "ergebnis"
    ziel.mkdir(exist_ok=True)
    mp4 = ziel / "L001_animtest_1min.mp4"
    ff("-framerate", str(FPS), "-i", str(ARBEIT / "frames" / "%05d.jpg"), "-t", f"{ende:.3f}", "-i", str(l001_video()),
       "-map", "0:v", "-map", "1:a", "-af", f"afade=t=out:st={max(ende - 0.8, 0):.2f}:d=0.8",
       "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-maxrate", "12M", "-bufsize", "24M", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(mp4))
    # Kontaktbogen: alle 3 Sekunden ein Bild
    ff("-i", str(mp4), "-vf", "fps=1/3,scale=480:270,tile=6x4", "-frames:v", "1", "-q:v", "3", str(ziel / "kontaktbogen.jpg"))
    print(f"fertig: {mp4.name} ({mp4.stat().st_size / 1e6:.1f} MB, {ende:.1f} s)")


if __name__ == "__main__":
    schritte = {"clips": clips, "zeiten": zeiten, "frames": frames, "mix": mix}
    if len(sys.argv) != 2 or sys.argv[1] not in schritte:
        sys.exit("Aufruf: python animtest.py clips|zeiten|frames|mix")
    schritte[sys.argv[1]]()
