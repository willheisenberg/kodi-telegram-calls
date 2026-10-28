# Teilprojekt 3: 1-zu-1-Videoanrufe im Vollbild

Stand: 2026-10-28

Baut auf Teilprojekt 2 auf (`2026-10-16-teilprojekt-2-sprachanrufe-addon-design.md`,
`../../ergebnisse-teilprojekt-2.md`). Was dort festgelegt ist, gilt weiter,
soweit hier nichts anderes steht.

## Ziel

Videoanrufe mit Telegram-Kontakten am Fernseher, in beide Richtungen: Man
sieht die Gegenseite im Vollbild und sich selbst klein in der Ecke, die
Gegenseite sieht einen über die Webcam C922. Bedienung weiter nur mit der
Fernbedienung. Sprachanrufe bleiben unverändert.

### Festgelegt

- Beide Richtungen: Video der Gegenseite im Vollbild, eigenes Bild klein
  unten rechts, eigene Kamera (C922) an die Gegenseite.
- Anrufen: OK auf einer Kachel oder einem Kontakt öffnet die Auswahl
  „Sprachanruf“ / „Videoanruf“.
- Eingehender Videoanruf: Knöpfe „Mit Video annehmen“, „Nur Ton annehmen“,
  „Ablehnen“.
- Im Videogespräch: Knöpfe „Stumm“, „Kamera an/aus“, „Auflegen“.
- Vorrang: wenig Verzögerung vor Bildqualität (Ziel 360p bis 720p,
  30 Bilder pro Sekunde, siehe Nachtrag).
- Weg zum Fernseher (Nachtrag 2026-10-28, ersetzt MPEG-TS über `udp://`):
  Bild (H.264) und Ton (L16) der Gegenseite als zwei RTP-Ströme, beschrieben
  durch eine SDP-Datei, die Kodis Player abspielt.

### Erfolgskriterien

1. Videoanruf in beide Richtungen: Gegenseite sieht und hört einen, man sieht
   und hört die Gegenseite im Vollbild, eigenes Bild in der Ecke.
2. Verzögerung von Bild und Ton im Gespräch nicht spürbar größer als bei
   Sprachanrufen (Kodi-Anteil Ziel unter 1 s); Bild und Ton lippensynchron.
3. Annehmen mit und ohne Video; Kamera im Gespräch aus- und wieder
   einschalten.
4. Schaltet die Gegenseite ihre Kamera aus, erscheint ihr Profilbild.
5. Kodi läuft stabil weiter, auch wenn Kamera, Encoder oder Anrufprozess
   ausfallen.
6. CPU-Last auf dem Pi 5 so, dass Kodi flüssig bleibt (Richtwert: Anrufprozess
   unter 150 % von 400 %).

## Bausteine

Neu im Anrufprozess (`worker/`):

| Baustein | Aufgabe |
|---|---|
| Kamera (`camera.py`) | liest die C922 per V4L2 in einem eigenen Thread, liefert I420-Bilder an ntgcalls (`Device.CAMERA`) und eine verkleinerte Kopie an den Bildmischer; an/aus |
| Bildmischer (`compositor.py`) | setzt das eigene Bild unten rechts in das Bild der Gegenseite; ohne Bild der Gegenseite deren Profilbild groß auf dunklem Grund |
| Medien-Taktgeber (`avpacer.py`) | wie `pacer.py`, für Ton und Bild: Ton alle 10 ms lückenlos (Stille bei Bedarf), Bilder im festen Takt (letztes Bild wiederholen) |
| Videoausgabe (`videosink.py`) | kodiert das Bild (H.264), sendet Bild und Ton als zwei RTP-Ströme (mit RTCP) an 127.0.0.1, schreibt die SDP-Datei; meldet Kodi `play_video`, sobald Daten fließen |

Geändert: `callmanager.py` (Videoanruf, Annehmen mit/ohne Video, Kamera
an/aus), `tgbackend.py` (Video-Streams, eingehende Videobilder, Kennung
„Videoanruf“ beim Klingeln), Add-on-Oberfläche (Auswahl, Klingeldialog,
Video-Bedienleiste).

Die Kodier-Bibliothek PyAV 18.1.0 (mit eingebautem FFmpeg und libx264) kommt
ins Bündel `vendor/` (Phase 0 bestätigt).

### Schnittstelle Add-on ↔ Anrufprozess (Änderungen)

Befehle: `call {id, video}`, `accept {video}`, neu `camera {an}`.
`video` ist ein Wahrheitswert; fehlt er, gilt `false` (Sprachanruf wie
bisher).

