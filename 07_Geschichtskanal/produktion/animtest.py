"""Animiertes Langvideo L001: 2,5D-Animation der L001-Bilder + realistische KI-Einschübe (Wan 3.0).

UMFANG=test  → Szenen 1–14 (ca. 1 Minute, Animationstest vom 11.11.2026)
UMFANG=voll  → ganzes Video, 93 Szenen (ca. 8:44)

Schritte (einzeln aufrufbar, der Workflow animtest.yml ruft sie der Reihe nach auf):
  zeiten  – liest die Szenenwechsel aus L001_final.mp4 (jede Szene blendet aus Schwarz ein) und prüft sie
            gegen die Kapitelmarken (kapitel.txt)
  clips   – erzeugt fehlende realistische Clips (Startbild nano-banana-pro 16:9, Video Wan 3.0 16:9, 5 s)
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
UMFANG = os.environ.get("UMFANG", "test")
VOLL = UMFANG == "voll"
SID = "A002" if VOLL else "A001"            # eigenes Konto im Kostenbuch
LIMIT_USD = 12.0 if VOLL else 6.0           # harte Grenze je Lauf
FPS = 30
SZENEN = 93 if VOLL else 14
KAPITEL_SZENEN = [1, 8, 17, 25, 37, 51, 64, 77]   # erste Szene je Kapitel (Plan L001 v2)

STIL = ("photorealistic cinematic film still, 16:9 widescreen, upright camera, level horizon, natural light, "
        "35mm documentary realism, historically plausible 1st century Roman Italy, no modern objects, "
        "no close-up faces, no text, no captions, no watermark")
STIL_HEUTE = ("photorealistic aerial documentary photograph, 16:9 widescreen, upright camera, level horizon, "
              "clear daylight, no text, no captions, no watermark")
VESUV = ("Mount Vesuvius as ONE single tall symmetrical cone with a single summit, as it looked before 79 AD, "
         "no second peak, no caldera rim")
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
    "e3": {"szene": 13, "umfang": "test",
           "bild": "Rows of grapevines on a gentle hillside at golden hour, a clay amphora at the edge of the vineyard, "
                   "beyond them the calm blue Bay of Naples and the quiet green cone of Mount Vesuvius without any smoke, "
                   "ancient countryside, no buildings of modern times. " + STIL,
           "video": "Slow cinematic dolly forward over the vines, leaves move in a light breeze, warm sunset light, "
                    "calm sea glittering, upright camera, level horizon, no cuts."},
    # --- nur im vollen Video (e3b ersetzt e3: im Test hatte der Vesuv fälschlich zwei Gipfel) ---
    "e3b": {"szene": 13, "umfang": "voll",
            "bild": "Rows of grapevines on a gentle hillside at golden hour, a clay amphora at the edge of the vineyard, "
                    "beyond them the calm blue Bay of Naples and, far away, " + VESUV + ", green slopes, no smoke, "
                    "ancient countryside. " + STIL,
            "video": "Slow cinematic dolly forward over the vines, leaves move in a light breeze, warm sunset light, "
                     "calm sea glittering, upright camera, level horizon, no cuts."},
    "e4": {"szene": 25, "umfang": "voll",
           "bild": "A gigantic volcanic explosion tears open the summit of " + VESUV + "; a dark column of ash and gas "
                   "shoots straight up into a bright afternoon sky, seen from far across a wide bay with ancient Roman "
                   "villas and pines on the shore in the foreground. " + STIL,
           "video": "The explosion blasts upward, the ash column surges higher and billows outward, slow steady "
                    "push-in, upright camera, level horizon, no cuts."},
    "e5": {"szene": 33, "umfang": "voll",
           "bild": "Light grey-white pumice stones and ash raining down on a narrow stone-paved street of an ancient "
                   "Roman town, red-tiled roofs and wooden shop shutters, sky darkened brown-grey, empty street, "
                   "no people. " + STIL,
           "video": "Pumice stones fall steadily and bounce on the paving stones and roofs, ash drifts through the air, "
                    "slow push-in, steady upright camera, level horizon, no cuts."},
    "e6": {"szene": 47, "umfang": "voll",
           "bild": "Night: glowing orange fires and burning streaks on the slopes of " + VESUV + " under a massive dark "
                   "ash cloud, seen from far across a dark bay, faint orange reflections on the water, ancient coastline "
                   "without any modern lights. " + STIL,
           "video": "Flames flicker and glow on the mountain, the dark cloud slowly churns above, reflections shimmer "
                    "on the water, gentle push-in, upright camera, level horizon, no cuts."},
    "e7": {"szene": 54, "umfang": "voll",
           "bild": "A pyroclastic surge: a gigantic billowing avalanche of grey-black hot ash and gas rushing down the "
                   "slopes of a volcano toward fields and the sea, seen from a distance, ancient countryside, "
                   "no people. " + STIL,
           "video": "The surge rolls rapidly down the slope and expands toward the camera, churning and boiling, "
                    "realistic physics, steady upright camera, level horizon, no cuts."},
    "e8": {"szene": 60, "umfang": "voll",
           "bild": "A towering black ash cloud rolling across the sea toward a small ancient coastal town, flashes of "
                   "lightning inside the cloud, dark stormy light, rough grey water. " + STIL,
           "video": "The black cloud advances over the water, lightning flickers inside it, waves roll, slow push-in, "
                    "upright camera, level horizon, no cuts."},
    "e9": {"szene": 85, "umfang": "voll",
           "bild": "Aerial view of the modern city of Naples spreading densely along the bay, apartment buildings "
                   "climbing up the lower slopes, with Mount Vesuvius rising directly behind the city. " + STIL_HEUTE,
           "video": "Slow aerial drone flight forward over the city toward the volcano, light haze, "
                    "steady upright camera, level horizon, no cuts."},
}
AKTIV = {k: v for k, v in EINSCHUEBE.items() if v.get("umfang") in (None, UMFANG)}
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
    for name, e in AKTIV.items():
        mp4 = ziel / f"{name}.mp4"
        if mp4.exists() and mp4.stat().st_size > 100_000:
            print(f"{name}: vorhanden, wird nicht neu bezahlt")
            continue
        if kosten.summe(short=SID) + BILD_USD + VIDEO_USD_S * CLIP_S > LIMIT_USD:
            sys.exit(f"Grenze {LIMIT_USD} USD erreicht")
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
        print(f"{name}: fertig ({mp4.stat().st_size // 1024} KB)", flush=True)
    print(f"Kosten dieses Laufs: {kosten.summe(short=SID):.2f} USD")


def kapitelmarken() -> list[int]:
    kap = sorted((ARBEIT / "l001").rglob("kapitel.txt"))
    if not kap:
        return [0, 28]
    out = []
    for z in kap[0].read_text(encoding="utf-8").splitlines():
        if z.strip():
            m, s = z.split()[0].split(":")
            out.append(int(m) * 60 + int(s))
    return out


def zeiten() -> None:
    """Jede Szene in L001 beginnt mit fade=in aus Schwarz: Szenenanfang = Bild, das schlagartig dunkel wird."""
    w, h = 64, 36
    dauer = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                  str(l001_video())], check=True, capture_output=True, text=True).stdout.strip())
    roh = ff(*([] if VOLL else ["-t", "90"]), "-i", str(l001_video()), "-vf", f"scale={w}:{h},format=gray",
             "-f", "rawvideo", "pipe:", ausgabe=True)
    n = len(roh) // (w * h)
    hell = [sum(roh[i * w * h:(i + 1) * w * h]) / (w * h) for i in range(n)]
    starts = [0.0]
    for i in range(1, n):
        if hell[i] < 0.45 * hell[i - 1] and hell[i - 1] > 20 and i / FPS - starts[-1] > 0.8:
            starts.append(round(i / FPS, 3))
    print("Szenenanfänge:", starts[:SZENEN + 2])
    if len(starts) < SZENEN + (0 if VOLL else 1):
        sys.exit(f"nur {len(starts)} Szenen erkannt")
    if VOLL and len(starts) != SZENEN:
        sys.exit(f"{len(starts)} Szenen erkannt statt {SZENEN}")
    if any(b - a < 1.0 for a, b in zip(starts, starts[1:SZENEN + 1])):
        sys.exit("Schnitterkennung unplausibel (Szene kürzer als 1 s)")
    marken = kapitelmarken()
    for sz, m in zip(KAPITEL_SZENEN, marken):
        if sz <= SZENEN and abs(starts[sz - 1] - m) > 1.0:
            sys.exit(f"Schnitterkennung unplausibel: Szene {sz} bei {starts[sz - 1]} s, Kapitelmarke {m} s")
    z = starts[:SZENEN] + [round(dauer - 0.05, 3)] if VOLL else starts[:SZENEN + 1]
    print(f"{SZENEN} Szenen, Ende {z[-1]} s, Kapitelmarken {marken} geprüft")
    (ARBEIT / "zeiten.json").write_text(json.dumps(z))


def frames() -> None:
    anzahl = {}
    for name in AKTIV:
        mp4 = ARBEIT / "clips" / f"{name}.mp4"
        ordner = ARBEIT / "clips" / name
        ordner.mkdir(parents=True, exist_ok=True)
        ff("-i", str(mp4), "-vf", f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps={FPS}",
           "-q:v", "3", str(ordner / "%04d.jpg"))
        anzahl[AKTIV[name]["szene"]] = {"name": name, "frames": len(list(ordner.glob("*.jpg")))}
    print("Clip-Bilder:", anzahl)
    (ARBEIT / "clips.json").write_text(json.dumps(anzahl))


def mix() -> None:
    ende = json.loads((ARBEIT / "zeiten.json").read_text())[-1]
    ziel = ARBEIT / "ergebnis"
    ziel.mkdir(exist_ok=True)
    mp4 = ziel / ("L001_animiert.mp4" if VOLL else "L001_animtest_1min.mp4")
    ff("-framerate", str(FPS), "-i", str(ARBEIT / "frames" / "%05d.jpg"), "-t", f"{ende:.3f}", "-i", str(l001_video()),
       "-map", "0:v", "-map", "1:a", "-af", f"afade=t=out:st={max(ende - 0.8, 0):.2f}:d=0.8",
       "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "10M", "-bufsize", "20M", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(mp4))
    # Kontaktbogen: 24 Bilder gleichmäßig über das Video
    ff("-i", str(mp4), "-vf", f"fps=24/{ende:.1f},scale=480:270,tile=6x4", "-frames:v", "1", "-q:v", "3",
       str(ziel / "kontaktbogen.jpg"))
    print(f"fertig: {mp4.name} ({mp4.stat().st_size / 1e6:.1f} MB, {ende:.1f} s)")


if __name__ == "__main__":
    schritte = {"clips": clips, "zeiten": zeiten, "frames": frames, "mix": mix}
    if len(sys.argv) != 2 or sys.argv[1] not in schritte:
        sys.exit("Aufruf: python animtest.py clips|zeiten|frames|mix")
    schritte[sys.argv[1]]()
