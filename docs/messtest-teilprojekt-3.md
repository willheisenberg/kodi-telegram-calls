# Messtest Teilprojekt 3: Video (Phase 0)

Stand: 2026-10-28. Gerät: Raspberry Pi 5, LibreELEC 12.2.1, Kodi 21.3, HDMI
1080p60 an einen Denon-AVR, Webcam C922. Gegenseite: ein Freund mit der
Telegram-App. Plan: `superpowers/plans/2026-10-28-teilprojekt-3a-machbarkeit-video.md`,
Spec: `superpowers/specs/2026-10-28-teilprojekt-3-videoanrufe-design.md`
(Nachtrag „Ergebnis Phase 0“).

Werkzeuge (`tools/messtest/`): `av_probe.py` (Fähigkeiten des PyAV-Bündels),
`videolag.py` (Kodis Zeitangabe gegen gesendete Dauer), `beeplag.py` (Piepton
senden, mit dem C922-Mikrofon im Raum wieder aufnehmen), `videocall_probe.py`
(echter Videoanruf mit Kamera, Empfangsstatistik). Bündel:
`tools/build-probe.sh`.

## Ergebnis

| Frage | Ergebnis | Entscheidung für Plan 3b |
|---|---|---|
| Encoder im Bündel | PyAV 18.1.0 (FFmpeg avcodec 62.28), aarch64/cp311, 151 MB mit numpy; libx264, mpeg2video, h264_v4l2m2m, mp2, aac, libopus, mpegts, rtp; es fehlen der `v4l2`-Eingang, libopenh264, s302m | PyAV ins Bündel; Bild libx264 (`ultrafast`, `zerolatency`, keine B-Frames) |
| Weg zu Kodi | Piep→Mikrofon: Ton-RTP wie TP2 0,59 s; MPEG-TS über `udp://` (live) 2,33 s; RTP H.264 + RTP L16 + SDP 1,63 s, mit Anfangsschub 0,75–0,96 s (Einzelläufe) | RTP H.264 + RTP L16 + SDP-Datei, Anfangsschub 50 Bilder (Spec-Nachtrag, vom Nutzer bestätigt) |
| Kodi nach Lücke | `udp://` live: kein Sprung (Kodi bremst nur); SDP (Dateimodus): +7–9 s | Medien-Taktgeber für Bild und Ton Pflicht |
| Bildrate am Fernseher | 25 fps ruckeln an 60 Hz sichtbar, 30 fps flüssig (Sichtprüfung); Bild und Ton lippensynchron; keine Umschaltung von TV/Denon | 30 fps an Kodi, Zeitbasis 1/300 s |
| CPU | Kodieren 720p (Testbild): 42 % eines Kerns bei 25 fps, ~55 % bei 30 fps samt Senden; Kodi 11–20 %; Videoanruf-Probe (Kamera dekodieren + ntgcalls) 79 % | 720p bleibt; Gesamtlast im Anruf in 3b messen (Richtwert 150 %) |
| Kamera an Gegenseite | Bild kommt an (vom Freund bestätigt); in der Probe nur ~15 fps (902 Bilder in 60 s), allein ~21 fps | Kameraquelle `v4l2-ctl --stream-mmap --stream-to=-` (MJPEG), mit PyAV dekodieren; Ursache der 15 fps offen (Belichtung oder Last in der Probe), in 3b prüfen |
| Eingehendes Video | 1280x720, 24–25 fps; einmal 2,2 s Pause ohne Zutun | Bildmischer und Taktgeber halten das letzte Bild; Profilbild erst nach längerer Pause |
| Videokennung | `PhoneCallRequested.video` = True bei Videoanruf, False bei Sprachanruf (beides geprüft) | Klingeldialog wertet dieses Feld aus |
| Kamera der Gegenseite aus | Bild-Pause 13,3 s (Freund schaltete ~10 s aus); Telegram schickt kein eigenes Ereignis | „Kamera aus“ = keine Bilder seit 3 s (2,2 s kamen auch ohne Ausschalten vor) |
| Startfehler | stummes `udp://`: Kodi wartet 30 s, dann „Wiedergabe fehlgeschlagen“; MP2T-in-RTP-SDP ohne Daten: Kodi bricht sofort ab | Kodi erst öffnen, wenn Daten fließen; erstes Bild ein Schlüsselbild |
| Wert für die Echounterdrückung | Videoweg Piep→Raum 0,75–0,96 s (Tonweg 0,59 s), Messung über `aplay -C`, nicht über den Mikrofonweg des Anrufprozesses | Referenz lieber zu früh als zu spät (`worker/echo.py`): Startwert 0,7 s, im Gespräch per Kreuzkorrelation nachmessen |

