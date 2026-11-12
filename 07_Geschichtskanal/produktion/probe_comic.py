"""Probe im neuen Stil: schwarz-weiße, flache Comic-/Vektorbilder, per Code animiert (anim.html), mit Stimme und Musik.
Hängt die Probe an den schon bezahlten Einstieg (cotard_probe_20s.mp4) an. Kein Upload.

Aufruf: python probe_comic.py bilder | stimme | mix     (dazwischen rendert animation/render_anim.mjs)
Kosten: 5 Bilder × höchstens 0,08 USD + Stimme wenige Cent = höchstens 0,50 USD. Harte Grenze 1 USD.
Text selbst geschrieben. Fakten: Jules Cotard beschrieb 1880 in Paris die Patientin „Mademoiselle X“, die überzeugt war,
kein Gehirn, keine Nerven und keinen Magen zu haben und nicht sterben zu können; sie hörte auf zu essen und verhungerte.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import lauf
from anbieter import AnbieterFehler, ElevenLabs, Fal, lade_datei

SID = "P002"
LIMIT_USD = 1.0
STIMME = "pJGEjsYXKNeCU49MF7cD"
MUSIK = "dark_mystery_piano.mp3"
MODELL = "fal-ai/recraft/v3/text-to-image"
STILE = ["vector_illustration/sharp_contrast", "vector_illustration", "digital_illustration/2d_art_poster"]   # erster gültiger gewinnt
FARBEN = [{"r": 10, "g": 10, "b": 10}, {"r": 245, "g": 245, "b": 245}, {"r": 120, "g": 120, "b": 120}, {"r": 60, "g": 60, "b": 60}]
STIL = ("black and white flat vector illustration, bold simple shapes, solid fills, crisp clean edges, strong contrast, "
        "minimal composition with generous empty space, no texture, no grain, no gradients, no shading, "
        "figures only as simple silhouettes without facial details, wide 16:9 composition, no text, no letters, no watermark")
SZENEN = [
    {"text": "In 1880, in Paris, a neurologist named Jules Cotard described a patient he called Mademoiselle X.",
     "bild": "Paris rooftops at night in 1880 with a large old hospital building and tall arched windows, a few lit windows, "
             "gas street lamps, a huge full moon behind chimneys",
     "bewegung": "zoom_rein", "fx": "nebel staub", "wort": "PARIS, 1880", "tiefe": 1.4},
    {"text": "She told him she had no brain, no nerves, and no stomach.",
     "bild": "Side view of a seated woman as a solid black silhouette on a wooden chair, her body shown as an empty white "
             "outline inside the silhouette like a hollow shell, a doctor silhouette with a notebook standing far away",
     "bewegung": "schwenk_rechts", "fx": "licht", "wort": "MADEMOISELLE X", "tiefe": .9},
    {"text": "She was certain that nothing inside her was left.",
     "bild": "A simple medical diagram of a human torso outline, completely empty inside, with thin pointer lines leading "
             "to blank labels, centered on a plain background",
     "bewegung": "zoom_rein", "fx": "staub", "wort": "NOTHING INSIDE", "tiefe": .4},
    {"text": "And because she believed she could never die, she saw no reason to eat.",
     "bild": "A small table with a full plate, a spoon and a glass, completely untouched, an empty chair pushed back, "
             "a single hanging lamp above, long shadow on the floor",
     "bewegung": "zoom_raus", "fx": "licht staub", "wort": "NO REASON TO EAT", "tiefe": 1.1},
    {"text": "She starved to death, convinced she was already gone.",
     "bild": "An empty narrow iron hospital bed in a bare room, a tall window with moonlight falling across the floor, "
             "one wilted flower in a vase on the windowsill",
     "bewegung": "zoom_rein", "fx": "nebel", "wort": None, "tiefe": 1.2},
]


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def dauer(p: Path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                check=True, capture_output=True, text=True).stdout.strip())


def ordner() -> Path:
    o = lauf.arbeitsordner() / "anim"
    (o / "bilder").mkdir(parents=True, exist_ok=True)
    return o


def bilder() -> None:
    kosten, *_ = lauf.buecher()
    fal, o, stil = Fal(), ordner(), None
    for n, s in enumerate(SZENEN, 1):
        ziel = o / "bilder" / f"bild_{n:03d}.png"
        if ziel.exists() and ziel.stat().st_size > 10_000:
            continue
        if kosten.summe(short=SID) + 0.08 > LIMIT_USD:
            sys.exit(f"Grenze {LIMIT_USD} USD erreicht")
        r = None
        for kandidat in ([stil] if stil else STILE):
            try:
                r = fal._lauf(MODELL, {"prompt": f"{s['bild']}. {STIL}", "image_size": "landscape_16_9", "style": kandidat,
                                       "colors": FARBEN})
                stil = kandidat
                break
            except AnbieterFehler as ex:
                print(f"Stil {kandidat} nicht möglich: {str(ex)[:120]}")
        if r is None:
            sys.exit("kein Stil hat funktioniert")
        kosten.buchen(SID, f"bild_{n}", 0.08 if stil.startswith("vector") else 0.04, "fal")
        roh = lade_datei(r["images"][0]["url"], ziel.with_suffix(".roh"))
        if roh.read_bytes()[:300].lstrip().startswith((b"<svg", b"<?xml")):
            mitte = ziel.with_suffix(".gross.png")
            subprocess.run(["rsvg-convert", "-w", "2400", "-b", "white", "-o", str(mitte), str(roh)], check=True)
            roh.replace(o / "bilder" / f"bild_{n:03d}.svg")
            roh = mitte
        ff("-i", str(roh), "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080", str(ziel))
        roh.unlink(missing_ok=True)
        print(f"Bild {n} fertig ({stil})", flush=True)
    (o / "stil.txt").write_text(stil or "aus Cache")


def stimme() -> None:
    kosten, *_ = lauf.buecher()
    o = ordner()
    text = " ".join(s["text"] for s in SZENEN)
    kosten.buchen(SID, "stimme", len(text) / 1000 * lauf.KONF["stimme"]["preis_usd_pro_1000_zeichen"], "elevenlabs")
    woerter = ElevenLabs().sprechen(text, STIMME, lauf.KONF["stimme"]["modell"], o / "stimme.mp3")
    zeiten, i = [0.0], 0
    for s in SZENEN[:-1]:                                   # Szenenwechsel = Beginn des ersten Worts der nächsten Szene
        i += len(s["text"].split())
        zeiten.append(round(max(woerter[i]["start"] - 0.12, zeiten[-1] + 1.0), 3))
    zeiten.append(round(dauer(o / "stimme.mp3") + 0.9, 3))
    konf = {"zeiten": zeiten, "sw": True, "filmlook": False,
            "szenen": [{k: s[k] for k in ("bewegung", "fx", "wort", "tiefe")} for s in SZENEN]}
    (o / "konf.json").write_text(json.dumps(konf))
    print("Zeiten:", zeiten)


def mix() -> None:
    kosten, *_ = lauf.buecher()
    o = ordner()
    ende = json.loads((o / "konf.json").read_text())["zeiten"][-1]
    erg = lauf.arbeitsordner() / "ergebnis"
    erg.mkdir(exist_ok=True)
    teil2 = erg / "cotard_comic_probe.mp4"
    musik = Path(__file__).parent / "musik" / MUSIK
    ein = ["-framerate", "30", "-i", str(o / "frames" / "%05d.jpg"), "-i", str(o / "stimme.mp3")]
    if musik.exists():
        ein += ["-stream_loop", "-1", "-i", str(musik)]
        ton = (f"[2:a]volume=-15dB[mu];[1:a]asplit=2[s1][s2];[mu][s1]sidechaincompress=threshold=0.03:ratio=5:attack=30:release=700[d];"
               f"[s2][d]amix=inputs=2:duration=first:normalize=0,apad=pad_dur=1.2,afade=t=out:st={ende - 0.8:.2f}:d=0.8,"
               f"loudnorm=I=-14:TP=-1.5:LRA=11[ton]")
    else:
        ton = "[1:a]apad=pad_dur=1.2,loudnorm=I=-14:TP=-1.5:LRA=11[ton]"
    ff(*ein, "-filter_complex", ton, "-map", "0:v", "-map", "[ton]", "-t", f"{ende:.2f}", "-r", "30",
       "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
       "-movflags", "+faststart", str(teil2))
    einstieg = sorted((lauf.arbeitsordner() / "einstieg").rglob("cotard_probe_20s.mp4"))
    if einstieg:                                             # schon bezahlter Einstieg + neue Probe hintereinander
        ff("-i", str(einstieg[0]), "-i", str(teil2), "-filter_complex",
           "[0:v]fps=30,format=yuv420p[a];[1:v]fps=30,format=yuv420p[b];[0:a]aresample=48000[x];[1:a]aresample=48000[y];"
           "[a][x][b][y]concat=n=2:v=1:a=1[v][t]", "-map", "[v]", "-map", "[t]", "-c:v", "libx264", "-preset", "medium",
           "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
           str(erg / "cotard_einstieg_plus_comic.mp4"))
    ff("-i", str(teil2), "-vf", f"fps=10/{ende:.1f},scale=480:270,tile=5x2", "-frames:v", "1", "-q:v", "3", str(erg / "kontaktbogen.jpg"))
    usd = round(kosten.summe(short=SID), 2)
    sek = round(ende, 1)
    (erg / "info.json").write_text(json.dumps({"dauer_s": sek, "usd": usd, "usd_pro_10_min": round(usd / sek * 600, 2),
                                               "stil": (o / "stil.txt").read_text()}))
    print(f"fertig: {sek} s, {usd} USD, hochgerechnet auf 10 Minuten {usd / sek * 600:.2f} USD")


if __name__ == "__main__":
    schritte = {"bilder": bilder, "stimme": stimme, "mix": mix}
    if len(sys.argv) != 2 or sys.argv[1] not in schritte:
        sys.exit("Aufruf: python probe_comic.py bilder|stimme|mix")
    schritte[sys.argv[1]]()
