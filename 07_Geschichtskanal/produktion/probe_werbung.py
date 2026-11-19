"""10-Sekunden-Werbetest (fotorealistisch, 16:9) über Higgsfield: Soul Cinema + Seedance 2.5. Kein Upload.

Aufruf: python probe_werbung.py [--probe]   (Umgebung: HIGGSFIELD_KEY, GK_ARBEIT)
  --probe  ohne Netz und ohne Kosten: Platzhalter-Clips, um den Schnitt zu prüfen.

Ablauf des Spots (Vorgabe des Nutzers, 19.11.2026):
  0–5 s   Clip A: Büro, Frau greift zur Tasse, Monitor wird rot (Ransomware), alle schrecken hoch, Kaffee kippt
  5–6,5 s Rücklauf: Clip A rückwärts und schnell (echter Rückspuleffekt aus demselben Material)
  6,5–8 s Clip B: dieselbe Szene ruhig, die Frau trinkt einen Schluck
  8–10 s  Schlussbild schwarz mit Schriftzug (im Schnitt gesetzt, weil Video-KI Schrift oft verfälscht)
Beide Clips starten vom selben Startbild, damit Personen und Raum gleich bleiben.
Vor jedem Auftrag fragt das Skript den Preis bei Higgsfield ab und bricht über der Grenze ab.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import lauf
from anbieter import Higgsfield, http_json, lade_datei, _schluessel

SID = "W001"
LIMIT_USD = 4.0
MARKE = "PENTEST EXPERTS"
SPRUCH = "Schwachstellen finden, bevor es knallt."
EINBLENDUNG = "RANSOMWARE – ALLE DATEN VERSCHLÜSSELT"

BILD_MODELL = "higgsfield-ai/soul/cinema"
VIDEO_MODELL = "bytedance/seedance-2.5/image-to-video"
VIDEO_USD_S = 0.0738   # Listenpreis laut Higgsfield-Blog; der echte Preis kommt aus der Preisabfrage
BILD_USD = 0.01

LOOK = ("photorealistic, shot on a full-frame cinema camera, 35mm lens, natural window light, shallow depth of field, "
        "realistic skin texture, true-to-life colours, 16:9 widescreen, level horizon")
BILD = ("A modern open-plan office in daylight. Three colleagues sit relaxed at their desks: in the foreground a woman in "
        "her thirties in a light blouse sits at her desk, seen from a three-quarter front angle, her right hand reaching "
        "towards a white coffee mug that stands next to her keyboard. Her large computer monitor is clearly visible and "
        "shows an ordinary calm desktop with a few windows. Behind her two colleagues, a man and a woman, work quietly at "
        "their own screens. Calm, everyday atmosphere. No text overlays, no logos, no watermark. " + LOOK)
CLIP_A = ("Single continuous shot, locked-off camera, no cuts. Seconds 0 to 2: calm office, the woman in the foreground "
          "reaches for her coffee mug and lifts it slightly. At second 2: her monitor suddenly flashes to a bright solid "
          "red warning screen with one big white word RANSOMWARE, red light spills onto her face. Seconds 2 to 5: all three "
          "colleagues flinch and jump up in shock, the woman knocks over the mug, coffee splashes across the keyboard and "
          "desk. Realistic physics, realistic motion, natural office sound, a loud alarm beep, startled gasps. "
          "No subtitles, no captions, no watermark.")
CLIP_B = ("Single continuous shot, locked-off camera, no cuts. The office is calm and safe. The monitor keeps showing the "
          "ordinary desktop. The woman in the foreground picks up her coffee mug right away, takes a relaxed sip and smiles "
          "slightly, the two colleagues behind her keep working quietly. Realistic motion, quiet office ambience. "
          "No subtitles, no captions, no watermark.")
A_S, B_S = 5, 4          # erzeugte Längen (Seedance: 4 bis 30 s)
RUECK_VON, RUECK_S = 1.5, 1.5    # Rücklauf zeigt Clip A von 5,0 s zurück bis 1,5 s, zusammengedrückt auf 1,5 s
B_AB, B_TEMPO, B_ZEIG = 0.3, 1.6, 1.5
ENDE_S = 2.0
B, H, FPS = 1920, 1080, 30


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


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
        print(f"Preisabfrage {modell} nicht möglich ({lauf.maskiere(str(ex))[:120]}), rechne mit {ersatz:.2f} USD")
        return ersatz


def platzhalter(ziel: Path, sekunden: int, farbe: str) -> None:
    ff("-f", "lavfi", "-i", f"testsrc2=s={B}x{H}:r={FPS}:d={sekunden}", "-f", "lavfi", "-i", f"sine=f=440:d={sekunden}",
       "-vf", f"drawbox=c={farbe}@0.4:t=fill", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-shortest", str(ziel))


def erzeugen(arbeit: Path, probe: bool) -> tuple[Path, Path]:
    a, b = arbeit / "clip_a.mp4", arbeit / "clip_b.mp4"
    if probe:
        platzhalter(a, A_S, "green")
        platzhalter(b, B_S, "blue")
        return a, b
    kosten = lauf.buecher()[0]
    hf = Higgsfield()
    summe = kosten.summe(short=SID)

    def pruefen(betrag: float, was: str) -> None:
        nonlocal summe
        if summe + betrag > LIMIT_USD:
            sys.exit(f"Grenze {LIMIT_USD} USD: {was} würde {betrag:.2f} USD kosten, bisher {summe:.2f} USD")
        summe += betrag

    start = arbeit / "start.png"
    url_datei = arbeit / "start_url.txt"
    if not (start.exists() and url_datei.exists()):
        eingabe = {"prompt": BILD, "aspect_ratio": "16:9", "resolution": "1080p", "batch_size": 1, "enhance_prompt": False}
        usd = preis(BILD_MODELL, eingabe, BILD_USD)
        pruefen(usd, "Startbild")
        kosten.buchen(SID, "bild", usd, "higgsfield")
        r = hf._lauf(BILD_MODELL, eingabe)
        url = r["images"][0]["url"]
        lade_datei(url, start)
        url_datei.write_text(url, encoding="utf-8")
        print(f"Startbild fertig ({usd:.3f} USD)", flush=True)
    url = url_datei.read_text(encoding="utf-8").strip()
    for ziel, prompt, sekunden, name in ((a, CLIP_A, A_S, "clip_a"), (b, CLIP_B, B_S, "clip_b")):
        if ziel.exists() and ziel.stat().st_size > 100_000:
            continue
        eingabe = {"image_url": url, "prompt": prompt, "duration": sekunden, "resolution": "1080p", "generate_audio": True}
        usd = preis(VIDEO_MODELL, eingabe, VIDEO_USD_S * sekunden)
        pruefen(usd, name)
        kosten.buchen(SID, name, usd, "higgsfield")
        r = hf._lauf(VIDEO_MODELL, eingabe, max_warten_s=1200)
        lade_datei(r["video"]["url"], ziel)
        print(f"{name} fertig ({usd:.2f} USD)", flush=True)
    return a, b


def schneiden(arbeit: Path, a: Path, b: Path, einblendung: bool) -> Path:
    bild = f"scale={B}:{H}:force_original_aspect_ratio=increase,crop={B}:{H},fps={FPS},setsar=1"
    ton = "aresample=48000,aformat=channel_layouts=stereo"
    stille = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    kodieren = ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
    schrift = "font='DejaVu Sans':"

    # Teil 1: Clip A, optional mit Warnzeile ab Sekunde 2,2
    (arbeit / "einblendung.txt").write_text(EINBLENDUNG, encoding="utf-8")
    zusatz = ""
    if einblendung:
        zusatz = (f",drawbox=x=0:y=ih-150:w=iw:h=110:color=0xB00000@0.88:t=fill:enable='gte(t,2.2)',"
                  f"drawtext={schrift}textfile=einblendung.txt:fontsize=58:fontcolor=white:x=(w-text_w)/2:y=h-150+26:"
                  f"enable='gte(t,2.2)'")
    t1 = arbeit / "teil1.mp4"
    quelle_ton = ["-i", str(a)] if hat_ton(a) else stille
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(a), *quelle_ton, "-filter_complex",
                    f"[0:v]{bild},trim=duration={A_S},setpts=PTS-STARTPTS{zusatz}[v];[1:a]{ton},atrim=duration={A_S}[a]",
                    "-map", "[v]", "-map", "[a]", "-t", str(A_S), *kodieren, "teil1.mp4"], check=True, cwd=arbeit)

    # Teil 2: Rücklauf aus Clip A (rückwärts, schnell, leicht entsättigt, Bildrauschen), Ton: Wusch oder Stille
    t2 = arbeit / "teil2.mp4"
    tempo = (A_S - RUECK_VON) / RUECK_S
    wusch = Path(__file__).parent / "musik" / "geraeusche" / "whoosh.mp3"
    ton2 = ["-i", str(wusch)] if wusch.exists() else stille
    ff("-i", str(a), *ton2, "-filter_complex",
       f"[0:v]{bild},trim=start={RUECK_VON}:end={A_S},setpts=PTS-STARTPTS,reverse,setpts=PTS/{tempo:.4f},"
       f"eq=saturation=0.6:contrast=1.08,noise=alls=22:allf=t,trim=duration={RUECK_S}[v];"
       f"[1:a]{ton},atrim=duration={RUECK_S},apad=whole_dur={RUECK_S}[a]",
       "-map", "[v]", "-map", "[a]", "-t", str(RUECK_S), *kodieren, str(t2))

    # Teil 3: Clip B, etwas schneller, damit der Schluck in 1,5 s passt
    t3 = arbeit / "teil3.mp4"
    quelle_ton = ["-i", str(b)] if hat_ton(b) else stille
    ende_b = B_AB + B_ZEIG * B_TEMPO
    ff("-i", str(b), *quelle_ton, "-filter_complex",
       f"[0:v]{bild},trim=start={B_AB}:end={ende_b:.3f},setpts=(PTS-STARTPTS)/{B_TEMPO}[v];"
       f"[1:a]{ton},atrim=start={B_AB}:end={ende_b:.3f},asetpts=PTS-STARTPTS,atempo={B_TEMPO},apad=whole_dur={B_ZEIG}[a]",
       "-map", "[v]", "-map", "[a]", "-t", str(B_ZEIG), *kodieren, str(t3))

    # Teil 4: Schlussbild
    (arbeit / "marke.txt").write_text(MARKE, encoding="utf-8")
    (arbeit / "spruch.txt").write_text(SPRUCH, encoding="utf-8")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"color=c=black:s={B}x{H}:r={FPS}:d={ENDE_S}", *stille, "-filter_complex",
                    f"[0:v]drawtext={schrift}textfile=marke.txt:fontsize=120:fontcolor=white:x=(w-text_w)/2:y=h/2-130,"
                    f"drawtext={schrift}textfile=spruch.txt:fontsize=46:fontcolor=white:x=(w-text_w)/2:y=h/2+40,"
                    f"fade=t=in:st=0:d=0.25,setsar=1[v]",
                    "-map", "[v]", "-map", "1:a", "-t", str(ENDE_S), *kodieren, "teil4.mp4"], check=True, cwd=arbeit)
    t4 = arbeit / "teil4.mp4"

    ziel = arbeit / "pentest_experts_10s.mp4"
    ff("-i", str(t1), "-i", str(t2), "-i", str(t3), "-i", str(t4), "-filter_complex",
       "[0:v][0:a][1:v][1:a][2:v][2:a][3:v][3:a]concat=n=4:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]",
       "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-maxrate", "12M", "-bufsize", "24M", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(ziel))
    ff("-i", str(ziel), "-vf", "fps=1,scale=480:270,tile=5x2", "-frames:v", "1", "-q:v", "3", str(arbeit / "kontaktbogen.jpg"))
    return ziel


def main() -> int:
    probe = "--probe" in sys.argv
    einblendung = "--einblendung" in sys.argv
    arbeit = lauf.arbeitsordner() / "werbung"
    arbeit.mkdir(parents=True, exist_ok=True)
    a, b = erzeugen(arbeit, probe)
    ziel = schneiden(arbeit, a, b, einblendung)
    sekunden = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                     str(ziel)], check=True, capture_output=True, text=True).stdout.strip())
    usd = 0.0 if probe else lauf.buecher()[0].summe(short=SID)
    (arbeit / "info.json").write_text(json.dumps({"dauer_s": round(sekunden, 2), "usd": round(usd, 2), "probe": probe}))
    print(f"fertig: {ziel.name}, {sekunden:.1f} s, Kosten {usd:.2f} USD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
