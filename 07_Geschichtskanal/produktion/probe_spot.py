"""Werbespot aus einem Storyboard (JSON): Bilder, Clips mit Anschluss, Schnitt. Über Higgsfield, kein Upload.

Aufruf: python probe_spot.py <storyboard.json> [--aufloesung 480p|720p|1080p] [--nur-bilder] [--probe]
Umgebung: HIGGSFIELD_KEY, GK_ARBEIT. Optional SPOT_SPEC (JSON-Text) ersetzt die Datei.

Arbeitsweise (Gedaechtnis/Higgsfield-Arbeitsweise.md):
  - Erst Bilder (Soul 2, je Motiv 1 oder 4 Varianten), dann Clips (Seedance 2.5 Bild-zu-Video).
  - Anschluss: Ein Clip startet von einem Bild ("bild:name#2") oder vom letzten Bild eines anderen Clips
    ("ende:clipname"). So bleiben Figuren, Raum und Zustand von Szene zu Szene gleich.
  - Alles wird im Arbeitsordner unter einem Namen aus Inhalt und Auflösung abgelegt. Ein späterer Lauf mit
    demselben Material (Artefakt) erzeugt nur neu, was sich im Storyboard geändert hat.
  - Unabhängige Clips laufen gleichzeitig.
  - Schrift entsteht nur im Schnitt, nie im erzeugten Bild.

Storyboard:
  {"id": "S001", "limit_usd": 6,
   "bilder": {"buero": {"prompt": "...", "anzahl": 4} | {"url": "https://..."}},
   "clips":  {"ruhe": {"von": "bild:buero#2", "prompt": "...", "dauer": 5}, "panik": {"von": "ende:ruhe", ...}},
   "schnitt": [{"clip": "ruhe", "ab": 0, "dauer": 4, "tempo": 1.0, "band": "TEXT", "band_ab": 2.0},
               {"standbild": "bild:haus#1", "dauer": 4, "zoom": [1.0, 1.12], "duester": true, "schild": "ZU VERMIETEN"},
               {"rueck": true, "dauer": 3},
               {"karte": ["MARKE", "Spruch"], "dauer": 3}]}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import lauf
from anbieter import Higgsfield, _http, _schluessel, http_json, lade_datei

BILD_MODELL = "higgsfield-ai/soul/v2/standard"
VIDEO_MODELL = "bytedance/seedance-2.5/image-to-video"
VIDEO_USD_S = 0.0738        # Listenpreis 1080p (Higgsfield-Blog); 480p und 720p grob geschätzt
FAKTOR = {"480p": 0.35, "720p": 0.6, "1080p": 1.0}
BILD_USD = 0.006
B, H, FPS = 1920, 1080, 30
FETT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
NORMAL = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BILDF = f"scale={B}:{H}:force_original_aspect_ratio=increase,crop={B}:{H},fps={FPS},setsar=1"
TONF = "aresample=48000,aformat=channel_layouts=stereo"
STILLE = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
KODIEREN = ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]


def ff(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True, cwd=cwd)


def probe_wert(p: Path, was: str) -> str:
    return subprocess.run(["ffprobe", "-v", "error", *was.split(), "-of", "csv=p=0", str(p)],
                          capture_output=True, text=True).stdout.strip()


def hat_ton(p: Path) -> bool:
    return bool(probe_wert(p, "-select_streams a -show_entries stream=index"))


def dauer(p: Path) -> float:
    return float(probe_wert(p, "-show_entries format=duration"))


def kurz(*teile) -> str:
    return hashlib.sha1("|".join(str(t) for t in teile).encode()).hexdigest()[:8]


class Spot:
    def __init__(self, spec: dict, aufloesung: str, probe: bool):
        self.spec, self.aufl, self.probe = spec, aufloesung, probe
        self.sid = spec.get("id", "S000")
        self.limit = float(spec.get("limit_usd", 6))
        self.arbeit = lauf.arbeitsordner() / "spot"
        self.arbeit.mkdir(parents=True, exist_ok=True)
        self.zustand_datei = self.arbeit / "zustand.json"
        self.zustand = json.loads(self.zustand_datei.read_text(encoding="utf-8")) if self.zustand_datei.exists() else {}
        self.buch = None if probe else lauf.buecher()[0]
        self.summe = 0.0 if probe else self.buch.summe(short=self.sid)
        self.hf = Higgsfield()

    # --- Kosten und Zustand ------------------------------------------------
    def zahlen(self, posten: str, usd: float) -> None:
        if self.probe:
            return
        if self.summe + usd > self.limit:
            sys.exit(f"Grenze {self.limit} USD: {posten} würde {usd:.2f} USD kosten, bisher {self.summe:.2f} USD")
        self.summe += usd
        self.buch.buchen(self.sid, posten, usd, "higgsfield")

    def merken(self, schluessel: str, wert) -> None:
        self.zustand[schluessel] = wert
        self.zustand_datei.write_text(json.dumps(self.zustand, indent=1), encoding="utf-8")

    # --- Bilder --------------------------------------------------------------
    def bild_dateien(self, name: str) -> list[Path]:
        b = self.spec["bilder"][name]
        kennung = kurz(b.get("prompt", ""), b.get("url", ""), b.get("format", "16:9"))
        return [self.arbeit / f"bild_{name}_{kennung}_{n}.png" for n in range(1, int(b.get("anzahl", 1)) + 1)]

    def bilder(self) -> None:
        for name, b in self.spec.get("bilder", {}).items():
            dateien = self.bild_dateien(name)
            schluessel = "urls:" + dateien[0].name
            if all(d.exists() for d in dateien) and schluessel in self.zustand:
                continue
            if self.probe:
                for d in dateien:
                    ff("-f", "lavfi", "-i", f"testsrc2=s={B}x{H}", "-frames:v", "1", str(d))
                urls = ["https://probe.invalid/b.png"] * len(dateien)
            elif "url" in b:
                urls = [b["url"]]
                lade_datei(b["url"], dateien[0])
            else:
                if len(dateien) not in (1, 4):
                    sys.exit(f"Bild {name}: anzahl muss 1 oder 4 sein")
                self.zahlen(f"bild_{name}", BILD_USD * len(dateien))
                r = self.hf._lauf(BILD_MODELL, {"prompt": b["prompt"], "aspect_ratio": b.get("format", "16:9"),
                                               "resolution": "1080p", "batch_size": len(dateien), "enhance_prompt": False})
                urls = [x["url"] for x in r["images"]][:len(dateien)]
                for d, u in zip(dateien, urls):
                    lade_datei(u, d)
                print(f"Bild {name}: {len(urls)} Varianten fertig", flush=True)
            self.merken(schluessel, urls)
        for name in self.spec.get("bilder", {}):          # Auswahlbogen je Motiv mit vier Varianten
            dateien = self.bild_dateien(name)
            if len(dateien) == 4:
                eing = [x for d in dateien for x in ("-i", str(d))]
                graph = ";".join(f"[{i}:v]scale=960:540:force_original_aspect_ratio=increase,crop=960:540,"
                                 f"drawbox=x=0:y=0:w=110:h=96:color=black@0.75:t=fill,"
                                 f"drawtext=fontfile={FETT}:text='{i + 1}':fontsize=72:fontcolor=white:x=34:y=10[b{i}]"
                                 for i in range(4)) + ";[b0][b1][b2][b3]xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0[v]"
                ff(*eing, "-filter_complex", graph, "-map", "[v]", "-frames:v", "1", "-q:v", "3",
                   str(self.arbeit / f"auswahl_{name}.jpg"))

    def bild_ref(self, ref: str) -> tuple[Path, str]:
        """'bild:name#2' → (Datei, URL)."""
        name, _, nr = ref.removeprefix("bild:").partition("#")
        dateien = self.bild_dateien(name)
        i = int(nr or 1) - 1
        return dateien[i], self.zustand["urls:" + dateien[0].name][i]

    # --- Clips ---------------------------------------------------------------
    def clip_datei(self, name: str) -> Path:
        c = self.spec["clips"][name]
        von = c["von"]
        herkunft = self.clip_datei(von.removeprefix("ende:")).name if von.startswith("ende:") else \
            self.bild_ref(von)[0].name
        return self.arbeit / f"clip_{name}_{self.aufl}_{kurz(c['prompt'], c['dauer'], herkunft, c.get('take', 1))}.mp4"

    def start_url(self, von: str) -> str:
        if von.startswith("bild:"):
            return self.bild_ref(von)[1]
        quelle = self.clip_datei(von.removeprefix("ende:"))
        schluessel = "ende:" + quelle.name
        if schluessel in self.zustand:
            return self.zustand[schluessel]
        jpg = quelle.with_suffix(".ende.jpg")
        ff("-sseof", "-0.12", "-i", str(quelle), "-frames:v", "1", "-update", "1", "-q:v", "2", str(jpg))
        kopf = {"Authorization": f"Key {_schluessel('HIGGSFIELD_KEY')}"}
        r = http_json("POST", f"{Higgsfield.BASIS}/files/generate-upload-url", kopf, {"content_type": "image/jpeg"})
        _http("PUT", r["upload_url"], dict(r.get("upload_headers") or {"Content-Type": "image/jpeg"}), jpg.read_bytes())
        self.merken(schluessel, r["public_url"])
        return r["public_url"]

    def clips(self) -> None:
        offen = {n for n in self.spec.get("clips", {}) if not self.fertig(self.clip_datei(n))}
        while offen:
            bereit = [n for n in sorted(offen) if not self.spec["clips"][n]["von"].startswith("ende:")
                      or self.spec["clips"][n]["von"].removeprefix("ende:") not in offen]
            if not bereit:
                sys.exit(f"Clips hängen im Kreis voneinander ab: {sorted(offen)}")
            auftraege = []
            for n in bereit:
                c, ziel = self.spec["clips"][n], self.clip_datei(n)
                if self.probe:
                    ff("-f", "lavfi", "-i", f"testsrc2=s=854x480:r={FPS}:d={c['dauer']}", "-f", "lavfi", "-i",
                       f"sine=f={300 + 60 * len(auftraege)}:d={c['dauer']}", "-c:v", "libx264", "-preset", "ultrafast",
                       "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(ziel))
                    continue
                eingabe = {"image_url": self.start_url(c["von"]), "prompt": c["prompt"], "duration": int(c["dauer"]),
                           "resolution": self.aufl, "generate_audio": True}
                self.zahlen(ziel.stem, VIDEO_USD_S * c["dauer"] * FAKTOR[self.aufl])
                auftraege.append((n, ziel, eingabe))
            if auftraege:
                def machen(a):
                    n, ziel, eingabe = a
                    r = Higgsfield()._lauf(VIDEO_MODELL, eingabe, max_warten_s=1500)
                    lade_datei(r["video"]["url"], ziel)
                    print(f"Clip {n} fertig", flush=True)
                with ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(machen, auftraege))
            offen -= set(bereit)

    @staticmethod
    def fertig(p: Path) -> bool:
        return p.exists() and p.stat().st_size > 20_000

    # --- Schnitt ---------------------------------------------------------------
    def text_datei(self, name: str, text: str) -> str:
        (self.arbeit / name).write_text(text, encoding="utf-8")
        return name

    def teil_clip(self, i: int, s: dict, ziel: Path) -> None:
        quelle = self.clip_datei(s["clip"])
        ab, d, tempo = float(s.get("ab", 0)), float(s["dauer"]), float(s.get("tempo", 1.0))
        ende = ab + d * tempo
        band = ""
        if s.get("band"):
            t = self.text_datei(f"band_{i}.txt", s["band"])
            wann = f":enable='gte(t,{float(s.get('band_ab', 0))})'"
            band = (f",drawbox=x=0:y=56:w=iw:h=116:color={s.get('band_farbe', '0xB00000')}@0.92:t=fill{wann},"
                    f"drawtext=fontfile={FETT}:textfile={t}:fontsize=64:fontcolor=white:x=(w-text_w)/2:y=56+28{wann}")
        ton = ["-i", str(quelle)] if hat_ton(quelle) and s.get("ton", True) else STILLE
        atempo = f",atempo={tempo}" if abs(tempo - 1) > 0.01 else ""
        ff("-i", str(quelle), *ton, "-filter_complex",
           f"[0:v]{BILDF},trim=start={ab}:end={ende:.3f},setpts=(PTS-STARTPTS)/{tempo}{band}[v];"
           f"[1:a]{TONF},atrim=start={ab}:end={ende:.3f},asetpts=PTS-STARTPTS{atempo},apad=whole_dur={d}[a]",
           "-map", "[v]", "-map", "[a]", "-t", str(d), *KODIEREN, ziel.name, cwd=self.arbeit)

    def teil_standbild(self, i: int, s: dict, ziel: Path) -> None:
        bild = self.bild_ref(s["standbild"])[0]
        d = float(s["dauer"])
        z0, z1 = s.get("zoom", [1.0, 1.1])
        n = int(d * FPS)
        vor = "scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160"
        if s.get("duester"):                      # verlassen: entsättigt, dunkler, kühler
            vor += ",eq=saturation=0.3:brightness=-0.14:contrast=1.08,colorbalance=bs=0.08:bm=0.05"
        if s.get("schild"):                       # Schild liegt auf dem Standbild und zoomt mit
            t = self.text_datei(f"schild_{i}.txt", s["schild"])
            x, y, w, h = s.get("schild_feld", [0.30, 0.50, 0.40, 0.14])
            vor += (f",drawbox=x=iw*{x}:y=ih*{y}:w=iw*{w}:h=ih*{h}:color=white@0.96:t=fill,"
                    f"drawbox=x=iw*{x}:y=ih*{y}:w=iw*{w}:h=ih*{h}:color=0xC00000:t=14,"
                    f"drawtext=fontfile={FETT}:textfile={t}:fontsize=h*{h}*0.52:fontcolor=0xC00000:"
                    f"x=w*{x}+(w*{w}-text_w)/2:y=h*{y}+(h*{h}-text_h)/2")
        zoom = (f"zoompan=z='{z0}+({z1}-{z0})*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:"
                f"s={B}x{H}:fps={FPS}")
        ff("-loop", "1", "-i", str(bild), *STILLE, "-filter_complex", f"[0:v]{vor},{zoom},setsar=1[v]",
           "-map", "[v]", "-map", "1:a", "-t", str(d), *KODIEREN, ziel.name, cwd=self.arbeit)

    def teil_rueck(self, i: int, s: dict, ziel: Path, bisher: list[Path]) -> None:
        d = float(s["dauer"])
        alles = self.arbeit / f"vor_{i}.mp4"
        eing = [x for p in bisher for x in ("-i", p.name)]
        ff(*eing, "-filter_complex", "".join(f"[{k}:v]" for k in range(len(bisher))) +
           f"concat=n={len(bisher)}:v=1:a=0[v]", "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", alles.name, cwd=self.arbeit)
        tempo = dauer(alles) / d
        ff("-i", alles.name, *STILLE, "-filter_complex",
           f"[0:v]reverse,setpts=PTS/{tempo:.4f},eq=saturation=0.55:contrast=1.1,noise=alls=24:allf=t,"
           f"fps={FPS},trim=duration={d}[v];[1:a]{TONF},atrim=duration={d},apad=whole_dur={d}[a]",
           "-map", "[v]", "-map", "[a]", "-t", str(d), *KODIEREN, ziel.name, cwd=self.arbeit)

    def teil_karte(self, i: int, s: dict, ziel: Path) -> None:
        d = float(s["dauer"])
        z1 = self.text_datei(f"karte_{i}_1.txt", s["karte"][0])
        z2 = self.text_datei(f"karte_{i}_2.txt", s["karte"][1] if len(s["karte"]) > 1 else "")
        ff("-f", "lavfi", "-i", f"color=c=black:s={B}x{H}:r={FPS}:d={d}", *STILLE, "-filter_complex",
           f"[0:v]drawtext=fontfile={FETT}:textfile={z1}:fontsize=150:fontcolor=white:x=(w-text_w)/2:y=h/2-170,"
           f"drawtext=fontfile={NORMAL}:textfile={z2}:fontsize=58:fontcolor=white:x=(w-text_w)/2:y=h/2+50,"
           f"fade=t=in:st=0:d=0.3,setsar=1[v]", "-map", "[v]", "-map", "1:a", "-t", str(d), *KODIEREN,
           ziel.name, cwd=self.arbeit)

    def schnitt(self) -> Path:
        teile: list[Path] = []
        for i, s in enumerate(self.spec["schnitt"]):
            ziel = self.arbeit / f"teil_{i:02d}.mp4"
            if "clip" in s:
                self.teil_clip(i, s, ziel)
            elif "standbild" in s:
                self.teil_standbild(i, s, ziel)
            elif "rueck" in s:
                self.teil_rueck(i, s, ziel, list(teile))
            elif "karte" in s:
                self.teil_karte(i, s, ziel)
            else:
                sys.exit(f"Schnitt {i}: unbekannte Art {list(s)}")
            teile.append(ziel)
        ziel = self.arbeit / f"spot_{self.sid}_{self.aufl}.mp4"
        eing = [x for p in teile for x in ("-i", p.name)]
        n = len(teile)
        graph = "".join(f"[{k}:v][{k}:a]" for k in range(n)) + f"concat=n={n}:v=1:a=1[v][a0]"
        # Tonspuren: Musik (von/bis in Sekunden) und Geräusche je Schnittteil ("geraeusch": Datei, startet mit dem Teil)
        ordner = Path(__file__).parent / "musik"
        spuren, start = [], 0.0
        for s in self.spec["schnitt"]:
            if s.get("geraeusch"):
                spuren.append((ordner / "geraeusche" / s["geraeusch"], start, start + float(s["dauer"]),
                               float(s.get("geraeusch_db", -8))))
            start += float(s["dauer"])
        for m in self.spec.get("musik", []):
            spuren.append((ordner / m["datei"], float(m.get("von", 0)), float(m.get("bis", start)), float(m.get("db", -16))))
        marken = ["[a0]"]
        for datei, von, bis, db in spuren:
            if not datei.exists():
                print(f"Hinweis: Tondatei fehlt, ausgelassen: {datei.name}")
                continue
            k = n + len(marken) - 1          # Nummer dieses Eingangs: nach den n Schnitt-Teilen
            eing += ["-stream_loop", "-1", "-i", str(datei)]
            lang = max(0.3, bis - von)
            graph += (f";[{k}:a]{TONF},atrim=duration={lang:.2f},volume={db}dB,afade=t=in:st=0:d=0.25,"
                      f"afade=t=out:st={max(0, lang - 0.6):.2f}:d=0.6,adelay={int(von * 1000)}:all=1[s{k}]")
            marken.append(f"[s{k}]")
        graph += (f";{''.join(marken)}amix=inputs={len(marken)}:duration=first:normalize=0,"
                  f"alimiter=limit=0.95,loudnorm=I=-15:TP=-1.5:LRA=11[a]")
        ff(*eing, "-filter_complex", graph,
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-maxrate", "12M",
           "-bufsize", "24M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
           str(ziel), cwd=self.arbeit)
        gesamt = dauer(ziel)
        bilder = 18
        ff("-i", str(ziel), "-vf", f"fps={bilder}/{gesamt:.2f},scale=640:360,tile=3x6", "-frames:v", "1", "-q:v", "3",
           str(ziel.with_name(ziel.stem + "_bogen.jpg")))
        print(f"fertig: {ziel.name}, {gesamt:.1f} s")
        return ziel


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("storyboard")
    p.add_argument("--aufloesung", default="480p", choices=tuple(FAKTOR))
    p.add_argument("--nur-bilder", action="store_true")
    p.add_argument("--probe", action="store_true")
    a = p.parse_args()
    text = os.environ.get("SPOT_SPEC", "").strip() or Path(a.storyboard).read_text(encoding="utf-8")
    spot = Spot(json.loads(text), a.aufloesung, a.probe)
    spot.bilder()
    if not a.nur_bilder:
        spot.clips()
        spot.schnitt()
    (spot.arbeit / "info.json").write_text(json.dumps({"id": spot.sid, "aufloesung": a.aufloesung,
                                                       "usd": round(spot.summe, 2), "probe": a.probe}))
    print(f"Kosten dieses Spots bisher {spot.summe:.2f} USD (Clips nach Listenpreis geschätzt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