Ereignisse: `incoming {id, name, video}`, `connected {video}`, neu
`play_video {sdp_pfad}` (Kodi spielt die SDP-Datei des Videostroms;
`stop_kodi` beendet ihn wie bisher), neu `camera_state {an, verfuegbar}`; `status` bekommt zusätzlich
`kamera_ok`.

## Videoweg

```
C922 ──V4L2──▶ Kamera ──I420──▶ ntgcalls (CAMERA) ──▶ Telegram
                 └─ verkleinert ─┐
                                 ▼
Telegram ─▶ ntgcalls ─▶ Bild der Gegenseite ─▶ Bildmischer ─▶ Medien-Taktgeber ─▶ Videoausgabe ─RTP+SDP─▶ Kodi
        └─▶ Ton der Gegenseite ──────────────────────────────▶ Medien-Taktgeber ─┘
```

- Kodi spielt die SDP-Datei im Dateimodus (wie den Ton in Teilprojekt 2):
  Läuft es leer, hängt es danach 7–9 s hinterher. Der Medien-Taktgeber muss
  Bild und Ton deshalb lückenlos liefern (Stille, letztes Bild wiederholen).
- 30 Bilder pro Sekunde (der Fernseher läuft mit 60 Hz; 25 ruckeln sichtbar).
- Anfangsschub: Sobald Kodi den Videoport gebunden hat (der Anrufprozess
  sieht das in `/proc/net/udp`), gehen die ersten 50 Bilder im 10-ms-Takt
  raus (Zeitbasis 1/300 s; dasselbe Bild wiederholt, das kodiert billig),
  damit ffmpegs Bildraten-Schätzung schnell fertig ist; sonst spielt Kodi
  diese Zeit dauerhaft verzögert. Schlüsselbild mit SPS/PPS am Schubbeginn,
  danach kurzer Abstand der Schlüsselbilder (1 s).
- Kodi erst öffnen, wenn Daten fließen (sonst wartet es 30 s und zeigt
  „Wiedergabe fehlgeschlagen“). Erstes Bild nach dem Öffnen ist ein
  Schlüsselbild.
- RTCP der beiden RTP-Ströme hält Bild und Ton synchron (lippensynchron
  geprüft).
- Ton im Videogespräch geht nur über den Videostrom, nicht zusätzlich über
  den RTP-Tonweg. Die Echounterdrückung bekommt den Ton, den der
  Taktgeber ausgibt, als Referenz; ihre Verzögerung wird für den Videoweg
  in Phase 0 gemessen.
- Kodi zeigt das Video im Vollbild-Videofenster; die Bedienleiste ist ein
  Dialog des Add-ons darüber. Weil Kodi dabei Video spielt, schaltet keine
  Musik-Visualisierung (Party Video) dazwischen.

### Phase 0: Machbarkeitsmessung (vor allem anderen)

Erledigt am 2026-10-28; Ergebnis und Abweichungen (RTP statt MPEG-TS über
`udp://`, 30 statt 25 fps) im Nachtrag am Ende. Der folgende Text ist der
ursprüngliche Auftrag.

1. **Encoder:** Lässt sich eine Bibliothek mit Bild-/Ton-Encoder und
   MPEG-TS-Verpacker für aarch64 und Python 3.11 ins Bündel packen (Kandidat
   PyAV)? Welche Codecs sind dabei? Kandidaten: Bild MPEG-2 oder H.264 in
   Software, Ton MP2 oder PCM.
2. **Kodi im Live-Modus:** Verzögerung von Bild und Ton über `udp://`
   (Testbild und Stille, Kodis Wiedergabezeit per JSON-RPC wie in
   Teilprojekt 2), auch nach einer künstlichen Lücke.
3. **CPU-Last:** Kodieren 720p/25 fps plus Bildmischer plus Kamera auf dem
   Pi 5.
4. **Kamera an Telegram:** Kommt das C922-Bild über ntgcalls bei der
   Gegenseite an? Welche Auflösung und Bildrate sind sinnvoll (ein Anruf mit
   einem Freund)? Wie meldet Telegram einen eingehenden Videoanruf
   (`video`-Kennung) und eine ausgeschaltete Kamera der Gegenseite?

### Entscheidungsregeln

- Liegt der Kodi-Anteil im Live-Modus deutlich über 1 s oder lässt sich kein
  Encoder bündeln: anhalten, neu entscheiden, Nachtrag in dieser Spec.