## Wie gemessen

**Verzögerung.** Kodis Zeitangabe (`Player.GetProperties time`) hat bei
MPEG-TS einen unbekannten Versatz: Sie war bei „nur Ton“ negativ und blieb
beim Senderstopp sofort stehen. Deshalb misst `beeplag.py` Ende zu Ende: alle
4 s ein 0,2-s-Piepton (1 kHz) im Strom, Aufnahme mit dem C922-Mikrofon
(`aplay -C`, ALSA direkt, nicht PulseAudio), Erkennung per Goertzel in
5-ms-Blöcken. Die Messung enthält HDMI, Denon und den Schallweg (~50 cm)
sowie 10–20 ms Aufnahmeverzögerung. Innerhalb eines Laufs schwankten die
Werte um höchstens 0,01 s, zwischen Läufen mit gleicher Einstellung um bis zu
0,15 s (der Schub beginnt nach der Antwort auf `Player.Open`; wie viele
Schub-Bilder Kodi wirklich erreichen, hängt davon ab, wann ffmpeg den Port
bindet). In den ausgewerteten Läufen wurden alle Pieptöne gehört, auch der
erste nach 4 s; die Zuordnung ist damit eindeutig. Je Einstellung gibt es nur
einen Lauf (für 50 Bilder drei).

**Warum `udp://` langsamer ist.** Ohne Kodi empfangen kommt der Strom nach
0,05 s an; der Rest entsteht in Kodi. Im Live-Modus baut Kodi beim Start ein
Polster auf, bremst bei leerer Ton-Warteschlange um 5 % und holt nie auf
(`VideoPlayer.cpp`, Kodi 21).

**Warum der Anfangsschub hilft.** Bei einer SDP-Datei liest ffmpeg erst
Stream-Informationen ein und schätzt dabei die Bildrate aus etwa 20 Bildern.
Alles, was in dieser Zeit ankommt, spielt Kodi danach verzögert ab. Kommen die
ersten Bilder im 10-ms-Takt, ist die Schätzung schneller fertig:

| Anfangsschub (Bilder im 10-ms-Takt) | Piep→Raum |
|---|---|
| 0 | 1,63 s |
| 20 | 1,38 s |
| 50 | 0,90 s / 0,75 s (25 fps) / 0,83 s (30 fps) |
| 80 | 0,96 s |
| 120 | 0,81 s |

Ab etwa 50 Bildern kein deutlicher Gewinn mehr (Streuung beachten). Kodi
meldet danach `videofps 100`; das hat am Bild nichts erkennbar verändert
(„Bildwiederholrate anpassen“ ist in Kodi aus).

## Rohdaten

### av_probe.py (Task 1)

```
[OK] PyAV: 18.1.0, FFmpeg (62, 28, 102)
[OK] Muxer mpegts
[FEHLT] Eingang v4l2
[OK] Encoder mpeg2video
[OK] Encoder libx264
[FEHLT] Encoder libopenh264
[OK] Encoder h264_v4l2m2m
[OK] Encoder mjpeg
[OK] Encoder mp2
[OK] Encoder aac
[OK] Encoder libopus
[FEHLT] Encoder s302m
[OK] Kodieren mpeg2video 1280x720: 122 fps möglich, CPU 35 % eines Kerns bei 25 fps
[OK] Kodieren mpeg2video 960x540: 193 fps möglich, CPU 21 % eines Kerns bei 25 fps
[OK] Kodieren mpeg2video 640x360: 355 fps möglich, CPU 10 % eines Kerns bei 25 fps
[OK] Kodieren libx264 1280x720: 104 fps möglich, CPU 42 % eines Kerns bei 25 fps
[OK] Kodieren libx264 960x540: 168 fps möglich, CPU 25 % eines Kerns bei 25 fps
[OK] Kodieren libx264 640x360: 280 fps möglich, CPU 13 % eines Kerns bei 25 fps
```

