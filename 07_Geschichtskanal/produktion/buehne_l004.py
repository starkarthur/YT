"""L004 «Why You'd Never Outrun the Boston Molasses Flood» – Bausteine-Stil (Vorbild Depth Theory), alles per Code gezeichnet.
Teil «einstieg»: Kaltstart-Blitz (1,2 s) + Szenen 1–4 (Skript 07_Geschichtskanal/Shorts/L004_Molasse_Skript.md, Stand 23.11.2026).

Aufruf (Workflow langvideo-buehne):
  python buehne_l004.py stimme            -> $GK_ARBEIT/l004/stimme.mp3 + wortzeiten.json   (ElevenLabs, ca. 600 Zeichen)
  python buehne_l004.py bilder 480p|4k    -> $GK_ARBEIT/l004/bild_<aufl>.mp4  (ffmpeg-Pipe; lokal ohne ffmpeg: OpenCV)
  python buehne_l004.py mix 480p|4k       -> $GK_ARBEIT/l004/ergebnis/L004_einstieg_<aufl>.mp4 (Stimme, Musik, Geräusche)
  python buehne_l004.py probe             -> wie stimme, aber ohne API (geschätzte Wortzeiten, stumme Stimme) für lokale Tests
Kosten: nur Stimme aus dem ElevenLabs-Abo. Kein Upload.
Fakten (gegengeprüft 23.11.2026, Wikipedia/NPR/NBC/Britannica): Tank 50 ft/15 m hoch, 90 ft/27 m Durchmesser, 2,3 Mio. Gallonen
(≈ 8,7 Mio. Liter, ≈ 26 Mio. lb), Welle ca. 25 ft (Quellen 15–40 ft), bis 35 mph (est.).
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HIER = Path(__file__).resolve().parent
ARBEIT = Path(os.environ.get("GK_ARBEIT", HIER / "arbeit")) / "l004"
KONF = json.loads((HIER / "konfig.json").read_text(encoding="utf-8"))
MODELL = KONF["stimme"]["modell"]
VOICE = "eBpY9CYcMHfCjbmwwKKB"          # «MysterStimmeMenschenEcht», vom Nutzer gewählt am 23.11.2026
MUSIK = HIER / "musik"
FPS = 24
KALT = 1.2                               # Kaltstart-Blitz vor dem ersten Satz
PAUSE = 0.35                             # Luft zwischen den Szenen

SZENEN = [
    "Picture this. It's lunchtime on Commercial Street, Boston, January 1919. You are standing in the sun. Behind you is a steel tank, five stories tall.",
    "Inside it are two point three million gallons of molasses. Nearly nine million liters of thick brown syrup. Twenty-six million pounds of it.",
    "In a few seconds, the steel will tear open. And a brown wave, reportedly as tall as a two-story house, will come down this street toward you.",
    "It moves at up to thirty-five miles an hour. You can't outrun it, and you can't swim in it. So what would you do? Let's find out.",
]

# ---------------------------------------------------------------- Stimme
def stimme(probe: bool) -> None:
    from anbieter import ElevenLabs
    ARBEIT.mkdir(parents=True, exist_ok=True)
    zeiten = []
    for i, txt in enumerate(SZENEN):
        w = ElevenLabs(probe=probe).sprechen(txt, VOICE, MODELL, ARBEIT / f"stimme_{i + 1}.mp3")
        dauer = (w[-1]["ende"] if w else 3.0) + 0.15
        zeiten.append({"szene": i + 1, "dauer": round(dauer, 3), "woerter": w})
    (ARBEIT / "wortzeiten.json").write_text(json.dumps(zeiten, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Stimme:", [z["dauer"] for z in zeiten], "Zeichen", sum(len(s) for s in SZENEN))


def zeitplan():
    z = json.loads((ARBEIT / "wortzeiten.json").read_text(encoding="utf-8"))
    t, plan = KALT, []
    for e in z:
        plan.append((t, t + e["dauer"] + PAUSE, e))
        t += e["dauer"] + PAUSE
    return plan, t + 1.0           # 1 s Ausklang mit Titel


# ---------------------------------------------------------------- Zeichnen (Logik 1708x960, wie Stiltest)
WW, HH = 1708, 960
BODEN = int(HH * 0.80)
M = 24                                                   # px pro Meter: Tank, Welle, Mensch im echten Massstab
TANK_X, TANK_B, TANK_H = int(WW * 0.05), int(27 * M), int(15 * M)
DU_X = int(WW * 0.84)
C = dict(himmel1=(20, 32, 45), himmel2=(9, 13, 19), haus=(24, 32, 43), haus2=(32, 42, 55), boden=(10, 13, 17),
         linie=(55, 66, 80), tank=(122, 130, 140), tank_d=(84, 90, 100), rot=(229, 56, 59), weiss=(244, 245, 247),
         grau=(141, 147, 156), melasse=(74, 38, 14), melasse_h=(160, 92, 30), du=(242, 196, 48), fenster=(240, 200, 110),
         graublau=(150, 170, 186))
clamp = lambda x, a=0.0, b=1.0: max(a, min(b, x))
ease = lambda x: (lambda y: 2 * y * y if y < .5 else 1 - (-2 * y + 2) ** 2 / 2)(clamp(x))
phase = lambda t, a, b: clamp((t - a) / (b - a)) if b > a else float(t >= a)


def schrift(gr, fk, fett=True):
    namen = ["Montserrat-Bold.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if fett else ["Montserrat-Regular.ttf", "arial.ttf", "DejaVuSans.ttf"]
    for n in namen:
        for p in (n, f"/usr/share/fonts/truetype/montserrat/{n}", f"/usr/share/fonts/truetype/dejavu/{n}"):
            try:
                return ImageFont.truetype(p, int(gr * 2 * fk))
            except OSError:
                continue
    return ImageFont.load_default()


class Z:
    """Zeichnet in der Logik 1708x960 auf eine Fläche × fk (480p: fk=1 + Verkleinerung, 4K: fk=2,25)."""
    def __init__(self, im, fk):
        self.d, self.f = ImageDraw.Draw(im), fk
        self.F = {k: schrift(g, fk, fe) for k, (g, fe) in
                  dict(titel=(30, True), text=(17, False), klein=(12, False), hud=(15, True), zahl=(34, True)).items()}

    def _p(self, xy):
        f = self.f
        return [(a * f, b * f) for a, b in xy] if xy and isinstance(xy[0], (tuple, list)) else [v * f for v in xy]

    def _w(self, k):
        if "width" in k:
            k["width"] = max(1, int(round(k["width"] * self.f)))
        return k

    def rect(self, xy, **k): self.d.rectangle(self._p(xy), **self._w(k))
    def oval(self, xy, **k): self.d.ellipse(self._p(xy), **self._w(k))
    def line(self, xy, **k): self.d.line(self._p(xy), **self._w(k))
    def poly(self, xy, **k): self.d.polygon(self._p(xy), **self._w(k))
    def rrect(self, xy, r, **k): self.d.rounded_rectangle(self._p(xy), radius=r * self.f, **self._w(k))

    def text(self, x, y, s, font="hud", fill=None, mitte=False, alpha=1.0):
        if alpha <= 0:
            return
        f = self.F[font]
        if mitte:
            b = self.d.textbbox((0, 0), s, font=f)
            x = x - (b[2] - b[0]) / self.f / 2
        col = tuple(int(c * alpha) for c in (fill or C["weiss"]))
        self.d.text((x * self.f, y * self.f), s, font=f, fill=col)

    def breite(self, s, font):
        b = self.d.textbbox((0, 0), s, font=self.F[font])
        return (b[2] - b[0]) / self.f


rng = np.random.default_rng(11)
HAEUSER, _x = [], TANK_X + TANK_B + 30
while _x < WW + 60:
    b, h = int(rng.integers(120, 220)), int(rng.integers(200, 380))
    HAEUSER.append((_x, b, h, [(int(rng.integers(0, 4)), int(rng.integers(0, 6))) for _ in range(6)]))
    _x += b + int(rng.integers(8, 30))


def welt(z: Z, t, tag=1.0, tank_dx=0.0, tank_durch=0.0, fuellung=0.0, beben=0.0):
    """Commercial Street: Himmel (Tag), Häuser, Hochbahn, Strasse, Tank (optional durchsichtig mit Füllstand)."""
    for y in range(0, BODEN, 8):
        p = y / BODEN
        col = tuple(int((C["himmel1"][i] * (1 - p) + C["himmel2"][i] * p) * (0.75 + 0.35 * tag)) for i in range(3))
        z.rect([0, y, WW, y + 8], fill=col)
    if tag > 0:                                                    # Sonne weiss (Farbregel Schnitt-Agent)
        z.oval([WW * .78 - 34, 70, WW * .78 + 34, 138], fill=tuple(int(c * (0.5 + 0.5 * tag)) for c in C["weiss"]))
    for (hx, hb, hh, fen) in HAEUSER:
        z.rect([hx, BODEN - hh, hx + hb, BODEN], fill=C["haus"])
        for (fx, fy) in fen:
            wx, wy = hx + 18 + fx * 40, BODEN - hh + 30 + fy * 52
            if wx + 20 < hx + hb and wy + 30 < BODEN - 30:
                z.rect([wx, wy, wx + 20, wy + 30], fill=C["haus2"])
    yb = BODEN - 250
    z.rect([0, yb, WW, yb + 22], fill=C["haus2"])
    for sx in range(60, WW, 260):
        z.rect([sx, yb + 22, sx + 16, BODEN], fill=C["haus2"])
    z.rect([0, BODEN, WW, HH], fill=C["boden"])
    z.line([0, BODEN, WW, BODEN], fill=C["linie"], width=4)
    tx = TANK_X + tank_dx + math.sin(t * 55) * 6 * beben
    if tx + TANK_B > -10:
        wand = C["tank"]
        if tank_durch > 0:
            wand = tuple(int(C["tank"][i] * (1 - .75 * tank_durch) + C["himmel2"][i] * .75 * tank_durch) for i in range(3))
        z.rect([tx, BODEN - TANK_H, tx + TANK_B, BODEN], fill=wand)
        if fuellung > 0:
            fh = (TANK_H - 18) * ease(fuellung)
            z.rect([tx + 6, BODEN - fh, tx + TANK_B - 6, BODEN], fill=C["melasse"])
            z.line([tx + 6, BODEN - fh, tx + TANK_B - 6, BODEN - fh], fill=C["melasse_h"], width=5)
        z.oval([tx, BODEN - TANK_H - 40, tx + TANK_B, BODEN - TANK_H + 40], fill=C["tank_d"])
        for r in range(1, 6):
            yy = BODEN - TANK_H + r * TANK_H // 6
            z.line([tx, yy, tx + TANK_B, yy], fill=C["tank_d"], width=3)
        for r in range(1, 18):
            xx = tx + r * TANK_B // 18
            z.line([xx, BODEN - TANK_H, xx, BODEN], fill=C["tank_d"], width=1)
        if tank_durch > 0:
            z.rect([tx, BODEN - TANK_H, tx + TANK_B, BODEN], outline=C["weiss"], width=3)
    return tx


def riss(z: Z, tx, p):
    if p <= 0:
        return
    c = tx + TANK_B * .6
    for kette in ([(c, BODEN - 160), (c + 25, BODEN - 210), (c + 10, BODEN - 255), (c + 40, BODEN - 300), (c + 60, BODEN - TANK_H)],
                  [(c, BODEN - 160), (c - 30, BODEN - 120), (c - 10, BODEN - 70), (c - 35, BODEN - 20)]):
        n = max(2, int(len(kette) * ease(p) + .5))
        z.line(kette[:n], fill=C["rot"], width=8, joint="curve")


def welle(z: Z, t, front, hoehe):
    if hoehe <= 1:
        return
    x0 = TANK_X + 40
    pts = [(x0, BODEN)]
    for i in range(41):
        q = i / 40
        pts.append((x0 + (front - x0) * q, BODEN - hoehe * (0.55 + 0.45 * math.sin(q * math.pi * 0.9)) - 8 * math.sin(t * 6 + i * .6)))
    pts += [(front + 60, BODEN - hoehe * .35), (front + 90, BODEN)]
    z.poly(pts, fill=C["melasse"])
    z.line(pts[1:-2], fill=C["melasse_h"], width=6)


def du(z: Z, x, t, laufen=0.0, umgedreht=False):
    s = 1.8 * M / 164
    ph = math.sin(t * 16) * laufen
    sp = -1 if umgedreht else 1
    P = lambda dx, dy: (x + dx * s * sp, BODEN - dy * s)
    k, r = P(0, 150), 16 * s
    z.oval([k[0] - r, k[1] - r, k[0] + r, k[1] + r], fill=C["du"])
    hals, huefte = P(4, 132), P(-4, 72)
    z.line([hals, huefte], fill=C["du"], width=4)
    z.line([huefte, P(-4 + 30 * ph, 36), P(10 + 34 * ph, 0)], fill=C["du"], width=4, joint="curve")
    z.line([huefte, P(-4 - 30 * ph, 36), P(-18 - 30 * ph, 0)], fill=C["du"], width=4, joint="curve")
    z.line([hals, P(28 * -ph, 100), P(30 * -ph, 76)], fill=C["du"], width=3)
    z.line([hals, P(-28 * -ph, 100), P(-30 * -ph, 76)], fill=C["du"], width=3)
    z.text(x - 18, BODEN - 1.8 * M - 40, "YOU", "klein", C["du"])


def massstab(z: Z, x, oben, txt, p, farbe):
    if p <= 0:
        return
    yy = BODEN - (BODEN - oben) * ease(p)
    z.line([x, BODEN, x, yy], fill=farbe, width=4)
    z.line([x - 14, yy, x + 14, yy], fill=farbe, width=4)
    z.line([x - 14, BODEN, x + 14, BODEN], fill=farbe, width=4)
    if p > .6:
        z.text(x + 18, yy - 6, txt, "hud", farbe)


def zeiger(z: Z, x, y, tx, ty, txt, p, farbe=None):
    if p <= 0:
        return
    farbe = farbe or C["weiss"]
    q = ease(p * 1.5)
    z.line([x, y, x + (tx - x) * q, y + (ty - y) * q], fill=farbe, width=4)
    z.oval([x - 8, y - 8, x + 8, y + 8], fill=farbe)
    if p > .5:
        z.text(tx + 10, ty - 26, txt, "hud", farbe)


def zeile(z: Z, txt, a, y=60, farbe=None, font="titel"):
    z.text(WW / 2, y, txt, font, farbe or C["weiss"], mitte=True, alpha=a)


def untertitel(z: Z, txt, a):
    if a <= 0 or not txt:
        return
    w = z.breite(txt, "text")
    x0, y0 = (WW - w) / 2 - 24, HH - 112
    z.rrect([x0, y0, x0 + w + 48, y0 + 60], 14, fill=(0, 0, 0))
    z.text(x0 + 24, y0 + 12, txt, "text", alpha=a)


def tacho(z: Z, cx, cy, r, wert, maxw, p, txt):
    if p <= 0:
        return
    z.oval([cx - r, cy - r, cx + r, cy + r], fill=(14, 20, 28), outline=C["linie"], width=3)
    for i in range(0, 8):
        w = math.pi * (0.85 + 1.3 * i / 7)
        z.line([cx + math.cos(w) * r * .82, cy + math.sin(w) * r * .82, cx + math.cos(w) * r * .95, cy + math.sin(w) * r * .95], fill=C["grau"], width=3)
    w = math.pi * (0.85 + 1.3 * (wert / maxw) * ease(p))
    z.line([cx, cy, cx + math.cos(w) * r * .8, cy + math.sin(w) * r * .8], fill=C["rot"], width=6)
    z.oval([cx - 10, cy - 10, cx + 10, cy + 10], fill=C["rot"])
    z.text(cx, cy + r * .35, txt, "hud", C["weiss"], mitte=True, alpha=clamp(p * 2))


def durchgestrichen(z: Z, x, y, txt, p_zeig, p_strich):
    if p_zeig <= 0:
        return
    z.text(x, y, txt, "zahl", C["rot"], alpha=clamp(p_zeig * 3))
    if p_strich > 0:
        w = z.breite(txt, "zahl")
        z.line([x - 6, y + 34, x - 6 + (w + 12) * ease(p_strich), y + 34], fill=C["weiss"], width=7)


def satz_bei(e, t_lokal):
    """Untertitel: der Satz der Szene, in dem die Stimme gerade ist."""
    saetze, aktuell, start = [], [], None
    for w in e["woerter"]:
        aktuell.append(w["wort"]); start = w["start"] if start is None else start
        if w["wort"].endswith((".", "?", "!")):
            saetze.append((start, w["ende"], " ".join(aktuell))); aktuell, start = [], None
    if aktuell:
        saetze.append((start, e["woerter"][-1]["ende"], " ".join(aktuell)))
    for i, (a, b, s) in enumerate(saetze):
        nxt = saetze[i + 1][0] if i + 1 < len(saetze) else b + 1.0
        if a - .1 <= t_lokal < nxt:
            return s
    return ""


def wort_zeit(e, wort, ab=0):
    for i, w in enumerate(e["woerter"][ab:]):
        if w["wort"].lower().strip(".,?!") == wort:
            return w["start"]
    return None


def bild(t, plan, ende, fk):
    im = Image.new("RGB", (round(WW * fk), round(HH * fk)))
    z = Z(im, fk)
    if t < KALT:                                                     # Kaltstart-Blitz: Riss + Welle kurz vor «du»
        tx = welt(z, t, tag=0.0, beben=0.6)
        riss(z, tx, 1.0)
        welle(z, t, DU_X - 160, 7.6 * M)
        du(z, DU_X, t, umgedreht=True)
        return im
    n = 0
    while n < len(plan) - 1 and t >= plan[n][1]:
        n += 1
    a, b, e = plan[n]
    tl = t - a
    if n == 0:                                                       # Szene 1: sonnige Strasse, Tank fährt ein
        satz2 = wort_zeit(e, "you") or 4.5
        tx = welt(z, t, tag=1.0, tank_dx=-(1 - ease(phase(tl, satz2 - .5, satz2 + 1.5))) * (TANK_B + TANK_X + 40))
        du(z, DU_X, t)
        zeile(z, "COMMERCIAL STREET, BOSTON · JANUARY 15, 1919", min(phase(tl, .2, .8), 1 - phase(tl, b - a - .5, b - a)), 60, font="hud")
        massstab(z, tx + TANK_B + 26, BODEN - TANK_H, "50 FT / 15 M", phase(tl, (wort_zeit(e, "steel") or 7) - .2, (wort_zeit(e, "steel") or 7) + .8), C["weiss"])
    elif n == 1:                                                     # Szene 2: Füllung + Zähler
        tx = welt(z, t, tag=1.0, tank_durch=ease(phase(tl, 0, 1.0)), fuellung=phase(tl, .5, 6.5))
        du(z, DU_X, t)
        t2, t3 = wort_zeit(e, "nearly") or 3.5, wort_zeit(e, "twenty-six") or wort_zeit(e, "twenty") or 6.5
        x0 = tx + TANK_B + 60
        gal = int(2_300_000 * ease(phase(tl, .3, t2 - .2)))
        z.text(x0, 250, f"{gal:,} GAL", "zahl", C["melasse_h"])
        if tl > t2 - .2:
            z.text(x0, 345, "≈ 8.7 MILLION LITERS", "hud", C["weiss"], alpha=phase(tl, t2 - .2, t2 + .3))
        if tl > t3 - .2:
            lb = int(26_000_000 * ease(phase(tl, t3 - .2, t3 + .8)))
            z.text(x0, 395, f"≈ {lb:,} LB", "hud", C["grau"])
    elif n == 2:                                                     # Szene 3: Riss + Wellen-Vorschau
        tx = welt(z, t, tag=1.0 - .7 * phase(tl, 0, 3))
        tw = wort_zeit(e, "brown") or 3.5
        riss(z, tx, phase(tl, .3, 2.5))
        p = phase(tl, tw - .3, b - a - 2.0)
        front = TANK_X + TANK_B + (DU_X - 200 - TANK_X - TANK_B) * ease(p)
        welle(z, t, front, 7.6 * M * ease(clamp(p * 3)))
        du(z, DU_X, t)
        tz = wort_zeit(e, "reportedly") or tw + 1
        if tl > tz - .3:
            hx, hb, hh = DU_X - 300, 7 * M, 6.4 * M                                       # Haus-Piktogramm, 2 Stockwerke (~7,6 m mit Dach)
            z.rect([hx, BODEN - hh, hx + hb, BODEN], outline=C["weiss"], width=3)
            z.line([hx, BODEN - hh / 2, hx + hb, BODEN - hh / 2], fill=C["weiss"], width=2)
            z.poly([(hx - 8, BODEN - hh), (hx + hb / 2, BODEN - 7.6 * M), (hx + hb + 8, BODEN - hh)], outline=C["weiss"], width=3)
            zeiger(z, front - 40, BODEN - 7.6 * M, front + 40, BODEN - 7.6 * M - 90, "REPORTEDLY ~25 FT (EST.)", phase(tl, tz - .3, tz + .9), C["melasse_h"])
    else:                                                            # Szene 4: Tacho, RUN?/SWIM?, Zurückspulen, Titel
        tr = wort_zeit(e, "so") or 6.0
        rueck = phase(tl, tr + 1.2, tr + 2.2)
        tx = welt(z, t, tag=.3 + .7 * rueck)
        if rueck < 1:
            riss(z, tx, 1 - rueck)
            welle(z, t, DU_X - 200 - (DU_X - 200 - TANK_X - TANK_B) * rueck, 7.6 * M * (1 - rueck))
        du(z, DU_X, t, umgedreht=tl > 1.0 and rueck < 1, laufen=phase(tl, 1.0, 1.4) * (1 - rueck))
        tacho(z, WW - 300, 250, 120, 35, 40, phase(tl, .1, 1.6) * (1 - rueck), "35 MPH (EST.)")
        t_run, t_swim = wort_zeit(e, "outrun") or 3.0, wort_zeit(e, "swim") or 4.5
        durchgestrichen(z, 120, 170, "RUN?", phase(tl, t_run - .3, t_run) * (1 - rueck), phase(tl, t_run + .4, t_run + .9))
        durchgestrichen(z, 120, 280, "SWIM?", phase(tl, t_swim - .3, t_swim) * (1 - rueck), phase(tl, t_swim + .4, t_swim + .9))
        if t >= b - .2 or rueck >= 1:
            pt = phase(t, b - 1.0, b - .4)
            if pt > 0:
                z.rrect([WW / 2 - 560, 110, WW / 2 + 560, 290], 18, fill=tuple(int(c * pt) for c in (8, 11, 16)))
            zeile(z, "WHY YOU'D NEVER OUTRUN", pt, 130, C["weiss"])
            zeile(z, "THE BOSTON MOLASSES FLOOD", phase(t, b - .8, b - .2), 205, C["rot"])
    if t < b:
        untertitel(z, satz_bei(e, tl), 1.0)
    return im


# ---------------------------------------------------------------- Bilder rendern
def bilder(aufl: str) -> Path:
    plan, ende = zeitplan()
    W, H = (3840, 2160) if aufl == "4k" else (854, 480)
    fk = 2.25 if aufl == "4k" else 1.0
    ziel = ARBEIT / f"bild_{aufl}.mp4"
    n = int(ende * FPS)
    ff = shutil.which("ffmpeg")
    if ff:
        p = subprocess.Popen([ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                              "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18" if aufl == "4k" else "20",
                              "-pix_fmt", "yuv420p", str(ziel)], stdin=subprocess.PIPE)
        schreibe = lambda im: p.stdin.write(im.tobytes())
    else:                                                               # lokaler Test ohne ffmpeg
        import cv2
        vw = cv2.VideoWriter(str(ziel), cv2.VideoWriter_fourcc(*"avc1"), FPS, (W, H))
        schreibe = lambda im: vw.write(cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR))
    stich = []
    for i in range(n):
        t = i / FPS
        im = bild(t, plan, ende, fk).resize((W, H), Image.LANCZOS)
        schreibe(im)
        if i % (FPS * 4) == FPS * 2:
            stich.append(im.resize((640, 360)))
    if ff:
        p.stdin.close(); p.wait()
    else:
        vw.release()
    kb = Image.new("RGB", (640 * 4, 360 * ((len(stich) + 3) // 4)))
    for k, im in enumerate(stich):
        kb.paste(im, ((k % 4) * 640, (k // 4) * 360))
    kb.save(ARBEIT / f"kontaktbogen_{aufl}.jpg", quality=85)
    print("Bilder", aufl, n, "Frames,", round(ende, 2), "s")
    return ziel


# ---------------------------------------------------------------- Ton mischen (nur Cloud, ffmpeg)
def mix(aufl: str) -> None:
    plan, ende = zeitplan()
    ff = shutil.which("ffmpeg")
    if not ff:
        print("ffmpeg fehlt (nur im Workflow)"); sys.exit(1)
    aus = ARBEIT / "ergebnis"; aus.mkdir(parents=True, exist_ok=True)
    eing, filt, labels = ["-i", str(ARBEIT / f"bild_{aufl}.mp4")], [], []
    def spur(datei, start, vol_db, dauer=None, fade=0.0):
        k = len(eing) // 2
        eing.extend(["-i", str(datei)])
        f = f"[{k}:a]"
        if dauer:
            f += f"atrim=0:{dauer},"
        if fade:
            f += f"afade=t=out:st={max(0, (dauer or 9) - fade)}:d={fade},"
        f += f"volume={vol_db}dB,adelay={int(start * 1000)}|{int(start * 1000)}[a{k}]"
        filt.append(f); labels.append(f"[a{k}]")
    for i, (a, b, e) in enumerate(plan):
        spur(ARBEIT / f"stimme_{i + 1}.mp3", a, 0)
    spur(MUSIK / "dark_mystery_piano.mp3", 0, -24, ende, 2.0)                     # ab 0:00 dunkel (Hook-Empfehlung)
    spur(MUSIK / "geraeusche" / "whoosh.mp3", 0, -8, 1.0)
    spur(MUSIK / "geraeusche" / "erdbeben.mp3", 0, -6, KALT + .3, .3)
    spur(MUSIK / "geraeusche" / "erdbeben.mp3", plan[2][0] + 0.4, -14, 2.5, 1.0)  # Szene 3: Riss
    spur(MUSIK / "geraeusche" / "whoosh.mp3", plan[3][0] + (wort_zeit(plan[3][2], "so") or 6.0) + 1.2, -10, 1.0)
    filt.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0,alimiter=limit=0.95[ton]")
    ziel = aus / f"L004_einstieg_{aufl}.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", *eing, "-filter_complex", ";".join(filt), "-map", "0:v", "-map", "[ton]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(ziel)], check=True)
    shutil.copy(ARBEIT / f"kontaktbogen_{aufl}.jpg", aus)
    print("fertig", ziel)


if __name__ == "__main__":
    was = sys.argv[1] if len(sys.argv) > 1 else ""
    if was in ("stimme", "probe"):
        stimme(probe=(was == "probe"))
    elif was == "bilder":
        bilder(sys.argv[2] if len(sys.argv) > 2 else "480p")
    elif was == "mix":
        mix(sys.argv[2] if len(sys.argv) > 2 else "480p")
    else:
        print(__doc__); sys.exit(1)