- Ist 720p zu teuer (Erfolgskriterium 6), dann 540p oder 360p.
- Codec: der billigste, den Kodi auf dem Pi 5 flüssig abspielt und der die
  Verzögerung nicht erhöht (keine B-Frames, kurze GOP).

## Bildschirme und Bedienung

- **Auswahl beim Anrufen:** OK auf einer Kachel oder einem Kontakt öffnet
  „Sprachanruf“ / „Videoanruf“; Zurück schließt sie. Gruppen weiter
  ausgenommen.
- **Klingeldialog:** zeigt, ob Video- oder Sprachanruf. Videoanruf: „Mit
  Video annehmen“ (Fokus), „Nur Ton annehmen“, „Ablehnen“. Sprachanruf:
  „Annehmen“, „Ablehnen“ wie bisher. „Nur Ton annehmen“ führt das Gespräch
  als Sprachanruf über den bisherigen Tonweg; die Gegenseite sieht kein Bild.
- **Im Videogespräch:** Video der Gegenseite im Vollbild, eigenes Bild unten
  rechts. Darüber eine schmale Leiste mit Name, Dauer und den Knöpfen
  „Stumm“, „Kamera an/aus“, „Auflegen“ (Fokus auf „Auflegen“). Nach 5 s ohne
  Taste blendet sie sich aus; die nächste Taste holt sie zurück, ohne etwas
  auszulösen. Zurück und Stopp legen auf.
- **Ende:** Grund 3 s groß, dann zurück (wie bei Sprachanrufen).
- **Kamera aus:** keine Bilder mehr an Telegram, die Ecke verschwindet; die
  Gegenseite sieht das Profilbild (Verhalten der Telegram-Apps).
- Rundherum wie Teilprojekt 2: laufende Wiedergabe pausiert, Bildschirmschoner
  und Party Video aus, zweiter Anruf „besetzt“.

## Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| Kamera fehlt oder ist belegt | Videoanruf läuft ohne eigenes Bild, Hinweis „Kamera nicht verfügbar“ |
| Kamera fällt im Gespräch aus | Ecke verschwindet, Hinweis, Gespräch läuft weiter |
| Gegenseite schaltet ihre Kamera aus | ihr Profilbild groß |
| Encoder oder Videoausgabe fällt aus | Gespräch endet mit „Videoausgabe fehlgeschlagen“ |
| Anrufprozess stürzt ab | wie Teilprojekt 2: „Verbindung abgebrochen“ groß, Neustart |

## Tests

Ohne Kodi und ohne Telegram, wie bisher:

- Bildmischer: Ecke, Profilbild ohne Bild der Gegenseite, Kamera aus.
- Medien-Taktgeber: fester Takt für Ton und Bild, letztes Bild wiederholen,
  Lücken mit Stille, Stau begrenzt.
- CallManager: Videoanruf starten, annehmen mit und ohne Video, Kamera an/aus,
  Kamera nicht verfügbar, Ausfall der Videoausgabe, Auflegen während des
  Öffnens.
- AppState: Auswahl Sprache/Video, Klingeldialog mit drei Knöpfen,
  Bedienleiste ein- und ausblenden.
- Protokoll: neue Felder, Befehle und Ereignisse.

Abnahme am Gerät mit echten Gesprächen: Videoanruf hin und her, Annehmen mit
und ohne Video, Kamera an/aus, Gegenseite schaltet Kamera aus, Verzögerung
und Lippensynchronität schätzen, Absturz im Videogespräch.

## Nicht enthalten

- Umschalten zwischen Sprach- und Videoweg mitten im Gespräch: Schaltet die
  Gegenseite in einem Sprachanruf ihre Kamera ein, wird das nicht gezeigt.
- Gruppenanrufe (Teilprojekt 4).
- Bildschirm teilen, Kamerawahl, Bildeinstellungen am Fernseher.

## Nachtrag 2026-10-28: Ergebnis Phase 0 (Kodi-Weg)

Gemessen mit einem Piepton im Strom, aufgenommen vom Mikrofon der C922 neben
den Lautsprechern (Senden bis Ton im Raum, inklusive HDMI und Denon).
Kodis eigene Zeitangabe taugt bei MPEG-TS nicht (unbekannter Versatz).

| Weg | Verzögerung |
|---|---|
| Ton wie Teilprojekt 2 (RTP L16 + SDP) | 0,59 s |
| MPEG-TS (H.264 + MP2) über `udp://`, Live-Modus | 2,33 s |
| MPEG-TS nur Ton über `udp://` | ~1,7 s |
| dieselben Daten ohne Kodi empfangen | 0,05 s |
| RTP H.264 + RTP L16 + SDP | 1,63 s |
| dasselbe mit Anfangsschub 50 Bilder | 0,75–0,90 s |