(Die mjpeg-Zeilen scheiterten an den Testparametern `g`/`bf` und sind ohne
Belang.)

### videolag.py (Kodis Zeitangabe, nur als Rohwert)

| Lauf | vor der Lücke | nach 1,5-s-Lücke | „stream stalled“ |
|---|---|---|---|
| `udp://` mpeg2video 720p | 2,0–2,2 s | 0,5 → 1,8 s | ja |
| `udp://` libx264 720p | 2,4–2,5 s | 0,8 → 1,8 s | nein |
| SDP (rtp_mpegts) libx264 720p | 2,4–2,6 s | 9,0 s | ja |
| `udp://` libx264, Schlüsselbild alle 5 Bilder | 2,2–2,4 s | 1,65 s | – |
| `udp://` nur mp2 | 1,5–1,9 s | – | – |

### beeplag.py (Piep→Mikrofon, Median über 7–9 Pieptöne)

```
l16  (RTP L16 + SDP, Tonweg TP2)          0.59 s
udp  (MPEG-TS libx264 + mp2, live)        2.33 s
udp  (MPEG-TS nur mp2, live)              ~1.7 s (Spitzen streuen 1.66–1.91)
rtp  (RTP H.264 + RTP L16 + SDP)          1.63 s
rtp  --burst 20                           1.38 s
rtp  --burst 50                           0.90 s, 0.75 s
rtp  --burst 80                           0.96 s
rtp  --burst 120                          0.81 s
rtp  --burst 50 --fps 30                  0.83 s
Eigenempfang ohne Kodi (udp, PyAV)        0.007–0.054 s
```

### videocall_probe.py (Task 3, IDs entfernt)

```
Box → Freund, Video, 720p, 60 s
  Telegram PhoneCallWaiting video=True / PhoneCallAccepted video=True
  Kamera: C922, 902 Bilder gelesen
  Eingehend: 1447 Bilder, Größen [(1280, 720)], 24.1 fps, Pausen >1 s: [(16.7, 2.2)]
  CPU: Probe 79 % eines Kerns, Kodi 11 %

Freund → Box, Sprachanruf
  Telegram PhoneCallRequested video=False
  Eingehend: 0 Bilder

Freund → Box, Videoanruf, 45 s
  Telegram PhoneCallRequested video=True
  Eingehend: 1122 Bilder, Größen [(1280, 720)], 24.9 fps, Pausen >1 s: []

Box → Freund, Video, Freund schaltet Kamera ~10 s aus
  Eingehend: 1164 Bilder, Größen [(1280, 720)], 19.4 fps, Pausen >1 s: [(25.4, 13.3)]
  kein zusätzliches Telegram-Ereignis
```

Der Ton war in allen Probe-Anrufen absichtlich stumm (die Probe sendet
Stille und spielt nichts ab).

## Nebenbefunde

- Kodis `Player.Open` per JSON-RPC lehnt manche neu angelegten Dateinamen mit
  „Invalid params“ ab (`audio.sdp`, `beeplag.sdp`), andere nicht (`a2.sdp`,
  `tonprobe.sdp`). Ursache offen. Das Add-on öffnet über `xbmc.Player`, die
  Videoausgabe soll das Ergebnis trotzdem prüfen.
- Ein MPEG-TS-in-RTP-Strom (`rtp_mpegts`) über eine SDP-Datei öffnet Kodi nur,
  wenn schon Pakete ankommen. Für den gewählten Weg (H.264 und L16 getrennt)
  ohne Belang.
- Im Sprachanruf schickte die Probe trotzdem Kamerabilder. Ob die Gegenseite
  sie sah, ist nicht geprüft; „Nur Ton“ in 3b schickt keine Kamera.
