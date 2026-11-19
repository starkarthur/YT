"""10-Sekunden-Werbetest (realistisch, 16:9) über Higgsfield: Soul 2 + Seedance 2.5. Kein Upload.

Arbeitsweise nach `Gedaechtnis/Higgsfield-Arbeitsweise.md` (Fassung 2, 19.11.2026), in Stufen:
  python probe_werbung.py bilder              vier Startbilder zur Auswahl (auswahl.jpg), Cent-Beträge
  python probe_werbung.py video --bild 2 --aufloesung 480p    Entwurf: Bewegung prüfen, billig
  python probe_werbung.py video --bild 2 --aufloesung 1080p   Endfassung, wenn der Entwurf passt
  Zusätze: --takes 2 (zwei Fassungen je Clip), --ohne-einblendung, --probe (ohne Netz und Kosten)
Umgebung: HIGGSFIELD_KEY, GK_ARBEIT.

Lehren aus Fassung 1 (Nutzerurteil „0 realistisch“):
  - Besetzung: klassische Programmierer, keine Models. Look wie ein Dokumentarfilm, nicht wie Stockmaterial.
  - Die Tasse ist schon im Startbild in der Hand am Henkel. Greifen und Umfassen kann Video-KI schlecht.
  - Keine Schrift im erzeugten Bild (wurde zu „RANSOMWIRE“). Monitore werden nur rot mit Schloss-Symbol;
    der Text kommt als Warnzeile aus dem Schnitt.
  - Rotes Licht nur als Schein der Monitore, der Raum bleibt wie er ist.
  - Erst auswählen (vier Startbilder), dann Entwurf in 480p, dann Endfassung. Nie einen einzigen Versuch abliefern.

Ablauf des Spots:
  0–5 s   Clip A: ruhiges Entwicklerbüro, dann werden die Monitore rot, alle schrecken hoch, Kaffee schwappt über
  5–6,5 s Rücklauf: Clip A rückwärts und schnell
  6,5–8 s Clip B: dieselbe Szene ruhig, der Entwickler trinkt einen Schluck
  8–10 s  Schlussbild schwarz mit Schriftzug
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import lauf
from anbieter import Higgsfield, http_json, lade_datei, _schluessel

SID = "W002"
LIMIT_USD = 5.0
MARKE = "PENTEST EXPERTS"
SPRUCH = "Schwachstellen finden, bevor es knallt."
EINBLENDUNG = "RANSOMWARE – ALLE DATEN VERSCHLÜSSELT"

BILD_MODELL = "higgsfield-ai/soul/v2/standard"
VIDEO_MODELL = "bytedance/seedance-2.5/image-to-video"
VIDEO_USD_S = 0.0738   # Listenpreis 1080p laut Higgsfield-Blog; die Preisabfrage liefert für Seedance keinen Wert
BILD_USD = 0.01
ANZAHL_BILDER = 4

BILD = ("Candid documentary photograph inside a real software company office in the early evening, not staged, not a stock "
        "photo. Three male software developers at a shared row of desks. In the foreground, seen from the side in a "
        "medium shot: a developer in his mid thirties with a short beard, glasses and a grey hoodie, headphones around his "
        "neck, sitting slightly slouched, his right hand holding a plain dark coffee mug by its handle, half raised above "
        "the desk, his left hand resting on a mechanical keyboard. In front of him two monitors showing a dark code editor "
        "with small coloured lines of code, too small to read. Behind him two colleagues in t-shirts, one with headphones "
        "on, both typing and looking at their own screens. Slightly messy desks: cables, sticky notes, a water bottle, an "
        "energy drink can, a laptop with stickers. Ordinary ceiling light mixed with cool monitor glow, ordinary people "
        "with normal skin and tired eyes, natural asymmetry, slight image noise, shot handheld on a 35mm lens at eye "
        "level, 16:9. No readable text, no logos, no watermark.")
CLIP_A = ("One continuous handheld documentary shot with subtle natural camera movement, no cuts. Seconds 0 to 2: quiet "
          "concentration, the developer in the foreground keeps holding his coffee mug by the handle and brings it towards "
          "his mouth, the two colleagues type. At second 2: every monitor in the room switches at the same instant to a "
          "plain solid red screen with one white padlock icon, no text. The room lighting stays the same, only a soft red "
          "glow from the screens falls on the faces. Seconds 2 to 5: the developer jerks back in shock, coffee sloshes out "
          "of the mug in his hand onto the keyboard, he sets the mug down hard, the colleagues spin around and half stand "
          "up, staring at their screens. Realistic physics, natural motion speed, hands stay anatomically correct. Sound: "
          "quiet keyboard typing, then a harsh alarm tone, startled voices. No subtitles, no captions, no watermark.")
CLIP_B = ("One continuous handheld documentary shot with subtle natural camera movement, no cuts. Everything is calm and "
          "normal. The monitors keep showing the dark code editor. The developer in the foreground, still holding his "
          "coffee mug by the handle, takes a slow relaxed sip and breathes out, the two colleagues keep typing. Realistic "
          "natural motion, hands stay anatomically correct. Sound: quiet keyboard typing, soft office ambience. "
          "No subtitles, no captions, no watermark.")
A_S, B_S = 5, 4          # erzeugte Längen (Seedance: 4 bis 30 s)
RUECK_VON, RUECK_S = 1.5, 1.5    # Rücklauf zeigt Clip A von 5,0 s zurück bis 1,5 s, zusammengedrückt auf 1,5 s
B_AB, B_TEMPO, B_ZEIG = 0.3, 1.6, 1.5
ENDE_S = 2.0
B, H, FPS = 1920, 1080, 30
FETT = "font='DejaVu Sans\\:style=Bold':"


def ff(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True, cwd=cwd)


def hat_ton(p: Path) -> bool:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0",
                        str(p)], capture_output=True, text=True)
    return bool(r.stdout.strip())


def preis(modell: str, eingabe: dict, ersatz: float) -> float:
    """Preisabfrage bei Higgsfield (POST /estimate/<Modell>). Klappt sie nicht, gilt der Listenpreis."""
    try:
        r = http_json("POST", f"{Higgsfield.BASIS}/estimate/{modell}",
                      {"Authorization": f"Key {_schluessel('HIGGSFIELD_KEY')}"}, eingabe)
        return float(r["usd"])
    except Exception as ex:  # noqa: BLE001 - die Schätzung darf den Lauf nicht verhindern
        print(f"Preisabfrage {modell} ohne Wert ({lauf.maskiere(str(ex))[:80]}), rechne mit {ersatz:.2f} USD")
        return ersatz


class Kasse:
    """Bucht ins Kostenbuch und hält die Grenze dieses Tests ein."""

    def __init__(self) -> None:
        self.buch = lauf.buecher()[0]
        self.summe = self.buch.summe(short=SID)

    def zahlen(self, posten: str, usd: float) -> None:
        if self.summe + usd > LIMIT_USD:
            sys.exit(f"Grenze {LIMIT_USD} USD: {posten} würde {usd:.2f} USD kosten, bisher {self.summe:.2f} USD")
        self.summe += usd
        self.buch.buchen(SID, posten, usd, "higgsfield")


def platzhalter_bild(ziel: Path, farbe: str) -> None:
    ff("-f", "lavfi", "-i", f"color=c={farbe}:s={B}x{H}", "-frames:v", "1", str(ziel))


def platzhalter_clip(ziel: Path, sekunden: int, farbe: str) -> None:
    ff("-f", "lavfi", "-i", f"testsrc2=s={B}x{H}:r={FPS}:d={sekunden}", "-f", "lavfi", "-i", f"sine=f=440:d={sekunden}",
       "-vf", f"drawbox=c={farbe}@0.4:t=fill", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-shortest", str(ziel))


def auswahlbogen(arbeit: Path, bilder: list[Path]) -> None:
    eingaben, graph = [], []
    for i, p in enumerate(bilder):
        eingaben += ["-i", str(p)]
        graph.append(f"[{i}:v]scale=960:540:force_original_aspect_ratio=increase,crop=960:540,"
                     f"drawbox=x=0:y=0:w=110:h=96:color=black@0.75:t=fill,"
                     f"drawtext={FETT}text='{i + 1}':fontsize=72:fontcolor=white:x=34:y=10[b{i}]")
    graph.append("".join(f"[b{i}]" for i in range(len(bilder))) + "xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0[v]")
    ff(*eingaben, "-filter_complex", ";".join(graph), "-map", "[v]", "-frames:v", "1", "-q:v", "3",
       str(arbeit / "auswahl.jpg"))


def stufe_bilder(arbeit: Path, probe: bool) -> int:
    bilder = [arbeit / f"start_{n}.png" for n in range(1, ANZAHL_BILDER + 1)]
    if probe:
        for p, farbe in zip(bilder, ("gray", "navy", "darkgreen", "maroon")):
            platzhalter_bild(p, farbe)
        urls = ["https://probe.invalid/bild.png"] * ANZAHL_BILDER
    else:
        kasse = Kasse()
        eingabe = {"prompt": BILD, "aspect_ratio": "16:9", "resolution": "1080p", "batch_size": ANZAHL_BILDER,
                   "enhance_prompt": False}
        usd = preis(BILD_MODELL, eingabe, BILD_USD * ANZAHL_BILDER)
        kasse.zahlen("bilder", usd)
        r = Higgsfield()._lauf(BILD_MODELL, eingabe)
        urls = [b["url"] for b in r["images"]][:ANZAHL_BILDER]
        if len(urls) < ANZAHL_BILDER:
            sys.exit(f"nur {len(urls)} Bilder erhalten")
        for p, url in zip(bilder, urls):
            lade_datei(url, p)
        print(f"{ANZAHL_BILDER} Startbilder fertig ({usd:.3f} USD)", flush=True)
    (arbeit / "start_urls.json").write_text(json.dumps(urls), encoding="utf-8")
    auswahlbogen(arbeit, bilder)
    print("fertig: auswahl.jpg")
    return 0


def erzeugen(arbeit: Path, url: str, aufloesung: str, takes: int, probe: bool) -> list[tuple[Path, Path]]:
    paare = []
    kasse = None if probe else Kasse()
    faktor = {"480p": 0.35, "720p": 0.6}.get(aufloesung, 1.0)   # grobe Annahme, der Listenpreis gilt für 1080p
    for t in range(1, takes + 1):
        paar = []
        for name, prompt, sekunden, farbe in (("a", CLIP_A, A_S, "green"), ("b", CLIP_B, B_S, "blue")):
            ziel = arbeit / f"clip_{name}_{aufloesung}_t{t}.mp4"
            paar.append(ziel)
            if ziel.exists() and ziel.stat().st_size > 50_000:
                continue
            if probe:
                platzhalter_clip(ziel, sekunden, farbe)
                continue
            eingabe = {"image_url": url, "prompt": prompt, "duration": sekunden, "resolution": aufloesung,
                       "generate_audio": True}
            usd = preis(VIDEO_MODELL, eingabe, VIDEO_USD_S * sekunden * faktor)
            kasse.zahlen(ziel.stem, usd)
            r = Higgsfield()._lauf(VIDEO_MODELL, eingabe, max_warten_s=1200)
            lade_datei(r["video"]["url"], ziel)
            print(f"{ziel.name} fertig ({usd:.2f} USD angesetzt)", flush=True)
        paare.append((paar[0], paar[1]))
    return paare


def schneiden(arbeit: Path, a: Path, b: Path, einblendung: bool, ziel: Path) -> None:
    bild = f"scale={B}:{H}:force_original_aspect_ratio=increase,crop={B}:{H},fps={FPS},setsar=1"
    ton = "aresample=48000,aformat=channel_layouts=stereo"
    stille = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    kodieren = ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
    (arbeit / "einblendung.txt").write_text(EINBLENDUNG, encoding="utf-8")
    (arbeit / "marke.txt").write_text(MARKE, encoding="utf-8")
    (arbeit / "spruch.txt").write_text(SPRUCH, encoding="utf-8")

    # Teil 1: Clip A, Warnzeile ab Sekunde 2,2
    zusatz = ""
    if einblendung:
        zusatz = (f",drawbox=x=0:y=ih-170:w=iw:h=120:color=0xB00000@0.9:t=fill:enable='gte(t,2.2)',"
                  f"drawtext={FETT}textfile=einblendung.txt:fontsize=62:fontcolor=white:x=(w-text_w)/2:y=h-170+28:"
                  f"enable='gte(t,2.2)'")
    quelle_ton = ["-i", str(a)] if hat_ton(a) else stille
    ff("-i", str(a), *quelle_ton, "-filter_complex",
       f"[0:v]{bild},trim=duration={A_S},setpts=PTS-STARTPTS{zusatz}[v];[1:a]{ton},atrim=duration={A_S}[a]",
       "-map", "[v]", "-map", "[a]", "-t", str(A_S), *kodieren, "teil1.mp4", cwd=arbeit)

    # Teil 2: Rücklauf aus Clip A (rückwärts, schnell, leicht entsättigt, Bildrauschen), Ton: Wusch oder Stille
    tempo = (A_S - RUECK_VON) / RUECK_S
    wusch = Path(__file__).parent / "musik" / "geraeusche" / "whoosh.mp3"
    ton2 = ["-i", str(wusch)] if wusch.exists() else stille
    ff("-i", str(a), *ton2, "-filter_complex",
       f"[0:v]{bild},trim=start={RUECK_VON}:end={A_S},setpts=PTS-STARTPTS,reverse,setpts=PTS/{tempo:.4f},"
       f"eq=saturation=0.6:contrast=1.08,noise=alls=22:allf=t,trim=duration={RUECK_S}[v];"
       f"[1:a]{ton},atrim=duration={RUECK_S},apad=whole_dur={RUECK_S}[a]",
       "-map", "[v]", "-map", "[a]", "-t", str(RUECK_S), *kodieren, "teil2.mp4", cwd=arbeit)

    # Teil 3: Clip B, etwas schneller, damit der Schluck in 1,5 s passt
    quelle_ton = ["-i", str(b)] if hat_ton(b) else stille
    ende_b = B_AB + B_ZEIG * B_TEMPO
    ff("-i", str(b), *quelle_ton, "-filter_complex",
       f"[0:v]{bild},trim=start={B_AB}:end={ende_b:.3f},setpts=(PTS-STARTPTS)/{B_TEMPO}[v];"
       f"[1:a]{ton},atrim=start={B_AB}:end={ende_b:.3f},asetpts=PTS-STARTPTS,atempo={B_TEMPO},apad=whole_dur={B_ZEIG}[a]",
       "-map", "[v]", "-map", "[a]", "-t", str(B_ZEIG), *kodieren, "teil3.mp4", cwd=arbeit)

    # Teil 4: Schlussbild, fette Schrift
    ff("-f", "lavfi", "-i", f"color=c=black:s={B}x{H}:r={FPS}:d={ENDE_S}", *stille, "-filter_complex",
       f"[0:v]drawtext={FETT}textfile=marke.txt:fontsize=150:fontcolor=white:x=(w-text_w)/2:y=h/2-170,"
       f"drawtext=font='DejaVu Sans':textfile=spruch.txt:fontsize=56:fontcolor=white:x=(w-text_w)/2:y=h/2+50,"
       f"fade=t=in:st=0:d=0.25,setsar=1[v]",
       "-map", "[v]", "-map", "1:a", "-t", str(ENDE_S), *kodieren, "teil4.mp4", cwd=arbeit)

    ff("-i", "teil1.mp4", "-i", "teil2.mp4", "-i", "teil3.mp4", "-i", "teil4.mp4", "-filter_complex",
       "[0:v][0:a][1:v][1:a][2:v][2:a][3:v][3:a]concat=n=4:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]",
       "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-maxrate", "12M", "-bufsize", "24M", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(ziel), cwd=arbeit)
    # Prüfbogen mit grossen Einzelbildern: 10 Bilder, je 960x540
    ff("-i", str(ziel), "-vf", "fps=1,scale=960:540,tile=2x5", "-frames:v", "1", "-q:v", "3",
       str(ziel.with_name(ziel.stem + "_bogen.jpg")))


def stufe_video(arbeit: Path, a: argparse.Namespace) -> int:
    if a.probe:
        url = "https://probe.invalid/bild.png"
    else:
        datei = arbeit / "start_urls.json"
        if not datei.exists():
            sys.exit("start_urls.json fehlt: zuerst Stufe 'bilder' laufen lassen und deren Lauf-Nummer angeben")
        url = json.loads(datei.read_text(encoding="utf-8"))[a.bild - 1]
    paare = erzeugen(arbeit, url, a.aufloesung, a.takes, a.probe)
    for t, (ca, cb) in enumerate(paare, 1):
        ziel = arbeit / f"pentest_experts_{a.aufloesung}_t{t}.mp4"
        schneiden(arbeit, ca, cb, not a.ohne_einblendung, ziel)
        print(f"fertig: {ziel.name}")
    usd = 0.0 if a.probe else lauf.buecher()[0].summe(short=SID)
    (arbeit / "info.json").write_text(json.dumps({"bild": a.bild, "aufloesung": a.aufloesung, "takes": a.takes,
                                                  "usd": round(usd, 2), "probe": a.probe}))
    print(f"Kosten dieses Tests bisher {usd:.2f} USD (Clips nach Listenpreis geschätzt)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("stufe", choices=("bilder", "video"))
    p.add_argument("--bild", type=int, default=1, choices=range(1, ANZAHL_BILDER + 1))
    p.add_argument("--aufloesung", default="480p", choices=("480p", "720p", "1080p"))
    p.add_argument("--takes", type=int, default=1, choices=(1, 2))
    p.add_argument("--ohne-einblendung", action="store_true")
    p.add_argument("--probe", action="store_true")
    a = p.parse_args()
    arbeit = lauf.arbeitsordner() / "werbung"
    arbeit.mkdir(parents=True, exist_ok=True)
    return stufe_bilder(arbeit, a.probe) if a.stufe == "bilder" else stufe_video(arbeit, a)


if __name__ == "__main__":
    sys.exit(main())
