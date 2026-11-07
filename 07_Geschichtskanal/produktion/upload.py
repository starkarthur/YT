"""Uploads zu YouTube (Data API v3), TikTok (Content Posting API, Direct Post) und Instagram
(Graph API, Reels, resumable Upload). Nur Standardbibliothek.

Zugangsdaten nur als Umgebungsvariablen im Cloud-Worker:
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
  TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN
  IG_USER_ID, IG_ACCESS_TOKEN (langlebiges Token)

STAND: Die Abläufe folgen der öffentlichen Doku der Plattformen, sind aber noch NICHT gegen echte
Konten getestet. Erster echter Lauf nur nach Freigabe des Nutzers, zunächst als privat/Entwurf.
Plattformgrenzen: Ohne geprüftes API-Projekt (Google-Audit, TikTok-Audit) erzwingen YouTube und
TikTok privat. Das meldet der Upload, statt es zu verschweigen.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.parse
from pathlib import Path

from anbieter import AnbieterFehler, _http, http_json


def _env(n: str) -> str:
    v = os.environ.get(n)
    if not v:
        raise AnbieterFehler(f"Umgebungsvariable {n} fehlt")
    return v


def _form(url: str, felder: dict, kopf: dict | None = None) -> dict:
    daten = urllib.parse.urlencode(felder).encode()
    _, _, roh = _http("POST", url, {"Content-Type": "application/x-www-form-urlencoded", **(kopf or {})}, daten)
    return json.loads(roh)


# --- YouTube ------------------------------------------------------------
def youtube(video: Path, meta: dict, konf: dict) -> dict:
    tok = _form("https://oauth2.googleapis.com/token", {
        "client_id": _env("YT_CLIENT_ID"), "client_secret": _env("YT_CLIENT_SECRET"),
        "refresh_token": _env("YT_REFRESH_TOKEN"), "grant_type": "refresh_token"})["access_token"]
    y = meta["youtube"]
    body = {"snippet": {"title": y["titel"], "description": y["beschreibung"], "tags": y.get("tags", []),
                        "categoryId": konf["kategorie"], "defaultLanguage": "en", "defaultAudioLanguage": "en"},
            "status": {"privacyStatus": konf["privacy"], "selfDeclaredMadeForKids": konf["made_for_kids"],
                       "containsSyntheticMedia": konf["synthetic_media"], "embeddable": True}}
    groesse = video.stat().st_size
    _, kopf, _ = _http("POST",
                       "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                       {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
                        "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(groesse)},
                       json.dumps(body).encode())
    ort = kopf.get("Location") or kopf.get("location") or ""
    if not ort.startswith("https://www.googleapis.com/upload/youtube/"):
        raise AnbieterFehler("YouTube: unerwartete Upload-Adresse")
    _, _, roh = _http("PUT", ort, {"Authorization": f"Bearer {tok}", "Content-Type": "video/mp4"},
                      video.read_bytes(), zeit=900)
    r = json.loads(roh)
    status = r.get("status", {}).get("privacyStatus")
    hinweis = "" if status == konf["privacy"] else f"YouTube setzte '{status}' (API-Projekt noch nicht geprüft?)"
    return {"id": r["id"], "url": f"https://youtube.com/shorts/{r['id']}", "hinweis": hinweis}


# --- TikTok -------------------------------------------------------------
def tiktok(video: Path, meta: dict, konf: dict) -> dict:
    tok = _form("https://open.tiktokapis.com/v2/oauth/token/", {
        "client_key": _env("TIKTOK_CLIENT_KEY"), "client_secret": _env("TIKTOK_CLIENT_SECRET"),
        "grant_type": "refresh_token", "refresh_token": _env("TIKTOK_REFRESH_TOKEN")})["access_token"]
    kopf = {"Authorization": f"Bearer {tok}"}
    info = http_json("POST", "https://open.tiktokapis.com/v2/post/publish/creator_info/query/", kopf, {})["data"]
    optionen = info.get("privacy_level_options", [])
    privacy = "PUBLIC_TO_EVERYONE" if "PUBLIC_TO_EVERYONE" in optionen else "SELF_ONLY"
    groesse = video.stat().st_size
    chunk = min(groesse, 10_000_000)
    anzahl = max(1, groesse // chunk)
    init = http_json("POST", "https://open.tiktokapis.com/v2/post/publish/video/init/", kopf, {
        "post_info": {"title": meta["tiktok"]["text"], "privacy_level": privacy, "disable_duet": False,
                      "disable_comment": False, "disable_stitch": False, "is_aigc": konf["is_aigc"],
                      "brand_content_toggle": False, "brand_organic_toggle": False},
        "source_info": {"source": "FILE_UPLOAD", "video_size": groesse, "chunk_size": chunk,
                        "total_chunk_count": anzahl}})["data"]
    daten = video.read_bytes()
    for i in range(anzahl):
        a = i * chunk
        e = groesse if i == anzahl - 1 else a + chunk  # letzter Teil nimmt den Rest
        _http("PUT", init["upload_url"], {"Content-Type": "video/mp4", "Content-Length": str(e - a),
                                          "Content-Range": f"bytes {a}-{e - 1}/{groesse}"}, daten[a:e], zeit=600)
    for _ in range(60):
        s = http_json("POST", "https://open.tiktokapis.com/v2/post/publish/status/fetch/", kopf,
                      {"publish_id": init["publish_id"]})["data"]
        if s.get("status") == "PUBLISH_COMPLETE":
            break
        if s.get("status") == "FAILED":
            raise AnbieterFehler(f"TikTok: {s.get('fail_reason')}")
        time.sleep(10)
    else:
        raise AnbieterFehler("TikTok: Veröffentlichung nicht bestätigt (Status prüfen)")
    hinweis = "" if privacy == "PUBLIC_TO_EVERYONE" else "TikTok erlaubt nur privat (App noch nicht geprüft)"
    return {"id": init["publish_id"], "url": "", "hinweis": hinweis}


# --- Instagram Reels ----------------------------------------------------
def instagram(video: Path, meta: dict, konf: dict) -> dict:
    v, uid, tok = konf["api_version"], _env("IG_USER_ID"), _env("IG_ACCESS_TOKEN")
    basis = f"https://graph.facebook.com/{v}"
    auth = {"Authorization": f"Bearer {tok}"}  # Token im Kopf, nicht in der URL (CA-23)
    c = _form(f"{basis}/{uid}/media", {"media_type": "REELS", "upload_type": "resumable",
                                        "caption": meta["instagram"]["text"], "share_to_feed": "true"}, auth)
    groesse = video.stat().st_size
    _http("POST", f"https://rupload.facebook.com/ig-api-upload/{v}/{c['id']}",
          {"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(groesse)}, video.read_bytes(), zeit=900)
    for _ in range(60):
        s = http_json("GET", f"{basis}/{c['id']}?fields=status_code", auth)
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise AnbieterFehler("Instagram: Verarbeitung fehlgeschlagen")
        time.sleep(10)
    else:
        raise AnbieterFehler("Instagram: Verarbeitung nicht fertig, nicht veröffentlicht")
    p = _form(f"{basis}/{uid}/media_publish", {"creation_id": c["id"]}, auth)
    return {"id": p["id"], "url": "", "hinweis": ""}


PLATTFORMEN = {"youtube": youtube, "tiktok": tiktok, "instagram": instagram}