- Kodis Live-Modus baut beim Start ein Polster auf und bremst nur, holt nie
  auf (Kodi 21, `VideoPlayer.cpp`). Damit verfehlt `udp://` das Ziel unter 1 s
  deutlich; nach der Entscheidungsregel neu entschieden: RTP + SDP.
- Preis: Dateimodus ohne Schutz vor Leerlauf, also Taktgeber für Bild und Ton
  Pflicht (wie beim Ton bewährt).
- Sichtprüfung am Fernseher: lippensynchron, keine Umschaltung von Fernseher
  oder Denon; 25 fps ruckeln an 60 Hz, 30 fps laufen flüssig.
- CPU bei 720p/30 fps (libx264 `ultrafast`, `zerolatency`, Testbild): Sender
  ~55 % eines Kerns, Kodi ~14 %.
- Nebenbefund: Kodis `Player.Open` lehnt manche neu angelegten Dateinamen mit
  „Invalid params“ ab (Ursache offen); die Videoausgabe prüft die Antwort.
- Anruftest mit einem Freund: Das C922-Bild kommt an; eingehend 1280x720 mit
  24–25 fps. Videokennung: `PhoneCallRequested.video` (True/False, beides
  geprüft). Schaltet die Gegenseite ihre Kamera aus, schickt Telegram kein
  Ereignis, es kommen nur keine Bilder; auch ohne Ausschalten kam einmal 2,2 s
  nichts. Also: Profilbild erst, wenn 3 s kein Bild kam.
- Die C922 lieferte im Anruf nur ~15 fps (Belichtung); Kameraquelle ist
  `v4l2-ctl` (MJPEG), weil PyAV keinen `v4l2`-Eingang hat.
- Details und Rohdaten: `docs/messtest-teilprojekt-3.md`.

### Offen für Plan 3b (Abschlussreview Phase 0)

- Verzögerung über den echten Öffnungsweg (`play_video` → `xbmc.Player`)
  mindestens fünfmal messen; die Werte aus Phase 0 sind Einzelläufe
  (0,75–0,96 s). Probieren: `a=framerate:30` und `sprop-parameter-sets` in
  der SDP-Datei, vielleicht wird der Anfangsschub damit unnötig.
- Mehr Verzögerung als im Sprachanruf ist akzeptiert, solange sie unter 1 s
  bleibt (Erfolgskriterium 2 in diesem Sinne).
- Ton und Bild in getrennten Threads des Medien-Taktgebers, damit der Ton nie
  auf den Encoder wartet. Reine Bildlücken (100 und 300 ms) messen; Ausfall
  erkennen (Kodi-Zeit läuft weg oder „stream stalled“) und Kodi dann mit
  neuem Schub wieder öffnen.
- Kodi öffnet den Strom nicht: Das Add-on meldet `onAVStarted`, einen
  Wiedergabefehler oder eine Zeitüberschreitung als Ereignis zurück; der
  Anrufprozess beendet dann mit „Videoausgabe fehlgeschlagen“. Beim
  Abspielen Videoangaben setzen (`getVideoInfoTag`).
- Lippensynchronität im Gespräch: Der Ton liegt bis 0,3 s in der
  Warteschlange, das Bild ist immer das neueste. Bild um die Füllung der
  Ton-Warteschlange verzögern; bei der Abnahme Klatschtest.
- Echo-Referenz im Videogespräch: lieber zu früh als zu spät
  (`worker/echo.py`). Startwert 0,7 s, im Gespräch per Kreuzkorrelation
  nachmessen.
- CPU früh mit echtem Kamerabild messen (Testbilder sind für libx264 billig);
  Bildmischer direkt in I420; 540p als Ausweg.
- Bildrate: Gegenseite liefert 24–25 fps, an Kodi gehen 30 fps; prüfen, ob
  das Auffüllen sichtbar ruckelt. Kodi meldet wegen des Schubs `videofps 100`;
  unbedenklich, solange „Bildwiederholrate anpassen“ aus ist (so eingestellt).
- C922 mit ~15 fps im Anruf: Ursache offen (Belichtung oder Last in der
  Probe); `v4l2-ctl` allein messen. Die 2,2-s-Pause beim Empfang kann
  ebenfalls lokal entstanden sein; die 3-s-Schwelle für „Kamera aus“ im
  echten Anrufprozess prüfen.
