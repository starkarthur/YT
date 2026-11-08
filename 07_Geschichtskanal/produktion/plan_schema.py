"""Produktionsplan (Shorts/NNN_slug_plan[_vN].json, geschrieben vom geschichte-autor) und
Metadaten (Kanal/NNN.json, geschrieben vom geschichte-kanal) streng prüfen.

Grundsatz (CA-14, CA-19): Erlaubt ist nur, was ausdrücklich erlaubt ist. Alle Texte werden NFKC-normalisiert,
Steuerzeichen und Klammern sind verboten, Längen und Typen sind fest.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from pathlib import Path

BEWEGUNG = {"langsamer_zoom_rein", "langsamer_zoom_raus", "schwenk_links", "schwenk_rechts",
            "kamerafahrt_vor", "statisch", "handkamera", "aufsicht_drohne"}
EFFEKT = {"keiner", "punch_zoom", "wackler", "blitz_weiss", "zeitlupe"}
ART = {"video", "standbild"}
REIHEN = {"cons", "accidents", "really_happened", "time_is_weird", "natures_fury"}
# Reihen, die ohne menschliche Sichtung laufen dürfen (CA-21). Alles andere: Pflicht-Reviewer.
REIHEN_AUTO = {"accidents", "time_is_weird", "cons", "really_happened"}
VERBOTEN = re.compile(
    r"\b(swastika|hakenkreuz|ss|nazi|hitler|gore|blood|bloody|corpse|corpses|dead body|dead bodies|"
    r"victim|victims|injured|wounded|nude|naked|massacre|genocide|execution|beheading|suicide)\b", re.I)
STEUER = re.compile(r"[\x00-\x1f\x7f  <>\[\]{}\\]")
MUSIK = re.compile(r"[A-Za-z0-9_-]{1,60}\.(mp3|wav|m4a)")
PERSONEN_VERDACHT = re.compile(r"\b[A-Z][a-z]+(?:\s+(?:de|von|van|da|of|the)?\s*[A-Z][a-z]+)+\b")
ORTE_ERLAUBT = {"Eiffel Tower", "Paris", "Trocadero", "New England", "Lake Geneva", "Great Pyramid"}

MAX_TEXT, MAX_GESAMT, MAX_PROMPT = 220, 1100, 600


class PlanFehler(Exception):
    pass


def norm(s):
    return unicodedata.normalize("NFKC", s) if isinstance(s, str) else s


def _str(wert, feld: str, maxlen: int, f: list[str], pflicht: bool = True) -> str:
    if wert is None and not pflicht:
        return ""
    if not isinstance(wert, str) or (pflicht and not wert.strip()):
        f.append(f"{feld}: Text erwartet")
        return ""
    w = norm(wert)
    if len(w) > maxlen:
        f.append(f"{feld}: länger als {maxlen} Zeichen")
    if STEUER.search(w):
        f.append(f"{feld}: Steuerzeichen oder Klammern")
    if VERBOTEN.search(w):
        f.append(f"{feld}: verbotener Begriff")
    return w


def pruefe_plan(plan: dict, sid_aus_datei: str | None = None) -> list[str]:
    f: list[str] = []
    if not isinstance(plan, dict):
        return ["Plan ist kein Objekt"]
    if not isinstance(plan.get("id"), str) or not re.fullmatch(r"\d{3}", plan["id"]):
        f.append("id muss dreistellig sein")
    elif sid_aus_datei and plan["id"] != sid_aus_datei:
        f.append("id passt nicht zum Dateinamen")
    _str(plan.get("titel"), "titel", 120, f)
    if plan.get("reihe") not in REIHEN:
        f.append(f"reihe muss eine von {sorted(REIHEN)} sein")
    jahr = plan.get("jahr")
    if not isinstance(jahr, int) or isinstance(jahr, bool) or not -70_000_000 <= jahr <= date.today().year:
        f.append("jahr (Ganzzahl, v. Chr. negativ) fehlt oder ungültig")
    personen = plan.get("personen", [])
    if not isinstance(personen, list) or not all(isinstance(p, str) for p in personen):
        f.append("personen muss eine Liste von Namen sein")
    m = plan.get("musik")
    if m is not None and (not isinstance(m, str) or not MUSIK.fullmatch(m)):
        f.append("musik: nur Dateiname wie spannung_1.mp3")
    bw = plan.get("betonte_woerter", [])
    if not isinstance(bw, list) or len(bw) > 20 or not all(
            isinstance(w, str) and re.fullmatch(r"[A-Za-z'-]{1,30}", w) for w in bw):
        f.append("betonte_woerter: Liste einzelner Wörter")
    lang = plan.get("laenge", "kurz")
    if lang not in ("kurz", "lang"):
        f.append("laenge muss 'kurz' (bis 20 s) oder 'lang' (bis 30 s) sein")
    if lang == "lang" and not (isinstance(plan.get("lang_begruendung"), str) and len(plan["lang_begruendung"].strip()) >= 20):
        f.append("laenge 'lang' braucht eine lang_begruendung (mind. 20 Zeichen)")
    e = plan.get("einstellungen")
    if not isinstance(e, list) or not 3 <= len(e) <= (8 if lang == "lang" else 6):
        return f + ["3 bis 6 Einstellungen (lang: bis 8) erwartet"]
    gesamt, woerter, standbilder = 0, 0, 0
    for i, s in enumerate(e, 1):
        if not isinstance(s, dict):
            f.append(f"#{i}: Objekt erwartet")
            continue
        t = _str(s.get("text"), f"#{i} text", MAX_TEXT, f)
        if any(len(w) > 25 for w in t.split()):
            f.append(f"#{i} text: Wort länger als 25 Zeichen")
        if len(t.split()) > 15:
            f.append(f"#{i} text: höchstens 15 Wörter pro Einstellung (ein 5-s-Clip)")
        gesamt += len(t)
        woerter += len(t.split())
        _str(s.get("bild_prompt"), f"#{i} bild_prompt", MAX_PROMPT, f)
        _str(s.get("video_prompt"), f"#{i} video_prompt", 300, f, pflicht=False)
        if s.get("bewegung") not in BEWEGUNG:
            f.append(f"#{i}: bewegung unbekannt")
        if s.get("effekt", "keiner") not in EFFEKT:
            f.append(f"#{i}: effekt unbekannt")
        if s.get("art", "video") not in ART:
            f.append(f"#{i}: art unbekannt")
        standbilder += s.get("art") == "standbild"
    if gesamt > MAX_GESAMT:
        f.append(f"Text zu lang ({gesamt} Zeichen)")
    grenze = (30, 85) if plan.get("laenge", "kurz") == "lang" else (30, 58)
    if not grenze[0] <= woerter <= grenze[1]:
        f.append(f"{woerter} Wörter, erwartet {grenze[0]}-{grenze[1]} (ca. 2,8 Wörter pro Sekunde)")
    if standbilder > 3:
        f.append("höchstens 3 Standbilder")
    return f


def stufe(plan: dict) -> str:
    """'auto' nur für unkritische Shorts. Die Pipeline entscheidet, nicht der Autor (CA-21)."""
    if plan["reihe"] not in REIHEN_AUTO or plan.get("personen"):
        return "pruefung"
    if plan["jahr"] >= date.today().year - 10:
        return "pruefung"
    prompts = " ".join(s.get("bild_prompt", "") + " " + s.get("video_prompt", "") for s in plan["einstellungen"])
    namen = set(PERSONEN_VERDACHT.findall(prompts)) - ORTE_ERLAUBT
    return "pruefung" if namen else "auto"


def lade_plan(pfad: Path) -> dict:
    try:
        plan = json.loads(pfad.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as ex:
        raise PlanFehler(f"kein gültiges JSON: {ex}") from None
    fehler = pruefe_plan(plan, pfad.name[:3])
    if fehler:
        raise PlanFehler("; ".join(fehler))
    for s in plan["einstellungen"]:
        for k in ("text", "bild_prompt", "video_prompt"):
            if k in s:
                s[k] = norm(s[k])
    return plan


# --- Metadaten ---------------------------------------------------------
LINK = re.compile(r"https?|www|\w\.[a-z]{2,}\b|\bdot\s*(com|net|org|io|app|co)\b|@|\[|\]|<|>", re.I)
KENNZEICHNUNG = "Scenes are dramatized reenactments created with AI. Narration voice is AI-generated."


def lade_metadaten(pfad: Path) -> dict:
    """Prüft die Texte und gibt sie MIT fest angehängter KI-Kennzeichnung zurück."""
    try:
        m = json.loads(pfad.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as ex:
        raise PlanFehler(f"Metadaten kein gültiges JSON: {ex}") from None
    f: list[str] = []
    yt, tt, ig = m.get("youtube", {}), m.get("tiktok", {}), m.get("instagram", {})
    felder = {"youtube.titel": (yt.get("titel"), 90), "youtube.beschreibung": (yt.get("beschreibung"), 4000),
              "tiktok.text": (tt.get("text"), 2000), "instagram.text": (ig.get("text"), 2000)}
    for name, (wert, maxlen) in felder.items():
        if not isinstance(wert, str) or not wert.strip():
            f.append(f"{name} fehlt")
            continue
        w = norm(wert)
        if len(w) > maxlen:
            f.append(f"{name} zu lang")
        if re.search(r"[\x00-\x09\x0b-\x1f\x7f  ]", w):
            f.append(f"{name}: Steuerzeichen")
        if LINK.search(w):
            f.append(f"{name}: Links, @-Namen oder Klammern sind nicht erlaubt")
        if VERBOTEN.search(w):
            f.append(f"{name}: verbotener Begriff")
    tags = yt.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 15 or not all(
            isinstance(t, str) and re.fullmatch(r"[A-Za-z0-9 '-]{1,40}", t) for t in tags):
        f.append("youtube.tags: bis 15 einfache Begriffe")
    if f:
        raise PlanFehler("; ".join(f))
    beschreibung = norm(yt["beschreibung"]).replace(KENNZEICHNUNG, "").strip()
    return {"youtube": {"titel": norm(yt["titel"]), "tags": tags,
                        "beschreibung": f"{beschreibung}\n\n{KENNZEICHNUNG}"},
            "tiktok": {"text": norm(tt["text"]).strip() + " (AI-dramatized)"},
            "instagram": {"text": f"{norm(ig['text']).strip()}\n\n{KENNZEICHNUNG}"}}
