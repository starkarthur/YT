"""Probe nach dem Baukasten-Prinzip (Vorbild Depth Theory): ein durchgehender Raum, wiederkehrende Figuren als
Silhouetten-Bausteine, Infografik per Code (animation/buehne.html). Hängt die Probe an den bezahlten Einstieg an.

Aufruf: python probe_buehne.py bausteine | stimme | mix     (dazwischen rendert animation/render_anim.mjs)
Kosten: 4 Bausteine × 0,08 USD + Stimme wenige Cent = ca. 0,35 USD. Harte Grenze 1 USD. Kein Upload.
Text selbst geschrieben; die Angaben zu „Mademoiselle X“ werden als Cotards Bericht (1880) erzählt.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import lauf
from anbieter import AnbieterFehler, ElevenLabs, Fal, lade_datei
from probe_comic import MODELL, MUSIK, STIMME, dauer, ff

SID = "P003"
LIMIT_USD = 1.0
STILE = ["vector_illustration/sharp_contrast", "vector_illustration"]
FARBEN = [{"r": 0, "g": 0, "b": 0}, {"r": 255, "g": 255, "b": 255}]
STIL = ("one single solid black silhouette, flat vector shape, side view, completely isolated on a pure white background, "
        "centered, the whole object visible, no ground, no shadow, no frame, no other objects, no text")
BAUSTEINE = {
    "frau": "a woman in a long plain 1880s dress with her hair in a bun, sitting upright with hands in her lap, facing right",
    "arzt": "a 19th century doctor with a beard in a long coat sitting on a wooden chair, holding a notebook, facing left",
    "bett": "a simple narrow iron hospital bed with a thin mattress and a pillow, seen exactly from the side",
    "tisch": "a small round wooden table with one plate and one glass standing on it, seen exactly from the side",
}
SAETZE = [   # eine Szene je Eintrag, alle im selben Raum
    "Picture a hospital room in Paris, in 1880.",
    "A neurologist named Jules Cotard sits across from a woman he calls Mademoiselle X.",
    "She tells him she has no brain. No nerves. No stomach.",
    "According to his report, she believed she could never die, so she stopped eating.",
    "What would you say to convince her that she is alive?",
]


def ordner() -> Path:
    o = lauf.arbeitsordner() / "buehne"
    (o / "bilder").mkdir(parents=True, exist_ok=True)
    return o


def bausteine() -> None:
    kosten, *_ = lauf.buecher()
    fal, o, stil = Fal(), ordner(), None
    for name, was in BAUSTEINE.items():
        ziel = o / "bilder" / f"{name}.png"
        if ziel.exists() and ziel.stat().st_size > 2_000:
            continue
        if kosten.summe(short=SID) + 0.08 > LIMIT_USD:
            sys.exit(f"Grenze {LIMIT_USD} USD erreicht")
        r = None
        for kandidat in ([stil] if stil else STILE):
            try:
                r = fal._lauf(MODELL, {"prompt": f"{was}. {STIL}", "image_size": "square_hd", "style": kandidat, "colors": FARBEN})
                stil = kandidat
                break
            except AnbieterFehler as ex:
                print(f"Stil {kandidat} nicht möglich: {str(ex)[:120]}")
        if r is None:
            sys.exit("kein Stil hat funktioniert")
        kosten.buchen(SID, f"baustein_{name}", 0.08, "fal")
        roh = lade_datei(r["images"][0]["url"], ziel.with_suffix(".roh"))
        if roh.read_bytes()[:300].lstrip().startswith((b"<svg", b"<?xml")):
            subprocess.run(["rsvg-convert", "-w", "1400", "-b", "white", "-o", str(ziel), str(roh)], check=True)
            roh.replace(ziel.with_suffix(".svg"))
        else:
            ff("-i", str(roh), str(ziel))
            roh.unlink()
        print(f"Baustein {name} fertig", flush=True)


def stimme() -> None:
    kosten, *_ = lauf.buecher()
    o = ordner()
    text = " ".join(SAETZE)
    kosten.buchen(SID, "stimme", len(text) / 1000 * lauf.KONF["stimme"]["preis_usd_pro_1000_zeichen"], "elevenlabs")
    woerter = ElevenLabs().sprechen(text, STIMME, lauf.KONF["stimme"]["modell"], o / "stimme.mp3")
    zeiten, i = [0.0], 0
    for s in SAETZE[:-1]:
        i += len(s.split())
        zeiten.append(round(max(woerter[i]["start"] - 0.15, zeiten[-1] + 1.0), 3))
    zeiten.append(round(dauer(o / "stimme.mp3") + 1.6, 3))
    (o / "konf.json").write_text(json.dumps({"zeiten": zeiten}))
    print("Zeiten:", zeiten)


def mix() -> None:
    kosten, *_ = lauf.buecher()
    o = ordner()
    ende = json.loads((o / "konf.json").read_text())["zeiten"][-1]
    erg = lauf.arbeitsordner() / "ergebnis"
    erg.mkdir(exist_ok=True)
    teil = erg / "cotard_buehne_probe.mp4"
    musik = Path(__file__).parent / "musik" / MUSIK
    ein = ["-framerate", "30", "-i", str(o / "frames" / "%05d.jpg"), "-i", str(o / "stimme.mp3")]
    if musik.exists():
        ein += ["-stream_loop", "-1", "-i", str(musik)]
        ton = (f"[2:a]volume=-15dB[mu];[1:a]asplit=2[s1][s2];[mu][s1]sidechaincompress=threshold=0.03:ratio=5:attack=30:release=700[d];"
               f"[s2][d]amix=inputs=2:duration=first:normalize=0,apad=pad_dur=2,afade=t=out:st={ende - 0.8:.2f}:d=0.8,"
               f"loudnorm=I=-14:TP=-1.5:LRA=11[ton]")
    else:
        ton = "[1:a]apad=pad_dur=2,loudnorm=I=-14:TP=-1.5:LRA=11[ton]"
    ff(*ein, "-filter_complex", ton, "-map", "0:v", "-map", "[ton]", "-t", f"{ende:.2f}", "-r", "30", "-c:v", "libx264",
       "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
       "-movflags", "+faststart", str(teil))
    einstieg = sorted((lauf.arbeitsordner() / "einstieg").rglob("cotard_probe_20s.mp4"))
    if einstieg:
        ff("-i", str(einstieg[0]), "-i", str(teil), "-filter_complex",
           "[0:v]fps=30,format=yuv420p[a];[1:v]fps=30,format=yuv420p[b];[0:a]aresample=48000[x];[1:a]aresample=48000[y];"
           "[a][x][b][y]concat=n=2:v=1:a=1[v][t]", "-map", "[v]", "-map", "[t]", "-c:v", "libx264", "-preset", "medium",
           "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
           str(erg / "cotard_einstieg_plus_buehne.mp4"))
    ff("-i", str(teil), "-vf", f"fps=10/{ende:.1f},scale=480:270,tile=5x2", "-frames:v", "1", "-q:v", "3", str(erg / "kontaktbogen.jpg"))
    usd = round(kosten.summe(short=SID), 2)
    (erg / "info.json").write_text(json.dumps({"dauer_s": round(ende, 1), "usd": usd}))
    print(f"fertig: {ende:.1f} s, {usd} USD")


if __name__ == "__main__":
    schritte = {"bausteine": bausteine, "stimme": stimme, "mix": mix}
    if len(sys.argv) != 2 or sys.argv[1] not in schritte:
        sys.exit("Aufruf: python probe_buehne.py bausteine|stimme|mix")
    schritte[sys.argv[1]]()
