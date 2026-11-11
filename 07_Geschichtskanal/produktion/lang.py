"""Langvideos (ca. 8–12 Minuten, 16:9) im flachen 2D-Illustrationsstil – Format „Why You'd Never Survive …“.

Ablauf: Stimme (ElevenLabs, kapitelweise) → Szenenzeiten aus den Wortzeiten → je Szene eine Illustration
(Recraft V3 über fal, feste Farbpalette) mit Sichtprüfung → Kamerafahrt je Szene (ffmpeg zoompan) →
Schlagwörter groß eingeblendet (ASS) → Filmkorn, Vignette → Musik mit Ducking und Geräusche.

Aufruf:  python lang.py produziere L001 [--probe]
         python lang.py stiltest              (6 Testbilder in 3 Stilen, ca. 0,25 USD)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import lauf
import schnitt
from anbieter import ElevenLabs, Fal, lade_datei
from plan_schema import MUSIK, PlanFehler, norm

KONF = lauf.KONF
LK = KONF["lang"]
B, H, FPS = 1920, 1080, 30
BEWEGUNGEN = {"zoom_rein", "zoom_raus", "schwenk_links", "schwenk_rechts", "statisch"}
STIMMUNGEN = {"ruhig", "spannung", "gefahr", "ehrfurcht"}
ZOOM = {  # langsam, damit 6–8 s ruhig wirken; Eingabe ist ein einzelnes Bild in doppelter Größe
    "zoom_rein": "zoompan=z='min(1+0.0006*on,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    "zoom_raus": "zoompan=z='max(1.12-0.0006*on,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    "schwenk_links": "zoompan=z=1.1:x='(iw-iw/zoom)*(1-on/{n})':y='ih/2-(ih/zoom/2)'",
    "schwenk_rechts": "zoompan=z=1.1:x='(iw-iw/zoom)*on/{n}':y='ih/2-(ih/zoom/2)'",
    "statisch": "zoompan=z='1.02+0.0001*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
}


# --- Plan ---------------------------------------------------------------------
def pruefe_langplan(p: dict) -> list[str]:
    f = []
    if p.get("format") != "lang":
        f.append("format muss 'lang' sein")
    if not str(p.get("titel", "")).strip() or len(p["titel"]) > 100:
        f.append("titel fehlt oder zu lang")
    m = p.get("musik")
    if m is not None and (not isinstance(m, str) or not MUSIK.fullmatch(m)):
        f.append("musik: nur Dateiname")
    sz = p.get("szenen")
    if not isinstance(sz, list) or not 40 <= len(sz) <= 120:
        return f + ["szenen: 40–120 erwartet"]
    woerter = 0
    for i, s in enumerate(sz, 1):
        t = s.get("text")
        if not isinstance(t, str) or not 3 <= len(t.split()) <= 35:
            f.append(f"#{i} text: 3–35 Wörter")
            continue
        if re.search(r"[<>{}\\\[\]]", t):
            f.append(f"#{i} text: Steuerzeichen")
        woerter += len(t.split())
        if not isinstance(s.get("bild"), str) or not 10 <= len(s["bild"]) <= 700:
            f.append(f"#{i} bild: 10–700 Zeichen")
        w = s.get("wort")
        if w is not None and (not isinstance(w, str) or len(w) > 32 or re.search(r"[<>{}\\]", w)):
            f.append(f"#{i} wort: höchstens 32 Zeichen")
        if s.get("bewegung", "statisch") not in BEWEGUNGEN:
            f.append(f"#{i} bewegung unbekannt")
        if s.get("stimmung", "ruhig") not in STIMMUNGEN:
            f.append(f"#{i} stimmung unbekannt")
        g = s.get("geraeusch")
        if g is not None and (not isinstance(g, str) or not MUSIK.fullmatch(g)):
            f.append(f"#{i} geraeusch: nur Dateiname")
    if not LK["woerter_min"] <= woerter <= LK["woerter_max"]:
        f.append(f"{woerter} Wörter, erwartet {LK['woerter_min']}–{LK['woerter_max']}")
    for k in p.get("kapitel", []):
        if not isinstance(k.get("titel"), str) or not isinstance(k.get("ab_szene"), int) or not 1 <= k["ab_szene"] <= len(sz):
            f.append(f"kapitel ungültig: {k}")
    return f


def lade_langplan(pfad: Path) -> dict:
    try:
        p = json.loads(pfad.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as ex:
        raise PlanFehler(f"kein gültiges JSON: {ex}") from None
    fehler = pruefe_langplan(p)
    if fehler:
        raise PlanFehler("; ".join(fehler[:12]))
    for s in p["szenen"]:
        s["text"], s["bild"] = norm(s["text"]), norm(s["bild"])
    return p


def schaetze_kosten(p: dict) -> float:
    zeichen = sum(len(s["text"]) for s in p["szenen"])
    bilder = len(p["szenen"]) * LK["bild_preis_usd"] * 1.3  # 30 % Reserve für Neuversuche
    return round(bilder + zeichen / 1000 * KONF["stimme"]["preis_usd_pro_1000_zeichen"] + len(p["szenen"]) * 0.002, 2)


# --- Bausteine ----------------------------------------------------------------
def bild(fal: Fal, prompt: str, ziel: Path) -> Path:
    if fal.probe:
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x1d3b4a:s={B}x{H}", "-frames:v", "1", str(ziel)],
                       capture_output=True, check=True)
        return ziel
    r = fal._lauf(LK["bild_modell"], {"prompt": prompt[:1000], "image_size": "landscape_16_9", "style": LK["bild_stil"],
                                      "colors": LK.get("farben", [])})
    roh = lade_datei(r["images"][0]["url"], ziel.with_suffix(".roh"))
    subprocess.run(["ffmpeg", "-y", "-i", str(roh), "-vf", f"scale={B}:{H}:force_original_aspect_ratio=increase,crop={B}:{H}",
                    str(ziel)], capture_output=True, check=True)  # webp/png → png in Zielgröße
    roh.unlink(missing_ok=True)
    return ziel


def dauer(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def stimme(plan: dict, arbeit: Path, probe: bool) -> tuple[Path, list[dict]]:
    """Kapitelweise sprechen (API-Grenze), dann zusammensetzen; Wortzeiten werden verschoben."""
    st = KONF["stimme"]
    grenzen = [k["ab_szene"] - 1 for k in plan.get("kapitel", [])] or [0]
    grenzen = sorted(set([0] + grenzen)) + [len(plan["szenen"])]
    teile, woerter, versatz = [], [], 0.0
    for n, (a, z) in enumerate(zip(grenzen, grenzen[1:]), 1):
        text = " ".join(s["text"] for s in plan["szenen"][a:z])
        if not text:
            continue
        ziel = arbeit / f"stimme_{n:02d}.mp3"
        w = ElevenLabs(probe).sprechen(text, LK.get("voice_id") or st["voice_id"], st["modell"], ziel)
        if probe:
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono", "-t",
                            f"{(w[-1]['ende'] if w else 1) + 0.4:.2f}", str(ziel)], capture_output=True, check=True)
        woerter += [{"wort": x["wort"], "start": x["start"] + versatz, "ende": x["ende"] + versatz} for x in w]
        versatz += dauer(ziel)
        teile.append(ziel)
    liste = arbeit / "stimme.txt"
    liste.write_text("".join(f"file '{t.as_posix()}'\n" for t in teile), encoding="utf-8")
    gesamt = arbeit / "stimme.mp3"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(liste), "-c:a", "libmp3lame", "-b:a", "192k",
                    str(gesamt)], capture_output=True, check=True)
    return gesamt, woerter


def ass_woerter(plan: dict, zeiten: list[tuple[float, float]]) -> str:
    """Schlagwörter groß und Kapiteltitel klein oben; keine laufenden Untertitel (wie im Vorbild)."""
    kopf = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, "
            "Shadow, Alignment, MarginL, MarginR, MarginV\n"
            f"Style: Wort,{LK['schrift']},96,&H00DCEBF5,&H00000000,&H78000000,-1,1,0,4,2,80,80,150\n"
            f"Style: Kapitel,{LK['schrift']},44,&H00DCEBF5,&H00000000,&H96000000,-1,3,8,0,8,80,80,60\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Text\n")
    z = []
    kapitel = {k["ab_szene"]: k["titel"] for k in plan.get("kapitel", [])}
    for i, (s, (a, e)) in enumerate(zip(plan["szenen"], zeiten), 1):
        if i in kapitel and i > 1:
            z.append(f"Dialogue: 1,{schnitt._ass_zeit(a + 0.2)},{schnitt._ass_zeit(min(a + 3.2, e))},Kapitel,"
                     f"{{\\fad(300,300)}}{kapitel[i].upper()}")
        if s.get("wort"):
            w = s["wort"].replace("{", "").replace("}", "").replace("\\", "").upper()
            z.append(f"Dialogue: 0,{schnitt._ass_zeit(a + 0.35)},{schnitt._ass_zeit(max(a + 1.0, e - 0.15))},Wort,"
                     f"{{\\fad(250,200)}}{w}")
    return kopf + "\n".join(z) + "\n"


def szenen_befehle(plan: dict, zeiten: list[tuple[float, float]], bilder: list[Path], arbeit: Path) -> list[list[str]]:
    out, teile = [], []
    for n, ((a, e), s, b) in enumerate(zip(zeiten, plan["szenen"], bilder), 1):
        frames = max(int(round((e - a) * FPS)), FPS)
        z = ZOOM.get(s.get("bewegung", "statisch"), ZOOM["statisch"]).format(n=frames)
        vf = (f"scale={B * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={B * 2}:{H * 2},"
              f"{z}:d={frames}:s={B}x{H}:fps={FPS},fade=t=in:st=0:d=0.2,setsar=1")
        teil = arbeit / f"szene_{n:03d}.mp4"
        out.append(["ffmpeg", "-y", "-i", str(b), "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(teil)])
        teile.append(f"file '{teil.as_posix()}'")
    liste = arbeit / "szenen.txt"
    out.append(["#schreibe", str(liste), "\n".join(teile) + "\n"])
    out.append(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(liste), "-c", "copy", str(arbeit / "bild.mp4")])
    return out


def mix_befehl(bild_mp4: Path, stimme_mp3: Path, musik: Path | None, geraeusche: list[Path | None],
               zeiten: list[tuple[float, float]], ass: Path, ziel: Path) -> list[str]:
    ass_pfad = ass.as_posix().replace(":", "\\:")
    korn = int(KONF.get("filmkorn", {}).get("staerke", 0))
    vf = f"vignette=PI/6,{'noise=alls=%d:allf=t,' % korn if korn else ''}ass='{ass_pfad}'"
    ein, graph, mix = ["-i", str(bild_mp4), "-i", str(stimme_mp3)], [], ["[1:a]"]
    if musik:
        ein += ["-stream_loop", "-1", "-i", str(musik)]
        graph.append(f"[2:a]volume={LK['musik_db']}dB[mu];[mu][1:a]sidechaincompress=threshold=0.03:ratio=6:attack=30:release=600[duck]")
        mix.append("[duck]")
    for n, ((a, e), g) in enumerate(zip(zeiten, geraeusche), 1):
        if not g:
            continue
        idx = ein.count("-i")
        ein += ["-i", str(g)]
        d, ms = max(e - a, 0.5), int(a * 1000)
        graph.append(f"[{idx}:a]atrim=0:{d:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.2,afade=t=out:st={max(d - 0.6, 0):.3f}:d=0.6,"
                     f"volume={KONF.get('geraeusche', {}).get('lautstaerke_db', -14)}dB,adelay={ms}|{ms}[g{n}]")
        mix.append(f"[g{n}]")
    graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    return ["ffmpeg", "-y", *ein, "-filter_complex", ";".join(graph), "-map", "0:v", "-map", "[a]", "-vf", vf,
            "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-maxrate", "8M", "-bufsize", "16M", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(ziel)]


def kapitelmarken(plan: dict, zeiten: list[tuple[float, float]]) -> str:
    """YouTube-Kapitel: erste Marke 0:00, mindestens 10 s Abstand. Wird beim Upload an die Beschreibung angehängt."""
    zeilen, letzte = [], -999.0
    for k in sorted(plan.get("kapitel", []), key=lambda k: k["ab_szene"]):
        t = 0.0 if not zeilen else zeiten[k["ab_szene"] - 1][0]
        if t - letzte < 10:
            continue
        m, s = divmod(int(t), 60)
        zeilen.append(f"{m}:{s:02d} {k['titel']}")
        letzte = t
    return "\n".join(zeilen) if len(zeilen) >= 3 else ""


def kontaktbogen(video: Path, ziel: Path, n: int = 24) -> None:
    d = dauer(video)
    ordner = ziel.parent / "kontakt"
    ordner.mkdir(exist_ok=True)
    for i in range(n):
        subprocess.run(["ffmpeg", "-y", "-ss", f"{d * (i + 0.5) / n:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=384:216", str(ordner / f"k_{i:02d}.jpg")], capture_output=True, check=True)
    subprocess.run(["ffmpeg", "-y", "-framerate", "1", "-i", str(ordner / "k_%02d.jpg"), "-vf",
                    "tile=6x4:padding=4:color=white", "-frames:v", "1", str(ziel)], capture_output=True, check=True)


# --- Ablauf -------------------------------------------------------------------
def produziere(sid: str, probe: bool) -> Path:
    lauf.pause_pruefen()
    kosten, _, fehler, quar = lauf.buecher()
    pp = lauf.plan_pfad(sid)
    if not probe:
        lauf.pruef_freigabe(sid, pp)
    plan = lade_langplan(pp)
    musik = lauf.musik_pfad(plan, probe)
    geraeusche = lauf.geraeusch_pfade({"einstellungen": plan["szenen"]}, probe)
    rest = KONF["budget"]["limit_monat_usd"] - kosten.summe(monat=lauf.datetime.now(lauf.timezone.utc).strftime("%Y-%m"))
    if schaetze_kosten(plan) > min(rest, LK["limit_video_usd"]):
        raise lauf.Gesperrt(f"{sid}: Budget reicht nicht (Schätzung {schaetze_kosten(plan)} USD)")
    arbeit = lauf.arbeitsordner() / "medien" / sid
    arbeit.mkdir(parents=True, exist_ok=True)
    fal = Fal(probe)
    try:
        if not probe:
            kosten.buchen(sid, "stimme", sum(len(s["text"]) for s in plan["szenen"]) / 1000
                          * KONF["stimme"]["preis_usd_pro_1000_zeichen"], "elevenlabs")
        sprache, woerter = stimme(plan, arbeit, probe)
        zeiten = schnitt.zeiten_je_einstellung({"einstellungen": plan["szenen"]}, woerter)
        bilder = []
        for n, s in enumerate(plan["szenen"], 1):
            prompt = f"{s['bild']}. {LK['stil_text']}"
            ziel = arbeit / f"bild_{n:03d}.png"
            for v in (1, 2):
                if not probe:
                    kosten.buchen(sid, f"bild_{n}_v{v}", LK["bild_preis_usd"], "fal")
                bild(fal, prompt, ziel)
                probleme = lauf.sicht_pruefen(fal, ziel, kosten, sid, f"sicht_{n}_v{v}", fehler, sid)
                if not probleme:
                    break
                fehler.eintragen(sid, f"bild_{n}_v{v}", ", ".join(probleme))
            bilder.append(ziel)  # zweiter Fehlversuch: Bild bleibt, der Kontaktbogen zeigt es dem Chef-Agenten
        ass = arbeit / "woerter.ass"
        ass.write_text(ass_woerter(plan, zeiten), encoding="utf-8")
        lauf.ffmpeg_ausfuehren(szenen_befehle(plan, zeiten, bilder, arbeit), False)
        ziel = arbeit / f"{sid}_final.mp4"
        subprocess.run(mix_befehl(arbeit / "bild.mp4", sprache, musik, geraeusche, zeiten, ass, ziel),
                       capture_output=True, check=True)
        kontaktbogen(ziel, arbeit / "kontaktbogen.jpg")
        (arbeit / "kapitel.txt").write_text(kapitelmarken(plan, zeiten), encoding="utf-8")
        d = dauer(ziel)
        if not probe and not LK["dauer_min_s"] <= d <= LK["dauer_max_s"]:
            raise lauf.Gesperrt(f"{sid}: Länge {d:.0f} s außerhalb {LK['dauer_min_s']}–{LK['dauer_max_s']} s")
        (arbeit / "fertig.json").write_text(json.dumps({"plan_sha256": lauf.sha256(pp), "stufe": "pruefung",
                                                        "video_sha256": lauf.sha256(ziel), "dauer_s": round(d, 1)}),
                                            encoding="utf-8")
        return ziel
    except Exception as ex:
        fehler.eintragen(sid, "langvideo", f"{type(ex).__name__}: {ex}")
        if not probe:
            quar.sperren(sid, f"Langvideo gescheitert: {ex}")
        raise


def stiltest() -> Path:
    """Gleiche zwei Motive in drei Stilen – zur Auswahl durch Nutzer und Chef-Agenten."""
    fal = Fal(False)
    kosten, *_ = lauf.buecher()
    arbeit = lauf.arbeitsordner() / "medien" / "stiltest"
    arbeit.mkdir(parents=True, exist_ok=True)
    motive = {"stadt": "the Roman town of Pompeii at dawn, red-tiled roofs and a forum, the cone-shaped Mount Vesuvius "
                       "in muted purple-grey looming behind, a thin plume of smoke, a simple dark silhouette of a young "
                       "Roman in a beige tunic standing on a street in the foreground",
              "saeule": "a gigantic dark eruption column rising from Mount Vesuvius into the sky, tiny town below, "
                        "ash clouds spreading, dramatic warm light"}
    for stil in LK["stiltest_stile"]:
        for name, m in motive.items():
            kosten.buchen("stiltest", f"{stil}_{name}", LK["bild_preis_usd"], "fal")
            r = fal._lauf(LK["bild_modell"], {"prompt": f"{m}. {LK['stil_text']}", "image_size": "landscape_16_9",
                                              "style": stil, "colors": LK.get("farben", [])})
            lade_datei(r["images"][0]["url"], arbeit / f"{stil.replace('/', '_')}_{name}.webp")
    return arbeit


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="lang")
    ap.add_argument("befehl", choices=["produziere", "stiltest"])
    ap.add_argument("sid", nargs="?")
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args(argv)
    if a.befehl == "stiltest":
        print(stiltest())
        return 0
    if not a.sid or not re.fullmatch(r"L\d{3}", a.sid):
        print("Langvideo-Nummer wie L001 angeben")
        return 2
    print(produziere(a.sid, a.probe))
    return 0


if __name__ == "__main__":
    sys.exit(main())
