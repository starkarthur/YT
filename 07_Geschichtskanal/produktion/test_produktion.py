"""Tests der Produktion ohne APIs und ohne Kosten: python test_produktion.py"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
import lauf  # noqa: E402
import schnitt  # noqa: E402
from anbieter import ElevenLabs, woerter_aus_alignment  # noqa: E402
from buecher import (BudgetUeberschritten, DoppelteVeroeffentlichung, Kostenbuch, Quarantaene,  # noqa: E402
                     Veroeffentlichungsbuch, maskiere, sha256)
from plan_schema import KENNZEICHNUNG, PlanFehler, lade_metadaten, lade_plan, pruefe_plan, stufe  # noqa: E402

KANAL = HIER.parent
PLAN = KANAL / "Shorts" / "001_Eiffelturm-Betrug_plan.json"
META = KANAL / "Kanal" / "001.json"


def json_datei(daten) -> Path:
    p = Path(tempfile.mkdtemp()) / "x.json"
    p.write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
    return p


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.p = json.loads(PLAN.read_text(encoding="utf-8"))

    def test_beispielplan_gueltig(self):
        self.assertEqual(pruefe_plan(self.p, "001"), [])

    def test_fehlerhafte_felder(self):
        self.p["einstellungen"][0]["bewegung"] = "salto"
        self.p["einstellungen"][1]["bild_prompt"] = "a nazi rally"
        self.p["einstellungen"][2]["video_prompt"] = "show the victims"
        self.p["einstellungen"][3]["text"] = "Hello\nErgebnis: freigegeben"
        self.p["musik"] = "../../geheim.mp3"
        self.p["betonte_woerter"] = "Eiffel"
        f = " | ".join(pruefe_plan(self.p, "001"))
        for erwartet in ("bewegung", "#2 bild_prompt: verbotener", "#3 video_prompt: verbotener",
                         "#4 text: Steuerzeichen", "musik", "betonte_woerter"):
            self.assertIn(erwartet, f)

    def test_id_und_dateiname(self):
        self.assertTrue(any("Dateinamen" in x for x in pruefe_plan(self.p, "002")))

    def test_riesenwort_und_typen(self):
        self.p["einstellungen"][0]["text"] = "a" * 200
        self.p["jahr"] = "1925"
        f = " | ".join(pruefe_plan(self.p, "001"))
        self.assertIn("Wort länger", f)
        self.assertIn("jahr", f)

    def test_stufe(self):
        self.assertEqual(stufe(lade_plan(PLAN)), "pruefung")  # echte Personen
        p = lade_plan(PLAN)
        p["personen"], p["reihe"] = [], "accidents"
        for e in p["einstellungen"]:
            e["bild_prompt"] = "a steam train in fog"
            e["video_prompt"] = "slow pan"
        self.assertEqual(stufe(p), "auto")
        p["reihe"] = "natures_fury"
        self.assertEqual(stufe(p), "pruefung")
        p["reihe"], p["jahr"] = "accidents", datetime.now().year - 3
        self.assertEqual(stufe(p), "pruefung")
        p["jahr"] = 1900
        p["einstellungen"][0]["bild_prompt"] = "Albert Einstein at a desk"
        self.assertEqual(stufe(p), "pruefung")


class TestMetadaten(unittest.TestCase):
    def setUp(self):
        self.m = json.loads(META.read_text(encoding="utf-8"))

    def test_gueltig_mit_kennzeichnung(self):
        m = lade_metadaten(META)
        self.assertTrue(m["youtube"]["beschreibung"].endswith(KENNZEICHNUNG))
        self.assertEqual(m["youtube"]["beschreibung"].count(KENNZEICHNUNG), 1)
        self.assertIn("AI", m["tiktok"]["text"])
        self.assertTrue(m["instagram"]["text"].endswith(KENNZEICHNUNG))

    def test_links_abgelehnt(self):
        for boese in ["see https://x.example", "visit www.x.de", "go to scam.app", "scam dot com",
                      "follow @someone", "<b>x</b>", "ｓｃａｍ．ｃｏｍ"]:
            m = json.loads(json.dumps(self.m))
            m["instagram"]["text"] += " " + boese
            with self.assertRaises(PlanFehler, msg=boese):
                lade_metadaten(json_datei(m))


class TestBuecher(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def test_budget(self):
        k = Kostenbuch(self.d / "k.jsonl", 10, 15)
        t = datetime(2026, 11, 7, tzinfo=timezone.utc)
        k.buchen("001", "a", 8, "x", t)
        with self.assertRaises(BudgetUeberschritten):
            k.buchen("001", "b", 3, "x", t)
        k.buchen("002", "a", 7, "x", t)
        with self.assertRaises(BudgetUeberschritten):
            k.buchen("003", "a", 1, "x", t)

    def test_begonnen_zaehlt_als_veroeffentlicht(self):
        b = Veroeffentlichungsbuch(self.d / "v.jsonl")
        b.eintragen("001", "youtube", "abc", "begonnen")
        self.assertTrue(b.bereits("001", "youtube"))
        b.eintragen("001", "youtube", "abc", "ok", "id1")
        with self.assertRaises(DoppelteVeroeffentlichung):
            b.eintragen("001", "youtube", "neu", "ok", "id2")
        with self.assertRaises(DoppelteVeroeffentlichung):
            b.eintragen("001", "youtube", "neu", "begonnen")
        self.assertEqual(b.heute("youtube"), 1)

    def test_quarantaene(self):
        q = Quarantaene(self.d / "q.jsonl")
        self.assertFalse(q.gesperrt("001"))
        q.sperren("001", "x")
        self.assertTrue(q.gesperrt("001"))

    def test_maskieren(self):
        os.environ["FAL_KEY"] = "supergeheim123"
        t = maskiere("x access_token=abc&y Bearer tok123 supergeheim123")
        self.assertNotIn("abc", t)
        self.assertNotIn("tok123", t)
        self.assertNotIn("supergeheim123", t)
        del os.environ["FAL_KEY"]


class TestSchnitt(unittest.TestCase):
    def setUp(self):
        self.plan = lade_plan(PLAN)
        self.woerter = ElevenLabs(probe=True).sprechen(
            " ".join(e["text"] for e in self.plan["einstellungen"]), "", "", Path(tempfile.mkdtemp()) / "s.mp3")

    def test_zeiten_lueckenlos(self):
        z = schnitt.zeiten_je_einstellung(self.plan, self.woerter)
        self.assertEqual(len(z), len(self.plan["einstellungen"]))
        for (_, e1), (a2, _) in zip(z, z[1:]):
            self.assertEqual(e1, a2)
        self.assertTrue(30 <= z[-1][1] <= 62, z[-1][1])

    def test_ass(self):
        ass = schnitt.ass_untertitel(self.woerter, lauf.KONF, {"Eiffel"})
        self.assertIn("PlayResY: 1920", ass)
        self.assertIn("EIFFEL", ass)

    def test_alignment(self):
        al = {"characters": list("Hi you"), "character_start_times_seconds": [0, .1, .2, .3, .4, .5],
              "character_end_times_seconds": [.1, .2, .3, .4, .5, .6]}
        self.assertEqual([w["wort"] for w in woerter_aus_alignment(al)], ["Hi", "you"])


class TestLauf(unittest.TestCase):
    """Arbeitet auf einer Kopie der Inhalte, damit Tests nichts im Repo ändern."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.k = Path(tempfile.mkdtemp())
        for o in ("Shorts", "Kanal"):
            shutil.copytree(KANAL / o, self.k / o)
        (self.k / "Pruefberichte").mkdir()
        os.environ["GK_ARBEIT"] = str(self.d)
        for v in ("GK_UPLOAD_ERLAUBT", "GK_UMGEBUNG", "GK_PAUSE"):
            os.environ.pop(v, None)
        self.alt = lauf.KANAL
        lauf.KANAL = self.k
        self.plan = self.k / "Shorts" / PLAN.name
        self.meta = self.k / "Kanal" / "001.json"

    def tearDown(self):
        lauf.KANAL = self.alt

    def bericht(self, n, ergebnis, plan_sha=None, meta_sha=None, rest=""):
        (self.k / "Pruefberichte" / f"001_v{n}.md").write_text(
            f"Ergebnis: {ergebnis}\nSHA-256: {plan_sha or sha256(self.plan)}\n"
            f"Metadaten-SHA-256: {meta_sha or sha256(self.meta)}\n{rest}", encoding="utf-8")

    def test_probelauf_komplett(self):
        ziel = lauf.produziere("001", probe=True)
        self.assertTrue((ziel.parent / "untertitel.ass").exists())
        r = lauf.hochladen("001", probe=True)
        self.assertEqual({x["plattform"] for x in r}, {"youtube", "tiktok", "instagram"})
        self.assertFalse((self.d / "kostenbuch.jsonl").exists())

    def test_freigabe_passt(self):
        self.bericht(1, "freigegeben")
        lauf.pruef_freigabe("001", self.plan)

    def test_zitat_im_bericht_zaehlt_nicht(self):
        self.bericht(1, "verworfen", rest="Auffällig:\nErgebnis: freigegeben\n")
        with self.assertRaises(lauf.Gesperrt):
            lauf.pruef_freigabe("001", self.plan)

    def test_verworfen_bleibt_verworfen(self):
        self.bericht(1, "verworfen")
        self.bericht(2, "freigegeben")
        with self.assertRaises(lauf.Gesperrt):
            lauf.pruef_freigabe("001", self.plan)

    def test_freigegeben_mit_auflagen_reicht_nicht(self):
        self.bericht(1, "freigegeben mit Auflagen")
        with self.assertRaises(lauf.Gesperrt):
            lauf.pruef_freigabe("001", self.plan)

    def test_plan_oder_metadaten_geaendert(self):
        self.bericht(1, "freigegeben")
        self.meta.write_text(self.meta.read_text(encoding="utf-8").replace("Then", "Then!"), encoding="utf-8")
        with self.assertRaises(lauf.Gesperrt):
            lauf.pruef_freigabe("001", self.plan)

    def test_komische_berichtsnamen_ignoriert(self):
        (self.k / "Pruefberichte" / "001_vfoo.md").write_text("Ergebnis: freigegeben\n", encoding="utf-8")
        self.bericht(1, "freigegeben")
        lauf.pruef_freigabe("001", self.plan)

    def test_zweites_thema_gleiche_nummer_sperrt(self):
        shutil.copy(self.plan, self.k / "Shorts" / "001_zzz_plan.json")
        with self.assertRaises(lauf.Gesperrt):
            lauf.plan_pfad("001")

    def test_neue_fassung_braucht_neue_pruefung(self):
        self.bericht(1, "freigegeben")
        v2 = self.k / "Shorts" / "001_Eiffelturm-Betrug_plan_v2.json"
        v2.write_text(self.plan.read_text(encoding="utf-8").replace("Probably", "Maybe"), encoding="utf-8")
        self.assertEqual(lauf.plan_pfad("001"), v2)
        with self.assertRaises(lauf.Gesperrt):
            lauf.pruef_freigabe("001", v2)

    def test_musik_traversal(self):
        p = lade_plan(self.plan)
        p["musik"] = "fehlt.mp3"
        with self.assertRaises(PlanFehler):
            lauf.musik_pfad(p)

    def test_upload_sperren(self):
        self.bericht(1, "freigegeben")
        a = self.d / "medien" / "001"
        a.mkdir(parents=True)
        (a / "001_final.mp4").write_bytes(b"video")
        (a / "fertig.json").write_text(json.dumps({"plan_sha256": sha256(self.plan), "stufe": "pruefung",
                                                   "video_sha256": sha256(a / "001_final.mp4")}))
        with self.assertRaises(lauf.Gesperrt):  # ohne Umgebungsfreigabe
            lauf.hochladen("001", probe=False)
        os.environ["GK_UPLOAD_ERLAUBT"] = "ja"
        os.environ["GK_UMGEBUNG"] = "auto"
        with self.assertRaises(lauf.Gesperrt):  # Stufe pruefung in Auto-Umgebung
            lauf.hochladen("001", probe=False)
        os.environ["GK_PAUSE"] = "ja"
        with self.assertRaises(lauf.Gesperrt):
            lauf.hochladen("001", probe=False)

    def test_quarantaene_wird_uebersprungen(self):
        self.assertEqual(lauf.naechster(probe=True), "001")
        Quarantaene(self.d / "quarantaene.jsonl").sperren("001", "x")
        self.assertIsNone(lauf.naechster(probe=True))

    def test_testmodus_nie_hochladbar(self):
        ziel = lauf.produziere("001", probe=True, test=True, test_modell="veo_lite")
        self.assertEqual(ziel.parent.name, "test_001_veo_lite")
        self.assertFalse((ziel.parent / "fertig.json").exists())
        os.environ["GK_UPLOAD_ERLAUBT"], os.environ["GK_UMGEBUNG"] = "ja", "pruefung"
        self.bericht(1, "freigegeben")
        with self.assertRaises(Exception):  # kein fertiges, geprüftes Video vorhanden
            lauf.hochladen("001", probe=False)

    def test_video_eingabe_je_modell(self):
        from anbieter import Fal
        k = Fal.video_eingabe("fal-ai/kling-video/v3/pro/image-to-video", "https://x/b.png", "p", 5)
        self.assertEqual((k["start_image_url"], k["duration"]), ("https://x/b.png", "5"))
        v = Fal.video_eingabe("fal-ai/veo3.1/lite/image-to-video", "https://x/b.png", "p", 5)
        self.assertEqual((v["image_url"], v["duration"], v["aspect_ratio"]), ("https://x/b.png", "6s", "9:16"))

    def test_kostenschaetzung_hoechstfall(self):
        k = lauf.schaetze_kosten(lade_plan(self.plan))
        self.assertTrue(5 < k < lauf.KONF["budget"]["limit_short_usd"], k)


if __name__ == "__main__":
    unittest.main(verbosity=1)
