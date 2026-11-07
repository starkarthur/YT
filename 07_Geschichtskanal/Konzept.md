# Geschichtskanal – Konzept

Stand: 07.11.2026, Fassung 2 · Chef-Agent · Ziel: **zuerst Reichweite**, Einnahmen später. **Alles läuft automatisch**, vom Thema bis zum Upload.
Arbeitstitel des Kanals: **„History Hooks“** (Vorschlag, Markenrecherche steht noch aus). Weitere Ideen: „Odd Old World“, „Footnotes of History“, „Yesterday's Secrets“.

## Format

| | Festlegung |
| --- | --- |
| Inhalt | wahre Geschichte und **historische Naturkatastrophen** |
| Sprache | **Englisch** (größte Reichweite) |
| Länge | 45–60 Sekunden, ca. 120–150 gesprochene Wörter |
| Takt | **1 Short pro Tag**, Upload automatisch |
| Plattformen | YouTube Shorts, TikTok, Instagram Reels, dieselbe 9:16-Datei |
| Zielgruppe | Erwachsene und Jugendliche ab 13 (kein Kinderinhalt) |
| Lange Videos | erst wenn die Shorts laufen |

## Aufbau eines Shorts

| Zeit | Teil | Regel |
| --- | --- | --- |
| 0–2 s | **Hook** | eine überraschende Behauptung, sofort, ohne Begrüßung |
| 2–10 s | Kontext | wer, wann, wo, in einem Satz |
| 10–45 s | Geschichte | 3–4 Wendungen, jede mit neuer Einstellung |
| 45–55 s | Pointe | die Auflösung oder das „und deshalb…“ |
| letzte Sekunde | Loop | der letzte Satz führt zurück in den Hook |

## Stil: filmische KI-Videos

- **Bild:** Pro Einstellung ein filmisches KI-Standbild (fester Stilsatz in `produktion/konfig.json`), daraus ein KI-Videoclip mit echter Bewegung. 2–3 ruhige Einstellungen pro Short dürfen Standbild mit Kamerafahrt sein (spart Kosten).
- **Personen der Geschichte** dürfen als **erkennbar nachgestellte Szene** gezeigt werden: filmischer Look, nie als echtes Foto oder Dokument ausgegeben. **Immer gekennzeichnet:** YouTube „veränderte oder synthetische Inhalte“, TikTok-KI-Label, Hinweis „dramatized with AI“ in der Beschreibung. Echte Originalfotos werden, wo vorhanden, mit Quelle bevorzugt.
- **Stimme:** eine feste, markante Erzählstimme (ElevenLabs Voice Design, keine Kopie einer echten Person).
- **Schnitt (automatisch):** Schnitte auf den Satzenden der Stimme, große Wort-für-Wort-Untertitel mit farbigen Schlüsselwörtern, kurze Punch-Zooms an Wendepunkten, Musik mit automatischem Absenken unter der Stimme, Lautheit −14 LUFS, 1080×1920.
- **Musik:** aus einer lizenzierten Bibliothek im Ordner `produktion/musik/`.

## Reihen

1. **„History's Greatest Cons“**: Betrüger, Hochstapler, Schwindel
2. **„Accidents That Changed Everything“**: Zufälle, Erfindungen, Pannen
3. **„Wait, That Really Happened?“**: kuriose Ereignisse
4. **„Time Is Weird“**: verblüffende Zeitvergleiche
5. **„Nature's Fury“**: die gewaltigsten Naturkatastrophen der Geschichte, wie sie abliefen, wie groß sie wirklich waren und was die Menschen daraus gelernt haben (Vulkane, Tsunamis, Erdbeben, Stürme, Fluten, Meteoriten)

## Rote Linien

- Jede Tatsachenbehauptung braucht mindestens eine verlässliche Quelle, eine davon nicht Wikipedia. Strittiges wird als strittig gesagt oder gestrichen.
- Keine NS-Symbole, kein Völkermord, keine drastische Gewalt, keine aktuelle Politik, keine Verschwörungstheorien als Fakten.
- **Naturkatastrophen:** Respekt vor den Opfern. Keine Leichen, keine verletzten Menschen im Bild, kein Spott, keine reißerischen Opferzahlen ohne Quelle. Die Gewalt der Natur steht im Mittelpunkt, nicht das Leid Einzelner. Ereignisse der **letzten 10 Jahre nur ausnahmsweise** und nie während einer laufenden Katastrophe (Werbebeschränkung, Respekt). Keine Panikmache vor künftigen Katastrophen.
- Keine nachgemachten Stimmen echter Personen. KI-Darstellungen echter Personen nur gekennzeichnet und erkennbar nachgestellt.
- Abwechslung: höchstens 2 Shorts derselben Reihe hintereinander (Schutz vor „Massenware“).

## Automatischer Ablauf

```
Wochenstapel (Chef-Agent startet):  Autor → 7 Skripte + Produktionspläne
                                    Prüfer → Faktenprüfung (Freigabe an den Hash des Plans gebunden)
                                    Kanal  → Titel, Texte, Hashtags
Täglich (Cloud-Worker, automatisch): nächster freigegebener Short → Stimme → Bilder → Videos → Schnitt
                                    → Qualitätsprüfung → Upload YouTube + TikTok + Instagram
Wöchentlich:                        Kennzahlen → Kanal-Agent → Erkenntnisse → nächster Stapel
```

**Freigabe-Stufen:**
1. **Testphase:** Die ersten Uploads gibt der Nutzer einzeln frei (Klick in GitHub).
2. **Automatik:** Sobald der Nutzer es ausdrücklich einschaltet (Pflicht-Klick in der GitHub-Umgebung entfernen), läuft der Upload ohne Einzelfreigabe. Sicherungen bleiben: Prüferfreigabe mit Hash, Qualitätsprüfung, Budgetgrenze, höchstens 1 Upload pro Tag und Plattform, keine Doppel-Uploads. Abschalten geht jederzeit über denselben Schalter.

## Kosten (Schätzung, Stufe „sehr gut“)

Ca. **$12–15 pro Short** (10 Einstellungen, 7–8 davon als KI-Video mit Kling, 2 Versuche, Stimme), bei 30 Shorts **ca. $380–450 im Monat** plus ElevenLabs ca. $22. Budgetgrenze in der Pipeline: $20 pro Short, $500 pro Monat.

## Freigaben

- Konten (YouTube, TikTok, Instagram, fal.ai, ElevenLabs, GitHub-Repo für den Worker) legt der Nutzer selbst an.
- Neue kostenpflichtige Dienste nur nach Freigabe.
- Der Automatik-Modus gilt erst, wenn der Nutzer ihn selbst einschaltet.
