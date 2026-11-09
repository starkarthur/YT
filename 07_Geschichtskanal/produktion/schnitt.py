"""Automatischer Schnitt: Clips auf die Stimme legen, Untertitel Wort für Wort, Musik mit Ducking,
Lautheit -14 LUFS, 1080x1920. Erzeugt FFmpeg-Befehle und eine ASS-Untertiteldatei."""
from __future__ import annotations

from pathlib import Path

BEWEGUNG_FILTER = {  # für Standbilder (art = standbild): Kamerafahrt per zoompan
    "langsamer_zoom_rein": "zoompan=z='min(zoom+0.0010,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    "langsamer_zoom_raus": "zoompan=z='if(eq(on,0),1.15,max(zoom-0.0010,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    "schwenk_links": "zoompan=z=1.12:x='(iw-iw/zoom)*(1-on/{n})':y='ih/2-(ih/zoom/2)'",
    "schwenk_rechts": "zoompan=z=1.12:x='(iw-iw/zoom)*on/{n}':y='ih/2-(ih/zoom/2)'",
}


def zeiten_je_einstellung(plan: dict, woerter: list[dict]) -> list[tuple[float, float]]:
    """Ordnet die Wörter der Stimme den Einstellungen zu (nach Wortanzahl) und liefert (start, ende).
    Der Schnitt sitzt so immer am Satzende einer Einstellung."""
    zeiten, i = [], 0
    for n, e in enumerate(plan["einstellungen"]):
        k = len(e["text"].split())
        teil = woerter[i:i + k]
        if not teil:
            raise ValueError(f"Einstellung {n + 1}: keine Wortzeiten (Text und Stimme passen nicht)")
        start = 0.0 if n == 0 else zeiten[-1][1]
        naechstes = woerter[i + k]["start"] if i + k < len(woerter) else teil[-1]["ende"] + 0.6
        zeiten.append((round(start, 3), round(naechstes, 3)))
        i += k
    return zeiten


def _ass_zeit(s: float) -> str:
    h, rest = divmod(s, 3600)
    m, sek = divmod(rest, 60)
    return f"{int(h)}:{int(m):02d}:{sek:05.2f}"


def ass_untertitel(woerter: list[dict], konf: dict, betont: set[str] | None = None) -> str:
    """Gruppen von N Wörtern, das gerade gesprochene Wort hervorgehoben."""
    u = konf["untertitel"]
    betont = {b.lower() for b in (betont or set())}
    kopf = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
            f"Style: Haupt,{u['schrift']},{u['groesse']},{u['farbe']},&H00000000,&H64000000,-1,1,6,2,2,60,60,520\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Text\n")
    zeilen, n = [], u["woerter_pro_zeile"]
    for g in range(0, len(woerter), n):
        gruppe = woerter[g:g + n]
        for j, w in enumerate(gruppe):
            teile = []
            for k, x in enumerate(gruppe):
                t = x["wort"].replace("{", "").replace("}", "").replace("\\", "").upper()
                farbe = u["betonung"] if (k == j or x["wort"].strip(".,!?").lower() in betont) else u["farbe"]
                teile.append(f"{{\\c{farbe}}}{t}")
            ende = gruppe[j + 1]["start"] if j + 1 < len(gruppe) else w["ende"] + 0.15
            zeilen.append(f"Dialogue: 0,{_ass_zeit(w['start'])},{_ass_zeit(ende)},Haupt,{' '.join(teile)}")
    return kopf + "\n".join(zeilen) + "\n"


def befehle(plan: dict, zeiten: list[tuple[float, float]], clips: list[Path], stimme: Path,
            musik: Path | None, ass: Path, ziel: Path, konf: dict,
            geraeusche: list[Path | None] | None = None) -> list[list[str]]:
    f = konf["format"]
    b, h, fps = f["breite"], f["hoehe"], f["fps"]
    arbeit = ziel.parent
    out: list[list[str]] = []
    teile = []
    for n, ((s, e), clip, einst) in enumerate(zip(zeiten, clips, plan["einstellungen"]), 1):
        dauer = max(e - s, 1.0)
        norm = arbeit / f"teil_{n:02d}.mp4"
        basis = f"scale={b}:{h}:force_original_aspect_ratio=increase,crop={b}:{h},setsar=1"
        if einst.get("art") == "standbild":
            frames = int(dauer * fps)
            bew = BEWEGUNG_FILTER.get(einst.get("bewegung"), BEWEGUNG_FILTER["langsamer_zoom_rein"]).format(n=frames)
            vf = f"scale={b * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={b * 2}:{h * 2},{bew}:d={frames}:s={b}x{h}:fps={fps}"
            eingang = ["-loop", "1", "-i", str(clip)]
        else:
            vf = f"{basis},fps={fps},tpad=stop_mode=clone:stop_duration=5"
            eingang = ["-i", str(clip)]
        if einst.get("effekt") == "punch_zoom":
            vf += ",zoompan=z='if(lt(on,6),1.0+0.03*on,1.18)':d=1:s=%dx%d:fps=%d" % (b, h, fps)
        out.append(["ffmpeg", "-y", *eingang, "-t", f"{dauer:.3f}", "-vf", vf, "-an",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", str(norm)])
        teile.append(f"file '{norm.as_posix()}'")
    liste = arbeit / "teile.txt"
    out.append(["#schreibe", str(liste), "\n".join(teile) + "\n"])
    bild = arbeit / "bild.mp4"
    out.append(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(liste), "-c", "copy", str(bild)])
    ass_pfad = ass.as_posix().replace(":", "\\:")
    korn = int(konf.get("filmkorn", {}).get("staerke", 0))
    vf = (f"noise=alls={korn}:allf=t," if korn > 0 else "") + f"ass='{ass_pfad}'"  # Korn unter den Untertiteln
    eingaenge = ["-i", str(bild), "-i", str(stimme)]
    graph, mix = [], ["[1:a]"]
    if musik:
        m = konf["musik"]["lautstaerke_unter_stimme_db"]
        eingaenge += ["-stream_loop", "-1", "-i", str(musik)]
        graph.append(f"[2:a]volume={m}dB[mu];[mu][1:a]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]")
        mix.append("[duck]")
    g_db = konf.get("geraeusche", {}).get("lautstaerke_db", -14)
    for n, ((s, e), g) in enumerate(zip(zeiten, geraeusche or []), 1):
        if not g:
            continue
        idx = eingaenge.count("-i")  # Nummer der nächsten Eingabe
        dauer = max(e - s, 0.5)
        eingaenge += ["-i", str(g)]
        ms = int(s * 1000)
        graph.append(f"[{idx}:a]atrim=0:{dauer:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.15,"
                     f"afade=t=out:st={max(dauer - 0.4, 0):.3f}:d=0.4,volume={g_db}dB,adelay={ms}|{ms}[g{n}]")
        mix.append(f"[g{n}]")
    graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    out.append(["ffmpeg", "-y", *eingaenge, "-filter_complex", ";".join(graph), "-map", "0:v", "-map", "[a]",
                "-vf", vf, "-c:v", "libx264", "-crf", "18", "-maxrate", "12M", "-bufsize", "24M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-movflags", "+faststart", str(ziel)])
    return out
