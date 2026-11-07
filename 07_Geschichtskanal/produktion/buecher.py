"""Kostenbuch, Veröffentlichungsbuch und Fehlerbuch (nur anhängen, JSON-Zeilen)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


class BudgetUeberschritten(Exception):
    pass


class DoppelteVeroeffentlichung(Exception):
    pass


def jetzt() -> datetime:
    return datetime.now(timezone.utc)


def _lies(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(z) for z in p.read_text(encoding="utf-8").splitlines() if z.strip()]


def _haenge_an(p: Path, eintrag: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(eintrag, ensure_ascii=False) + "\n")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class Kostenbuch:
    def __init__(self, datei: Path, limit_short: float, limit_monat: float):
        self.datei, self.limit_short, self.limit_monat = datei, limit_short, limit_monat

    def summe(self, short: str | None = None, monat: str | None = None) -> float:
        return round(sum(e["usd"] for e in _lies(self.datei)
                         if (short is None or e["short"] == short)
                         and (monat is None or e["zeit"].startswith(monat))), 4)

    def buchen(self, short: str, posten: str, usd: float, anbieter: str, t: datetime | None = None) -> None:
        """Vor jedem kostenpflichtigen Aufruf. Bricht ab, bevor ein Limit überschritten wird."""
        t = t or jetzt()
        if usd < 0:
            raise ValueError("negativ")
        if self.summe(short=short) + usd > self.limit_short:
            raise BudgetUeberschritten(f"Short {short}: Limit {self.limit_short} USD")
        if self.summe(monat=t.strftime("%Y-%m")) + usd > self.limit_monat:
            raise BudgetUeberschritten(f"Monat: Limit {self.limit_monat} USD")
        _haenge_an(self.datei, {"zeit": t.isoformat(), "short": short, "posten": posten,
                                "usd": round(usd, 4), "anbieter": anbieter})


class Veroeffentlichungsbuch:
    def __init__(self, datei: Path):
        self.datei = datei

    @staticmethod
    def schluessel(short: str, plattform: str, video_sha: str) -> str:
        return hashlib.sha256(f"{short}|{plattform}|{video_sha}".encode()).hexdigest()[:32]

    ZAEHLT = ("ok", "begonnen")  # "begonnen" zählt wie veröffentlicht (CA-16: Absturz mitten im Upload)

    def bereits(self, short: str, plattform: str) -> bool:
        """Ein Short wird je Plattform nur einmal veröffentlicht, auch in neuer Fassung nicht erneut."""
        return any(e["short"] == short and e["plattform"] == plattform and e["status"] in self.ZAEHLT
                   for e in _lies(self.datei))

    def erfolgreich(self) -> int:
        return len({e["short"] for e in _lies(self.datei) if e["status"] == "ok"})

    def heute(self, plattform: str, t: datetime | None = None) -> int:
        tag = (t or jetzt()).strftime("%Y-%m-%d")
        return len({e["short"] for e in _lies(self.datei)
                    if e["plattform"] == plattform and e["status"] in self.ZAEHLT and e["zeit"].startswith(tag)})

    def eintragen(self, short: str, plattform: str, video_sha: str, status: str, plattform_id: str = "",
                  info: str = "") -> None:
        if status in self.ZAEHLT and any(e["short"] == short and e["plattform"] == plattform
                                         and e["status"] in (status, "ok") for e in _lies(self.datei)):
            raise DoppelteVeroeffentlichung(f"{short} ist auf {plattform} schon online")
        _haenge_an(self.datei, {"zeit": jetzt().isoformat(), "short": short, "plattform": plattform,
                                "sha256": video_sha, "schluessel": self.schluessel(short, plattform, video_sha),
                                "status": status, "id": plattform_id, "info": maskiere(info)[:300]})


class Fehlerbuch:
    def __init__(self, datei: Path):
        self.datei = datei

    def eintragen(self, short: str, schritt: str, fehler: str) -> None:
        _haenge_an(self.datei, {"zeit": jetzt().isoformat(), "short": short, "schritt": schritt,
                                "fehler": maskiere(fehler)[:300]})


GEHEIM_VARIABLEN = ("FAL_KEY", "ELEVENLABS_API_KEY", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN",
                    "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN", "IG_ACCESS_TOKEN")


def maskiere(text: str) -> str:
    """Geheimnisse und Token-artige Zeichenketten vor dem Protokollieren entfernen (CA-23)."""
    import os
    import re
    t = str(text)
    for n in GEHEIM_VARIABLEN:
        w = os.environ.get(n)
        if w and len(w) >= 6:
            t = t.replace(w, "***")
    return re.sub(r"(access_token=|Bearer |Key |key=)[^\s&'\"]+", r"\1***", t)


class Quarantaene:
    """Shorts, deren Produktion nach einer Zahlung scheiterte. naechster() überspringt sie (CA-15).
    Freigeben: Eintrag mit "aufgehoben": true anhängen (nur Nutzer/Chef-Agent)."""

    def __init__(self, datei: Path):
        self.datei = datei

    def gesperrt(self, short: str) -> bool:
        stand = False
        for e in _lies(self.datei):
            if e["short"] == short:
                stand = not e.get("aufgehoben", False)
        return stand

    def sperren(self, short: str, grund: str) -> None:
        _haenge_an(self.datei, {"zeit": jetzt().isoformat(), "short": short, "grund": maskiere(grund)[:300]})
