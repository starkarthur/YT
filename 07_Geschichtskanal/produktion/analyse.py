"""Feedback-Schleife: holt YouTube-Zahlen der eigenen Shorts und schreibt sie für den InfluencerAgent auf.

Nur lesend. Zugangsdaten als Umgebungsvariablen (eigener Lese-Client, getrennt vom Upload):
  YT_ANALYSE_CLIENT_ID, YT_ANALYSE_CLIENT_SECRET, YT_ANALYSE_REFRESH_TOKEN
  Scopes: youtube.readonly, yt-analytics.readonly

Aufruf:  python analyse.py            (schreibt nach $GK_ARBEIT/analyse/)
         python analyse.py --probe    (ohne Netz, mit Beispieldaten)
Ausgabe: analyse/youtube_<datum>.json (alle Zahlen) und analyse/<NNN>_youtube.md (lesbar, je Short),
         beim ersten Lauf ab 24 h Alter zusätzlich analyse/<NNN>_48h.md (fester Schnappschuss).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from anbieter import AnbieterFehler, http_json
from upload import _env, _form

HIER = Path(__file__).resolve().parent
KANAL = Path(os.environ.get("GK_INHALT", HIER.parent))
ARBEIT = Path(os.environ.get("GK_ARBEIT", HIER / "arbeit"))
DATA = "https://www.googleapis.com/youtube/v3"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
KERN = ["views", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage",
        "likes", "comments", "shares", "subscribersGained"]
RETENTION_PUNKTE = (0.05, 0.25, 0.5, 0.75, 0.95)


def token() -> str:
    return _form("https://oauth2.googleapis.com/token", {
        "client_id": _env("YT_ANALYSE_CLIENT_ID"), "client_secret": _env("YT_ANALYSE_CLIENT_SECRET"),
        "refresh_token": _env("YT_ANALYSE_REFRESH_TOKEN"), "grant_type": "refresh_token"})["access_token"]


def _get(url: str, params: dict, tok: str) -> dict:
    return http_json("GET", f"{url}?{urllib.parse.urlencode(params)}", {"Authorization": f"Bearer {tok}"})


def uploads(tok: str, maximal: int = 50) -> list[dict]:
    """Eigene Videos (neueste zuerst) mit Titel, Datum, Dauer und öffentlichen Zählern."""
    kanal = _get(f"{DATA}/channels", {"part": "contentDetails", "mine": "true"}, tok)["items"][0]
    liste = kanal["contentDetails"]["relatedPlaylists"]["uploads"]
    items = _get(f"{DATA}/playlistItems", {"part": "contentDetails", "playlistId": liste,
                                            "maxResults": min(maximal, 50)}, tok).get("items", [])
    ids = [i["contentDetails"]["videoId"] for i in items]
    if not ids:
        return []
    v = _get(f"{DATA}/videos", {"part": "snippet,statistics,contentDetails,status", "id": ",".join(ids)}, tok)
    return [{"id": x["id"], "titel": x["snippet"]["title"], "veroeffentlicht": x["snippet"]["publishedAt"],
             "dauer": x["contentDetails"]["duration"], "status": x["status"]["privacyStatus"],
             "zaehler": {k: int(w) for k, w in x.get("statistics", {}).items() if str(w).isdigit()}}
            for x in v.get("items", [])]


def kennzahlen(tok: str, vid: str, start: str, ende: str) -> dict:
    """Analytics-Kernzahlen. Fällt ein Wert weg (API lehnt ab), werden die übrigen trotzdem geholt."""
    metriken = list(KERN)
    while metriken:
        try:
            r = _get(ANALYTICS, {"ids": "channel==MINE", "startDate": start, "endDate": ende,
                                 "metrics": ",".join(metriken), "filters": f"video=={vid}"}, tok)
            zeile = (r.get("rows") or [[0] * len(metriken)])[0]
            return dict(zip(metriken, zeile))
        except AnbieterFehler as e:
            if "HTTP 400" not in str(e) or len(metriken) == 1:
                return {"fehler": str(e)[:200]}
            metriken.pop()  # zuletzt genannte Metrik weglassen und erneut versuchen
    return {}


def bindung(tok: str, vid: str, start: str, ende: str) -> list[list[float]]:
    """Zuschauerbindung: Anteil der Zuschauer an Punkten des Videos (0..1 der Länge)."""
    try:
        r = _get(ANALYTICS, {"ids": "channel==MINE", "startDate": start, "endDate": ende,
                             "metrics": "audienceWatchRatio,relativeRetentionPerformance",
                             "dimensions": "elapsedVideoTimeRatio", "filters": f"video=={vid}"}, tok)
        return r.get("rows") or []
    except AnbieterFehler:
        return []


def an_punkten(kurve: list[list[float]]) -> dict:
    if not kurve:
        return {}
    return {f"{int(p * 100)}%": round(min(kurve, key=lambda z: abs(z[0] - p))[1], 3) for p in RETENTION_PUNKTE}


def short_nummern() -> dict:
    """YouTube-Titel → Short-Nummer aus Kanal/NNN.json."""
    m = {}
    for p in sorted((KANAL / "Kanal").glob("[0-9][0-9][0-9].json")):
        try:
            m[json.loads(p.read_text(encoding="utf-8"))["youtube"]["titel"].strip()] = p.stem
        except (KeyError, ValueError):
            continue
    return m


def dauer_s(iso: str) -> int:
    m = re.fullmatch(r"PT(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0) if m else 0


def bewerten(z: dict) -> list[str]:
    """Kurze, regelbasierte Hinweise für den StoryAgent (keine Spekulation)."""
    h, k, r = [], z.get("kennzahlen", {}), z.get("bindung", {})
    pct = k.get("averageViewPercentage")
    if isinstance(pct, (int, float)):
        if pct >= 90:
            h.append(f"Sehr gute Wiedergabe ({pct:.0f} % der Länge im Schnitt). Aufbau beibehalten.")
        elif pct < 60:
            h.append(f"Schwache Wiedergabe ({pct:.0f} %). Hook in Sekunde 0–2 stärker machen, Video kürzer.")
    if r.get("25%") is not None and r["25%"] < 0.6:
        h.append(f"Früher Abbruch: bei 25 % schauen nur noch {r['25%']:.0%}. Erste Einstellung prüfen.")
    if r.get("95%") is not None and r["95%"] >= 0.8:
        h.append("Viele schauen bis zum Ende. Loop/Pointe funktioniert.")
    if z.get("dauer_s", 0) > 22:
        h.append(f"Video ist {z['dauer_s']} s lang (Ziel ≤ 20 s).")
    if not h:
        h.append("Noch zu wenig Daten für eine klare Aussage.")
    return h


def markdown(z: dict) -> str:
    k, r = z.get("kennzahlen", {}), z.get("bindung", {})
    zeilen = [f"# Short {z['short']} – YouTube-Zahlen", "",
              f"Titel: {z['titel']}", f"Video: https://youtube.com/shorts/{z['id']}",
              f"Stand: {z['stand']} · Alter: {z['alter_h']} h · Länge: {z['dauer_s']} s", "",
              "| Kennzahl | Wert |", "| --- | --- |"]
    zeilen += [f"| Aufrufe (öffentlich) | {z['zaehler'].get('viewCount', 0)} |"]
    zeilen += [f"| {n} | {w} |" for n, w in k.items()]
    if r:
        zeilen += ["", "Zuschauerbindung (Anteil, der an dieser Stelle noch schaut):", "",
                   "| Stelle | Anteil |", "| --- | --- |"] + [f"| {p} | {w} |" for p, w in r.items()]
    zeilen += ["", "## Hinweise für den StoryAgent", ""] + [f"- {x}" for x in z["hinweise"]]
    zeilen += ["", "Hinweis: Analytics-Werte kommen mit 1–2 Tagen Verzögerung; frühe Werte können 0 sein."]
    return "\n".join(zeilen) + "\n"


def lauf(probe: bool = False, jetzt: datetime | None = None) -> list[dict]:
    jetzt = jetzt or datetime.now(timezone.utc)
    ziel = ARBEIT / "analyse"
    ziel.mkdir(parents=True, exist_ok=True)
    namen = short_nummern()
    if probe:
        tok, videos = "", [{"id": "PROBE000001", "titel": next(iter(namen), "Probe"), "dauer": "PT21S",
                            "veroeffentlicht": (jetzt - timedelta(hours=30)).isoformat(), "status": "public",
                            "zaehler": {"viewCount": 120}}]
    else:
        tok = token()
        videos = uploads(tok)
    ergebnis = []
    for v in videos:
        sid = namen.get(v["titel"].strip())
        if not sid:
            continue
        veroeff = datetime.fromisoformat(v["veroeffentlicht"].replace("Z", "+00:00"))
        start, ende = veroeff.date().isoformat(), jetzt.date().isoformat()
        z = {"short": sid, "id": v["id"], "titel": v["titel"], "status": v["status"],
             "alter_h": int((jetzt - veroeff).total_seconds() // 3600), "dauer_s": dauer_s(v["dauer"]),
             "zaehler": v["zaehler"], "stand": jetzt.strftime("%Y-%m-%d %H:%M UTC")}
        if probe:
            z["kennzahlen"] = {"views": 118, "averageViewPercentage": 54.0, "averageViewDuration": 11}
            z["bindung"] = an_punkten([[0.05, 0.9], [0.25, 0.55], [0.5, 0.4], [0.75, 0.3], [0.95, 0.2]])
        else:
            z["kennzahlen"] = kennzahlen(tok, v["id"], start, ende)
            z["bindung"] = an_punkten(bindung(tok, v["id"], start, ende))
        z["hinweise"] = bewerten(z)
        text = markdown(z)
        (ziel / f"{sid}_youtube.md").write_text(text, encoding="utf-8")
        fest = ziel / f"{sid}_48h.md"
        if z["alter_h"] >= 24 and not fest.exists():
            fest.write_text(text, encoding="utf-8")
        ergebnis.append(z)
    (ziel / f"youtube_{jetzt.date().isoformat()}.json").write_text(
        json.dumps(ergebnis, ensure_ascii=False, indent=1), encoding="utf-8")
    return ergebnis


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    for z in lauf(probe="--probe" in sys.argv):
        print(f"{z['short']}: {z['zaehler'].get('viewCount', 0)} Aufrufe, {z['alter_h']} h – " + " ".join(z["hinweise"]))
