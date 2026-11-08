"""Steuerung der Produktion eines Shorts, von der Freigabe des Prüfers bis zum Upload.

  python lauf.py waehle                     nächsten Short wählen, gibt short=… und umgebung=… aus (Workflow)
  python lauf.py produziere 001 [--probe]   Stimme → Bilder → Videos → Schnitt → Qualitätsprüfung
  python lauf.py hochladen 001 [--probe]    Upload auf alle aktiven Plattformen
  python lauf.py naechster --probe          Probelauf des ganzen Tagesablaufs ohne Kosten

Sperren vor dem Upload (Stand nach Cyber-Agent-Prüfung CA-2026-11-07-13 bis -23):
  1. Neuester Prüfbericht: Zeile 1 genau „Ergebnis: freigegeben“, Zeile 2 „SHA-256: <Plan>“,
     Zeile 3 „Metadaten-SHA-256: <Metadaten>“. Ein „verworfen“ zum selben Plan sperrt diesen dauerhaft.
  2. GK_UPLOAD_ERLAUBT=ja und GK_UMGEBUNG kommen als Variablen der GitHub-Umgebung, nicht aus dem Workflow.
     Shorts der Stufe „pruefung“ (Naturkatastrophen, echte Personen, letzte 10 Jahre) laufen nur in der Umgebung
     mit Pflicht-Reviewer.
  3. GK_PAUSE=ja hält alles an (Not-Aus).
  4. Kein Short zweimal pro Plattform („begonnen“ zählt mit), höchstens max_uploads_pro_tag.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anbieter import ElevenLabs, Fal  # noqa: E402
from buecher import Fehlerbuch, Kostenbuch, Quarantaene, Veroeffentlichungsbuch, maskiere, sha256  # noqa: E402
from plan_schema import PlanFehler, lade_metadaten, lade_plan, stufe  # noqa: E402
import schnitt  # noqa: E402
import upload  # noqa: E402

HIER = Path(__file__).resolve().parent
KANAL = Path(os.environ.get("GK_INHALT", HIER.parent))  # Inhalte (Branch "inhalt" im Cloud-Worker)
KONF = json.loads((HIER / "konfig.json").read_text(encoding="utf-8"))


class Gesperrt(Exception):
    pass


def arbeitsordner() -> Path:
    return Path(os.environ.get("GK_ARBEIT", HIER.parent.parent / "Privat" / "Geschichtskanal"))


def buecher():
    a, b = arbeitsordner(), KONF["budget"]
    return (Kostenbuch(a / "kostenbuch.jsonl", b["limit_short_usd"], b["limit_monat_usd"]),
            Veroeffentlichungsbuch(a / "veroeffentlicht.jsonl"), Fehlerbuch(a / "fehler.jsonl"),
            Quarantaene(a / "quarantaene.jsonl"))


def pause_pruefen() -> None:
    if os.environ.get("GK_PAUSE", "").lower() == "ja":
        raise Gesperrt("Not-Aus aktiv (GK_PAUSE=ja)")


def plan_pfad(sid: str) -> Path:
    """Genau ein Thema pro Nummer. Fassungen: NNN_slug_plan.json, NNN_slug_plan_v2.json … (CA-15)."""
    kandidaten = []
    for p in (KANAL / "Shorts").glob(f"{sid}_*.json"):
        m = re.fullmatch(rf"{sid}_([A-Za-z0-9-]{{1,60}})_plan(?:_v(\d{{1,3}}))?\.json", p.name)
        if m:
            kandidaten.append((m.group(1), int(m.group(2) or 1), p))
    if not kandidaten:
        raise Gesperrt(f"kein Plan Shorts/{sid}_…_plan.json")
    if len({k[0] for k in kandidaten}) > 1:
        raise Gesperrt(f"{sid}: mehrere Themen mit derselben Nummer")
    return max(kandidaten, key=lambda k: k[1])[2]


def meta_pfad(sid: str) -> Path:
    return KANAL / "Kanal" / f"{sid}.json"


def pruef_freigabe(sid: str, plan: Path) -> None:
    """Nur die Kopfzeilen zählen, nicht zitierter Text weiter unten (CA-13)."""
    berichte = []
    for p in (KANAL / "Pruefberichte").glob(f"{sid}_v*.md"):
        m = re.fullmatch(rf"{sid}_v(\d{{1,3}})\.md", p.name)
        if m:
            berichte.append((int(m.group(1)), p))
    if not berichte:
        raise Gesperrt(f"{sid}: kein Prüfbericht")
    plan_sha = sha256(plan)
    meta = meta_pfad(sid)
    meta_sha = sha256(meta) if meta.exists() else "fehlt"
    for _, p in berichte:
        kopf = p.read_text(encoding="utf-8").splitlines()[:3]
        if len(kopf) >= 2 and kopf[1].strip() == f"SHA-256: {plan_sha}" and kopf[0].strip() == "Ergebnis: verworfen":
            raise Gesperrt(f"{sid}: dieser Plan wurde verworfen")
    kopf = (max(berichte)[1].read_text(encoding="utf-8").splitlines() + ["", "", ""])[:3]
    if kopf[0].strip() != "Ergebnis: freigegeben":
        raise Gesperrt(f"{sid}: neuester Prüfbericht gibt nicht frei")
    if kopf[1].strip() != f"SHA-256: {plan_sha}":
        raise Gesperrt(f"{sid}: Plan wurde nach der Prüfung geändert (Hash passt nicht)")
    if kopf[2].strip() != f"Metadaten-SHA-256: {meta_sha}":
        raise Gesperrt(f"{sid}: Metadaten fehlen oder wurden nach der Prüfung geändert")


def schaetze_kosten(plan: dict) -> float:
    v, b, s = KONF["video"], KONF["bild"], KONF["stimme"]
    zeichen = sum(len(e["text"]) for e in plan["einstellungen"])
    bilder = len(plan["einstellungen"]) * b["preis_usd"]
    videos = sum(v["clip_s"] * v["preis_usd_pro_s"] * v.get("versuche", 2) for e in plan["einstellungen"]
                 if e.get("art", "video") == "video")  # Höchstfall: jeder Clip zweimal
    return round(bilder + videos + zeichen / 1000 * s["preis_usd_pro_1000_zeichen"], 2)  # Höchstfall: 10-s-Clips


def musik_pfad(plan: dict, probe: bool = False) -> Path | None:
    name = plan.get("musik")
    if not name:
        return None
    ordner = (HIER / KONF["musik"]["ordner"]).resolve()
    p = (ordner / name).resolve()
    if not p.is_relative_to(ordner):
        raise PlanFehler(f"Musik {name!r} liegt außerhalb der Bibliothek")
    if not p.is_file():
        if probe:
            return None  # im Probelauf darf die Musik noch fehlen
        raise PlanFehler(f"Musik {name!r} nicht in der Bibliothek")
    return p


def ffmpeg_ausfuehren(befehle: list[list[str]], probe: bool) -> None:
    for b in befehle:
        if b[0] == "#schreibe":
            Path(b[1]).write_text(b[2], encoding="utf-8")
        elif not probe:
            subprocess.run(b, check=True, capture_output=True, timeout=900)


VIDEO_ZUSATZ = "Vertical 9:16 full-frame shot, no letterbox, no black bars, no text"


def balken_aus_log(log: str, breite: int, hoehe: int) -> list[str]:
    """Wertet die letzte cropdetect-Zeile aus. Inhalt deutlich kleiner als das Bild = schwarze Balken."""
    treffer = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", log)
    if not treffer:
        return []
    w, h = int(treffer[-1][0]), int(treffer[-1][1])
    f = []
    if h < 0.9 * hoehe:
        f.append(f"schwarze Balken oben/unten (Inhalt {w}x{h} von {breite}x{hoehe})")
    if w < 0.9 * breite:
        f.append(f"schwarze Balken links/rechts (Inhalt {w}x{h} von {breite}x{hoehe})")
    return f


def clip_pruefen(clip: Path) -> list[str]:
    """Jeder KI-Clip muss Hochformat sein und darf keine eingebrannten Balken haben."""
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                      "stream=width,height", "-of", "json", str(clip)],
                                     capture_output=True, check=True).stdout)
    s = info["streams"][0]
    b, h = int(s["width"]), int(s["height"])
    if b >= h:
        return [f"Querformat {b}x{h}"]
    log = subprocess.run(["ffmpeg", "-i", str(clip), "-vf", "cropdetect=24:2:0", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return balken_aus_log(log, b, h)


def kontaktbogen(video: Path, zeiten: list[tuple[float, float]], ziel: Path) -> None:
    """Ein Bild mit der Mitte jeder Einstellung, zur Sichtprüfung durch Chef-Agent und Nutzer."""
    ordner = ziel.parent / "kontakt"
    ordner.mkdir(exist_ok=True)
    for n, (a, z) in enumerate(zeiten, 1):
        subprocess.run(["ffmpeg", "-y", "-ss", f"{(a + z) / 2:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=360:640", str(ordner / f"f_{n:02d}.jpg")], capture_output=True, check=True)
    spalten = min(len(zeiten), 5)
    zeilen = -(-len(zeiten) // spalten)
    subprocess.run(["ffmpeg", "-y", "-framerate", "1", "-i", str(ordner / "f_%02d.jpg"), "-vf",
                    f"tile={spalten}x{zeilen}:padding=6:color=white", "-frames:v", "1", str(ziel)],
                   capture_output=True, check=True)


def qualitaet(video: Path, max_s: float | None = None) -> list[str]:
    f = []
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
                                      "-show_streams", str(video)], capture_output=True, check=True).stdout)
    dauer = float(info["format"]["duration"])
    if not KONF["laenge_s"]["min"] <= dauer <= (max_s or KONF["laenge_s"]["max_ausnahme"]):
        f.append(f"Länge {dauer:.1f} s")
    vs = [s for s in info["streams"] if s["codec_type"] == "video"]
    if not vs or (vs[0]["width"], vs[0]["height"]) != (KONF["format"]["breite"], KONF["format"]["hoehe"]):
        f.append("Auflösung nicht 1080x1920")
    if not any(s["codec_type"] == "audio" for s in info["streams"]):
        f.append("keine Tonspur")
    log = subprocess.run(["ffmpeg", "-i", str(video), "-vf", "blackdetect=d=1.5:pix_th=0.05",
                          "-af", "silencedetect=n=-45dB:d=1.5", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    f += balken_aus_log(subprocess.run(["ffmpeg", "-i", str(video), "-vf", "cropdetect=24:2:0", "-f", "null", "-"],
                                       capture_output=True, text=True).stderr,
                        KONF["format"]["breite"], KONF["format"]["hoehe"])
    if "black_start" in log:
        f.append("schwarzes Bild über 1,5 s")
    if "silence_start" in log:
        f.append("Stille über 1,5 s")
    return f


def vorpruefung(sid: str, plan: dict, kosten: Kostenbuch, buch: Veroeffentlichungsbuch, probe: bool,
                konto: str | None = None, test: bool = False) -> None:
    """Alles Kostenlose vor der ersten Zahlung (CA-15)."""
    lade_metadaten(meta_pfad(sid))
    musik_pfad(plan, probe)
    rest_monat = KONF["budget"]["limit_monat_usd"] - kosten.summe(monat=datetime.now(timezone.utc).strftime("%Y-%m"))
    rest_short = KONF["budget"]["limit_short_usd"] - kosten.summe(short=konto or sid)
    if schaetze_kosten(plan) > min(rest_monat, rest_short):
        raise Gesperrt(f"{sid}: Budget reicht nicht (Schätzung {schaetze_kosten(plan)} USD)")
    if not test and all(buch.heute(p) >= KONF["max_uploads_pro_tag"] for p, k in KONF["plattformen"].items() if k.get("aktiv")):
        raise Gesperrt("Tageslimit auf allen Plattformen erreicht")
    # Trockenlauf von Schnitt und Untertiteln mit geschätzten Zeiten
    probe_woerter = ElevenLabs(probe=True).sprechen(" ".join(e["text"] for e in plan["einstellungen"]), "", "",
                                                     arbeitsordner() / "trocken" / "s.mp3")
    zeiten = schnitt.zeiten_je_einstellung(plan, probe_woerter)
    schnitt.ass_untertitel(probe_woerter, KONF, set(plan.get("betonte_woerter", [])))
    schnitt.befehle(plan, zeiten, [Path("x")] * len(zeiten), Path("s"), None, Path("a"), Path("z"), KONF)


def produziere(sid: str, probe: bool, test: bool = False, test_modell: str | None = None) -> Path:
    """test=True: echter Lauf mit Kosten, aber ohne Prüferfreigabe und NIE hochladbar
    (eigener Ordner test_NNN, keine fertig.json, eigenes Kostenkonto test-NNN)."""
    pause_pruefen()
    kosten, buch, fehler, quar = buecher()
    pp = plan_pfad(sid)
    if not probe and not test:
        pruef_freigabe(sid, pp)
    plan = lade_plan(pp)
    video_konf = dict(KONF["video"])
    if test and test_modell:
        if test_modell not in KONF.get("test_modelle", {}):
            raise Gesperrt(f"unbekanntes Testmodell {test_modell}")
        video_konf.update(KONF["test_modelle"][test_modell])
    konto = f"test-{sid}-{test_modell or 'standard'}" if test else sid
    arbeit = arbeitsordner() / "medien" / (f"test_{sid}_{test_modell or 'standard'}" if test else sid)
    arbeit.mkdir(parents=True, exist_ok=True)
    ziel = arbeit / f"{sid}_final.mp4"
    fertig = arbeit / "fertig.json"
    if not probe and not test and fertig.exists() and ziel.exists():
        f = json.loads(fertig.read_text(encoding="utf-8"))
        if f.get("plan_sha256") == sha256(pp) and f.get("video_sha256") == sha256(ziel):
            return ziel  # schon produziert: nicht erneut bezahlen (CA-15)
    vorpruefung(sid, plan, kosten, buch, probe or test, konto, test)
    bezahlt = False
    try:
        st, fal = KONF["stimme"], Fal(probe)
        text = " ".join(e["text"] for e in plan["einstellungen"])
        if not probe:
            kosten.buchen(konto, "stimme", len(text) / 1000 * st["preis_usd_pro_1000_zeichen"], "elevenlabs")
            bezahlt = True
        woerter = ElevenLabs(probe).sprechen(text, st["voice_id"], st["modell"], arbeit / "stimme.mp3")
        zeiten = schnitt.zeiten_je_einstellung(plan, woerter)
        clips = []
        for n, (e, (a, z)) in enumerate(zip(plan["einstellungen"], zeiten), 1):
            prompt = f"{e['bild_prompt']}. {KONF['bild']['stil']}"
            if not probe:
                kosten.buchen(konto, f"bild_{n}", KONF["bild"]["preis_usd"], "fal")
            bild, bild_url = fal.bild(KONF["bild"]["modell"], prompt, arbeit / f"bild_{n:02d}.png",
                                      KONF["bild"].get("aufloesung", "2K"))
            if e.get("art", "video") == "video":
                d = video_konf["clip_s"]  # immer 5 s; längere Sätze halten das letzte Bild (Kosten)
                clip = None
                for versuch in range(1, max(1, video_konf.get("versuche", 2)) + 1):
                    if not probe:
                        kosten.buchen(konto, f"video_{n}_v{versuch}", d * video_konf["preis_usd_pro_s"], "fal")
                    kandidat = fal.video(video_konf["modell"], bild_url,
                                         f"{e['bewegung'].replace('_', ' ')}. {e.get('video_prompt', '')}. {VIDEO_ZUSATZ}",
                                         d, arbeit / f"clip_{n:02d}_v{versuch}.mp4")
                    probleme = [] if probe else clip_pruefen(kandidat)
                    if not probleme:
                        clip = kandidat
                        break
                    fehler.eintragen(sid, f"clip_{n}_v{versuch}", ", ".join(probleme))
                if clip is None:  # lieber ein sauberes Standbild mit Kamerafahrt als ein falsches Format
                    e["art"] = "standbild"
                    fehler.eintragen(sid, f"clip_{n}", "Ersatz durch Standbild mit Kamerafahrt")
                    clips.append(bild)
                else:
                    clips.append(clip)
            else:
                clips.append(bild)
        ass = arbeit / "untertitel.ass"
        ass.write_text(schnitt.ass_untertitel(woerter, KONF, set(plan.get("betonte_woerter", []))), encoding="utf-8")
        ffmpeg_ausfuehren(schnitt.befehle(plan, zeiten, clips, arbeit / "stimme.mp3", musik_pfad(plan, probe or test), ass,
                                          ziel, KONF), probe)
        if not probe:
            kontaktbogen(ziel, zeiten, arbeit / "kontaktbogen.jpg")
            probleme = qualitaet(ziel, KONF["laenge_s"]["max_ausnahme" if plan.get("laenge") == "lang" else "max_normal"])
            if probleme:
                raise Gesperrt(f"{sid}: Qualitätsprüfung: {', '.join(probleme)}")
        if test:
            return ziel  # Testvideo: bewusst keine fertig.json, daher nie hochladbar
        fertig.write_text(json.dumps({"plan_sha256": sha256(pp), "stufe": stufe(plan),
                                      "video_sha256": sha256(ziel) if ziel.exists() else "probe"}), encoding="utf-8")
        return ziel
    except Exception as ex:
        fehler.eintragen(sid, "produktion", f"{type(ex).__name__}: {ex}")
        if bezahlt and not test:
            quar.sperren(sid, f"Produktion nach Zahlung gescheitert: {ex}")
        raise


def hochladen(sid: str, probe: bool) -> list[dict]:
    pause_pruefen()
    _, buch, fehler, _ = buecher()
    pp = plan_pfad(sid)
    arbeit = arbeitsordner() / "medien" / sid
    video = arbeit / f"{sid}_final.mp4"
    meta = lade_metadaten(meta_pfad(sid))
    if not probe:
        pruef_freigabe(sid, pp)
        f = json.loads((arbeit / "fertig.json").read_text(encoding="utf-8"))
        if f.get("plan_sha256") != sha256(pp) or f.get("video_sha256") != sha256(video):
            raise Gesperrt(f"{sid}: Video passt nicht zum geprüften Plan")
        if os.environ.get("GK_UPLOAD_ERLAUBT") != "ja":
            raise Gesperrt("Upload nicht freigegeben (GK_UPLOAD_ERLAUBT fehlt)")
        umgebung = os.environ.get("GK_UMGEBUNG")
        if umgebung not in ("auto", "pruefung") or (f["stufe"] == "pruefung" and umgebung != "pruefung"):
            raise Gesperrt(f"{sid}: Stufe {f['stufe']} braucht die Umgebung mit Pflicht-Reviewer")
    vsha = sha256(video) if video.exists() else "probe"
    privat_test = buch.erfolgreich() < KONF.get("erste_uploads_privat", 0)
    ergebnisse = []
    for name, konf in KONF["plattformen"].items():
        if not konf.get("aktiv"):
            continue
        if buch.bereits(sid, name):
            ergebnisse.append({"plattform": name, "status": "übersprungen (schon online oder begonnen)"})
            continue
        if buch.heute(name) >= KONF["max_uploads_pro_tag"]:
            ergebnisse.append({"plattform": name, "status": "übersprungen (Tageslimit)"})
            continue
        if probe:
            ergebnisse.append({"plattform": name, "status": "probe", "titel": meta["youtube"]["titel"]})
            continue
        if privat_test and name != "youtube":
            ergebnisse.append({"plattform": name, "status": "übersprungen (Testphase nur YouTube privat)"})
            continue
        k = dict(konf, privacy="private") if privat_test else konf
        buch.eintragen(sid, name, vsha, "begonnen")
        try:
            r = upload.PLATTFORMEN[name](video, meta, k)
            buch.eintragen(sid, name, vsha, "ok", r["id"], r.get("hinweis", ""))
            ergebnisse.append({"plattform": name, "status": "ok", **r})
        except Exception as ex:  # eine Plattform blockiert die anderen nicht
            buch.eintragen(sid, name, vsha, "fehler", info=str(ex))
            fehler.eintragen(sid, f"upload_{name}", str(ex))
            ergebnisse.append({"plattform": name, "status": "fehler", "info": maskiere(str(ex))[:200]})
    zusammenfassung(sid, meta, ergebnisse)
    return ergebnisse


def zusammenfassung(sid: str, meta: dict, ergebnisse: list[dict]) -> None:
    """Für den Reviewer und das Protokoll in GitHub (CA-18)."""
    ziel = os.environ.get("GITHUB_STEP_SUMMARY")
    if not ziel:
        return
    kosten = buecher()[0].summe(short=sid)
    zeilen = [f"## Short {sid}", f"**Titel:** {meta['youtube']['titel']}", "",
              "```", meta["youtube"]["beschreibung"], "```", f"Kosten bisher: {kosten:.2f} USD", ""]
    zeilen += [f"- {e['plattform']}: {e['status']}" for e in ergebnisse]
    with open(ziel, "a", encoding="utf-8") as f:
        f.write("\n".join(zeilen) + "\n")


def naechster(probe: bool) -> str | None:
    _, buch, _, quar = buecher()
    gesehen = set()
    for pp in sorted((KANAL / "Shorts").glob("[0-9][0-9][0-9]_*_plan*.json")):
        sid = pp.name[:3]
        if sid in gesehen:
            continue
        gesehen.add(sid)
        if quar.gesperrt(sid):
            continue
        if all(buch.bereits(sid, p) for p, k in KONF["plattformen"].items() if k.get("aktiv")):
            continue
        try:
            plan = plan_pfad(sid)
            if not probe:
                pruef_freigabe(sid, plan)
            lade_plan(plan)
        except (Gesperrt, PlanFehler):
            continue
        return sid
    return None


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="lauf")
    ap.add_argument("befehl", choices=["waehle", "produziere", "test", "hochladen", "naechster"])
    ap.add_argument("short", nargs="?")
    ap.add_argument("--probe", action="store_true", help="nichts aufrufen, nichts bezahlen, nichts hochladen")
    ap.add_argument("--modell", help="nur für test: Schlüssel aus konfig.json test_modelle")
    a = ap.parse_args(argv)
    if a.short is not None and not re.fullmatch(r"\d{3}", a.short):
        print("Short-Nummer muss dreistellig sein")
        return 2
    if not a.probe and a.befehl in ("produziere", "test") and shutil.which("ffmpeg") is None:
        print("FFmpeg fehlt")
        return 2
    try:
        if a.befehl == "waehle":
            pause_pruefen()
            sid = naechster(a.probe)
            st = stufe(lade_plan(plan_pfad(sid))) if sid else ""
            print(f"short={sid or ''}")
            print(f"umgebung={'veroeffentlichung-pruefung' if st == 'pruefung' else 'veroeffentlichung-auto'}")
        elif a.befehl == "produziere":
            print(produziere(a.short, a.probe))
        elif a.befehl == "test":
            print(produziere(a.short, a.probe, test=True, test_modell=a.modell))
        elif a.befehl == "hochladen":
            print(json.dumps(hochladen(a.short, a.probe), ensure_ascii=False, indent=2))
        else:
            sid = naechster(a.probe)
            if not sid:
                print("kein freigegebener Short offen")
                return 0
            produziere(sid, a.probe)
            print(json.dumps(hochladen(sid, a.probe), ensure_ascii=False, indent=2))
    except (Gesperrt, PlanFehler) as g:
        print(f"GESPERRT: {maskiere(str(g))}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
