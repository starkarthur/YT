"""20-Sekunden-Probe für ein neues Thema: Stimme + düstere Schwarz-Weiß-Clips + Musik. Kein Upload.

Aufruf: python probe20.py   (Umgebung: FAL_KEY, ELEVENLABS_API_KEY, GK_ARBEIT)
Kosten: 4 Clips × (0,15 + 1,00) USD = ca. 4,60 USD, Stimme wenige Cent. Harte Grenze 6 USD.
Thema dieser Probe: Cotard-Syndrom (Text selbst geschrieben, Aussagen allgemein und belegt:
seltene Wahnstörung, Betroffene sind überzeugt, tot zu sein; beschrieben von Jules Cotard 1880).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import lauf
from anbieter import ElevenLabs, Fal, lade_datei

SID = "P001"
LIMIT_USD = 6.0
STIMME = "pJGEjsYXKNeCU49MF7cD"      # vom Nutzer am 12.11.2026 für dieses Thema vorgegeben
MUSIK = "dark_mystery_piano.mp3"
TEXT = ("You wake up, and something is wrong. Your heart is beating. You are breathing. "
        "But you are completely certain of one thing: you are dead. "
        "Doctors call it Cotard's syndrome, one of the rarest conditions ever described. "
        "And for the people who have it, no proof of life is ever enough.")
STIL = ("black and white, high contrast, grainy 16mm film look, eerie and unsettling atmosphere, deep shadows, "
        "16:9 widescreen, upright camera, level horizon, no close-up faces, no blood, no text, no watermark")
CLIPS = [
    ("A dim bedroom at dawn, a person seen from behind sitting up slowly on the edge of a bed, pale light through thin "
     "curtains, long shadows on the wall. " + STIL,
     "The person slowly sits upright and stays still, curtains move slightly, very slow push-in, no cuts."),
    ("Extreme close-up of a hand pressed flat against a chest in a white shirt, fingers tense, hard side light, "
     "dark background. " + STIL,
     "The chest rises and falls with slow breathing, the fingers press harder, very slow push-in, no cuts."),
    ("A person standing in front of a fogged bathroom mirror, seen from behind, the reflection is only a blurred dark "
     "shape, a single bare light bulb above. " + STIL,
     "The figure stands motionless, the light bulb flickers, the blurred reflection barely moves, slow push-in, no cuts."),
    ("A long empty hospital corridor from the 1950s, a single small figure standing far away at the end, harsh ceiling "
     "lights, reflections on the floor. " + STIL,
     "The ceiling lights flicker one after another, the distant figure does not move, slow dolly forward, no cuts."),
]
BILD_MODELL, BILD_USD = "fal-ai/nano-banana-pro", 0.15
VIDEO_MODELL, VIDEO_USD_S, CLIP_S = "alibaba/wan-3.0/image-to-video", 0.2, 5


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def dauer(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                check=True, capture_output=True, text=True).stdout.strip())


def main() -> int:
    arbeit = lauf.arbeitsordner() / "probe20"
    arbeit.mkdir(parents=True, exist_ok=True)
    kosten, _, fehler, _ = lauf.buecher()
    fal = Fal()
    clips = []
    for n, (bild, bewegung) in enumerate(CLIPS, 1):          # erst die Clips: scheitert fal, ist keine Stimme verbraucht
        mp4 = arbeit / f"clip_{n}.mp4"
        clips.append(mp4)
        if mp4.exists() and mp4.stat().st_size > 100_000:
            continue
        if kosten.summe(short=SID) + BILD_USD + VIDEO_USD_S * CLIP_S > LIMIT_USD:
            sys.exit(f"Grenze {LIMIT_USD} USD erreicht")
        r = fal._lauf(BILD_MODELL, {"prompt": bild, "aspect_ratio": "16:9", "num_images": 1, "resolution": "2K",
                                    "output_format": "png"})
        kosten.buchen(SID, f"bild_{n}", BILD_USD, "fal")
        url = r["images"][0]["url"]
        lade_datei(url, arbeit / f"clip_{n}_start.png")
        lauf.sicht_pruefen(fal, arbeit / f"clip_{n}_start.png", kosten, SID, f"sicht_{n}", fehler, SID)
        kosten.buchen(SID, f"video_{n}", VIDEO_USD_S * CLIP_S, "fal")
        v = fal._lauf(VIDEO_MODELL, {"start_image_url": url, "prompt": bewegung, "duration": CLIP_S, "resolution": "1080p",
                                     "aspect_ratio": "16:9", "audio": False, "enable_prompt_expansion": False},
                      max_warten_s=900)
        lade_datei(v["video"]["url"], mp4)
        print(f"Clip {n} fertig", flush=True)

    sprache = arbeit / "stimme.mp3"
    kosten.buchen(SID, "stimme", len(TEXT) / 1000 * lauf.KONF["stimme"]["preis_usd_pro_1000_zeichen"], "elevenlabs")
    woerter = ElevenLabs().sprechen(TEXT, STIMME, lauf.KONF["stimme"]["modell"], sprache)
    gesamt = dauer(sprache) + 1.0
    teil = gesamt / len(CLIPS)
    print(f"Stimme {gesamt - 1:.1f} s, je Clip {teil:.2f} s, {len(woerter)} Wörter")

    eingaben, graph = [], []
    for i, c in enumerate(clips):
        eingaben += ["-i", str(c)]
        tempo = max(teil / (dauer(c) - 0.1), 1.0)            # Clip nur verlangsamen, nie beschleunigen
        graph.append(f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,"
                     f"setpts={tempo:.4f}*PTS,trim=duration={teil:.3f},setpts=PTS-STARTPTS,"
                     f"hue=s=0,eq=contrast=1.22:brightness=-0.04,fade=t=in:st=0:d=0.18[v{i}]")
    n = len(clips)
    graph.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,noise=alls=16:allf=t,vignette=PI/3.6,"
                 f"fade=t=out:st={gesamt - 0.6:.2f}:d=0.6[bild]")
    eingaben += ["-i", str(sprache)]
    musik = Path(__file__).parent / "musik" / MUSIK
    if musik.exists():
        eingaben += ["-stream_loop", "-1", "-i", str(musik)]
        graph.append(f"[{n + 1}:a]volume=-15dB[mu];[{n}:a]asplit=2[s1][s2];"
                     f"[mu][s1]sidechaincompress=threshold=0.03:ratio=5:attack=30:release=700[duck];"
                     f"[s2][duck]amix=inputs=2:duration=first:normalize=0,apad=pad_dur=1,"
                     f"afade=t=out:st={gesamt - 0.8:.2f}:d=0.8,loudnorm=I=-14:TP=-1.5:LRA=11[ton]")
    else:
        print("Hinweis: Musikstück fehlt, Probe ohne Musik")
        graph.append(f"[{n}:a]apad=pad_dur=1,loudnorm=I=-14:TP=-1.5:LRA=11[ton]")
    ziel = arbeit / "cotard_probe_20s.mp4"
    ff(*eingaben, "-filter_complex", ";".join(graph), "-map", "[bild]", "-map", "[ton]", "-t", f"{gesamt:.2f}",
       "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-maxrate", "10M", "-bufsize", "20M", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(ziel))
    ff("-i", str(ziel), "-vf", f"fps=8/{gesamt:.1f},scale=480:270,tile=4x2", "-frames:v", "1", "-q:v", "3",
       str(arbeit / "kontaktbogen.jpg"))
    (arbeit / "info.json").write_text(json.dumps({"dauer_s": round(gesamt, 2), "usd": round(kosten.summe(short=SID), 2)}))
    print(f"fertig: {ziel.name}, {gesamt:.1f} s, Kosten {kosten.summe(short=SID):.2f} USD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
