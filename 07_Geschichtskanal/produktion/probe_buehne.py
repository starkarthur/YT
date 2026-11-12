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
LIMIT_USD = 0.5          # 4 Bausteine + höchstens 2 Wiederholungen
STILE = ["vector_illustration", "vector_illustration"]
FARBEN = [{"r": 0, "g": 0, "b": 0}, {"r": 255, "g": 255, "b": 255}]
STIL = ("Simple flat icon, one single solid black silhouette shape, side view, isolated cutout on a completely empty plain white "
        "background, centered with wide white margin on all four sides, nothing touches the image edge, no floor, no wall, "
        "no window, no room, no scenery, no shadow, no frame, no border, no colors, no text")
BAUSTEINE = {
    "frau": "a seated woman in a long old-fashioned dress with her hair in a bun, hands in her lap, facing right",
    "arzt": "a bearded man in a long coat sitting on a wooden chair and writing in a notebook, facing left",
    "bett": "a narrow iron bed frame with a thin mattress and a pillow",
    "tisch": "a small round side table with one plate and one glass on it",
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


def freigestellt(roh: bytes, n: int = 100) -> float:
    """Anteil des Bildrands (4 px), der hell und einfarbig ist. roh = n×n Pixel RGB. 1.0 = sauber freigestellt."""
    rand = [(x, y) for y in range(n) for x in range(n) if x < 4 or y < 4 or x >= n - 4 or y >= n - 4]
    farbe = lambda x, y: roh[(y * n + x) * 3:(y * n + x) * 3 + 3]
    stufen: dict = {}
    for x, y in rand:
        k = tuple(v // 32 for v in farbe(x, y))
        stufen[k] = stufen.get(k, 0) + 1
    haupt = max(stufen, key=stufen.get)
    if sum(haupt) * 32 / 3 < 150:          # dunkler Rand = kein freier Hintergrund
        return 0.0
    return stufen[haupt] / len(rand)


def pruefe(png: Path) -> float:
    roh = png.with_suffix(".rgb")
    ff("-i", str(png), "-vf", "scale=100:100", "-f", "rawvideo", "-pix_fmt", "rgb24", str(roh))
    wert = freigestellt(roh.read_bytes())
    roh.unlink()
    return wert


def bausteine() -> None:
    kosten, *_ = lauf.buecher()
    fal, o = Fal(), ordner()
    for name, was in BAUSTEINE.items():
        ziel = o / "bilder" / f"{name}.png"
        if ziel.exists() and ziel.stat().st_size > 2_000:
            continue
        bester = -1.0
        for versuch, kandidat in enumerate(STILE, 1):
            if kosten.summe(short=SID) + 0.08 > LIMIT_USD:
                print(f"Grenze {LIMIT_USD} USD erreicht, kein weiterer Versuch")
                break
            try:
                r = fal._lauf(MODELL, {"prompt": f"{STIL}. Subject: {was}.", "image_size": "square_hd", "style": kandidat, "colors": FARBEN})
            except AnbieterFehler as ex:
                print(f"Stil {kandidat} nicht möglich: {str(ex)[:120]}")
                continue
            kosten.buchen(SID, f"baustein_{name}_{versuch}", 0.08, "fal")
            probe = ziel.with_name(f"{name}_v{versuch}.png")
            roh = lade_datei(r["images"][0]["url"], probe.with_suffix(".roh"))
            if roh.read_bytes()[:300].lstrip().startswith((b"<svg", b"<?xml")):
                subprocess.run(["rsvg-convert", "-w", "1400", "-b", "white", "-o", str(probe), str(roh)], check=True)
            else:
                ff("-i", str(roh), str(probe))
            roh.unlink()
            wert = pruefe(probe)
            print(f"Baustein {name}, Versuch {versuch}: Rand frei zu {wert:.0%}", flush=True)
            if wert > bester:
                bester = wert
                ziel.write_bytes(probe.read_bytes())
            if wert >= 0.97:
                break
        if bester < 0:
            sys.exit(f"Baustein {name}: kein Bild erzeugt")


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
