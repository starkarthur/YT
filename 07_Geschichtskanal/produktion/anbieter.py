"""Anbindung der KI-Dienste: Bild und Video (fal.ai Queue-API), Stimme mit Wortzeiten (ElevenLabs).

Nur Standardbibliothek (urllib). Schlüssel kommen aus Umgebungsvariablen:
  FAL_KEY, ELEVENLABS_API_KEY
Im Probelauf (probe=True) wird nichts aufgerufen und nichts bezahlt. Es entstehen nur Platzhalter.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.request
from pathlib import Path


class AnbieterFehler(Exception):
    pass


MAX_DOWNLOAD = 300 * 1024 * 1024


class _NurHttps(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen nur auf https (CA-23)."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith("https://"):
            raise AnbieterFehler("Weiterleitung auf Nicht-https abgelehnt")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OEFFNER = urllib.request.build_opener(_NurHttps())


def _http(methode: str, url: str, kopf: dict, daten: bytes | None = None, zeit: int = 120) -> tuple[int, dict, bytes]:
    if not url.startswith("https://"):
        raise AnbieterFehler("nur https")
    req = urllib.request.Request(url, data=daten, method=methode, headers=kopf)
    try:
        with _OEFFNER.open(req, timeout=zeit) as r:
            roh = r.read(MAX_DOWNLOAD + 1)
            if len(roh) > MAX_DOWNLOAD:
                raise AnbieterFehler("Antwort zu groß")
            return r.status, dict(r.headers), roh
    except urllib.error.HTTPError as e:
        raise AnbieterFehler(f"{methode} {url.split('?')[0]} → HTTP {e.code}: {e.read()[:200]!r}") from None


def http_json(methode: str, url: str, kopf: dict, body: dict | None = None, zeit: int = 120) -> dict:
    daten = json.dumps(body).encode() if body is not None else None
    k = {"Content-Type": "application/json", **kopf}
    _, _, roh = _http(methode, url, k, daten, zeit)
    return json.loads(roh) if roh else {}


def lade_datei(url: str, ziel: Path) -> Path:
    _, _, roh = _http("GET", url, {}, zeit=300)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(roh)
    return ziel


def _schluessel(name: str) -> str:
    wert = os.environ.get(name)
    if not wert:
        raise AnbieterFehler(f"Umgebungsvariable {name} fehlt")
    return wert


# --- fal.ai -------------------------------------------------------------
class Fal:
    BASIS = "https://queue.fal.run"

    def __init__(self, probe: bool = False):
        self.probe = probe

    def _lauf(self, modell: str, eingabe: dict, max_warten_s: int = 300) -> dict:
        kopf = {"Authorization": f"Key {_schluessel('FAL_KEY')}"}
        auftrag = http_json("POST", f"{self.BASIS}/{modell}", kopf, eingabe)
        status_url, antwort_url = auftrag["status_url"], auftrag["response_url"]
        ende = time.time() + max_warten_s
        while time.time() < ende:
            s = http_json("GET", status_url, kopf)
            if s.get("status") == "COMPLETED":
                return http_json("GET", antwort_url, kopf)
            if s.get("status") in ("FAILED", "ERROR"):
                raise AnbieterFehler(f"fal {modell}: {s}")
            time.sleep(5)
        raise AnbieterFehler(f"fal {modell}: Zeitüberschreitung")

    def bild(self, modell: str, prompt: str, ziel: Path, aufloesung: str = "2K") -> tuple[Path, str]:
        """Gibt (lokale Datei, fal-URL) zurück. Die URL nutzt der Videoschritt direkt."""
        if self.probe:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(b"PROBE-BILD " + prompt[:40].encode())
            return ziel, "https://probe.invalid/bild.png"
        r = self._lauf(modell, {"prompt": prompt, "aspect_ratio": "9:16", "num_images": 1,
                                "resolution": aufloesung, "output_format": "png"})
        url = r["images"][0]["url"]
        return lade_datei(url, ziel), url

    @staticmethod
    def video_eingabe(modell: str, bild_url: str, prompt: str, dauer_s: int) -> dict:
        """Jedes Modell erwartet andere Feldnamen (fal.ai-Doku, 07.11.2026)."""
        if "kling-video" in modell:   # Seitenverhältnis kommt aus dem Startbild
            return {"start_image_url": bild_url, "prompt": prompt, "duration": str(dauer_s),
                    "generate_audio": False, "negative_prompt": "blur, distort, low quality, text, watermark, letterbox, black bars, widescreen"}
        if "wan-3.0" in modell:  # fal-Schema 08.11.2026: start_image_url, duration als Zahl, Feld "audio"
            return {"start_image_url": bild_url, "prompt": prompt, "duration": int(dauer_s), "resolution": "1080p",
                    "aspect_ratio": "9:16", "audio": False, "enable_prompt_expansion": False}
        if "veo3" in modell:          # nur 4s, 6s, 8s
            d = next((x for x in (4, 6, 8) if x >= dauer_s), 8)  # lieber länger als zu kurz
            return {"image_url": bild_url, "prompt": prompt, "duration": f"{d}s", "aspect_ratio": "9:16",
                    "resolution": "1080p", "generate_audio": False}
        return {"image_url": bild_url, "prompt": prompt, "duration": str(dauer_s), "generate_audio": False}

    def video(self, modell: str, bild_url: str, prompt: str, dauer_s: int, ziel: Path) -> Path:
        if self.probe:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(b"PROBE-VIDEO " + prompt[:40].encode())
            return ziel
        r = self._lauf(modell, self.video_eingabe(modell, bild_url, prompt, dauer_s), max_warten_s=600)
        return lade_datei(r["video"]["url"], ziel)



# --- ElevenLabs ---------------------------------------------------------
def woerter_aus_alignment(al: dict) -> list[dict]:
    """Zeichenzeiten → Wörter mit Start/Ende (für Untertitel und Schnittpunkte)."""
    woerter, akt, start = [], "", None
    for z, s, e in zip(al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]):
        if z.isspace():
            if akt:
                woerter.append({"wort": akt, "start": start, "ende": letzte})
            akt, start = "", None
            continue
        if start is None:
            start = s
        akt += z
        letzte = e
    if akt:
        woerter.append({"wort": akt, "start": start, "ende": letzte})
    return woerter


class ElevenLabs:
    def __init__(self, probe: bool = False):
        self.probe = probe

    def sprechen(self, text: str, voice_id: str, modell: str, ziel: Path) -> list[dict]:
        """Schreibt MP3 nach ziel und gibt Wortzeiten zurück."""
        if self.probe:
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(b"PROBE-AUDIO")
            t, woerter = 0.0, []
            for w in text.split():  # ca. 2,8 Wörter pro Sekunde (übliches Short-Tempo)
                d = 0.15 + 0.03 * len(w)
                woerter.append({"wort": w, "start": round(t, 3), "ende": round(t + d, 3)})
                t += d + 0.06 + (0.25 if w.endswith((".", "?", "!")) else 0)
            return woerter
        if not voice_id:
            raise AnbieterFehler("voice_id fehlt in konfig.json")
        r = http_json("POST", f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
                      {"xi-api-key": _schluessel("ELEVENLABS_API_KEY")},
                      {"text": text, "model_id": modell, "output_format": "mp3_44100_192"})
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_bytes(base64.b64decode(r["audio_base64"]))
        return woerter_aus_alignment(r["alignment"])
