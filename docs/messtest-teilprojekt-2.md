# Messtest Teilprojekt 2

Stand: 2026-10-16. Gerät wie in Teilprojekt 1 (Pi 5, LibreELEC 12.2, Kodi 21,
HDMI an Denon-AVR, Webcam C922). Gemessen per SSH ohne Nutzer im Raum;
Tastendrücke in Kodi per JSON-RPC (`Input.Down`/`Input.Up`), die lösen
dieselben Bediengeräusche aus wie die Fernbedienung.

| Messung | Ergebnis |
|---|---|
| Bündel lädt (import_check) | OK: Python 3.11, ntgcalls 3.0.3, Telethon 1.45.0, numpy 2.4.6, LiveKit lädt |
| HDMI frei nach letztem Ton | 70 s (60 s laufend, 10 s vorbereitet, dann `closed`) |
| Verzögerung direkt (ALSA, `hdmi:CARD=vc4hdmi0,DEV=0`) | Median 85 ms (Läufe −75, 91, 85 ms; Startzeit der Aufnahme schwankt um etwa ±0,15 s) |
| Verzögerung über Kodi (VideoPlayer, SDP) | etwa 450 ms nach dem Einschwingen (Läufe 450, 385 ms; im Dauerlauf nach 30 und 60 s 448 und 446 ms); erste Sekunden unsicher |
| Kodi bei Bediengeräusch während direkter Ausgabe | Kodi kann den Ausgang nicht öffnen („no sink was returned“), läuft weiter und antwortet. Danach bleiben die Bediengeräusche stumm, bis Kodi wieder etwas abspielt; dann ist alles normal (geprüft mit 1 s Stille-WAV, danach Bediengeräusch wieder `RUNNING`). |
| Externe Frames senden | OK: 10-ms-Blöcke Mono 48 kHz per `send_frame`, kein Fehler; Gegenseite hörte den 440-Hz-Ton (Testanruf an eine andere Nummer statt Philipp) |
| Externe Frames empfangen | OK: 100 % Echtzeit, Blöcke zu 1920 Byte (10 ms Stereo), Richtung `INCOMING`, Gerät `MICROPHONE` |
| Echounterdrückung CPU / Dämpfung (künstliches Echo) | 2,6 % eines Kerns / 89,8 dB |
| Webcam-Regler | stand wieder auf 0, mit Zustimmung auf 10 gesetzt |

Teilprojekt 1 hatte über Kodi 1,77 s gemessen. Der Unterschied kommt vermutlich
vom damaligen Weg (44,1 kHz ohne SDP, andere Messung); die 450 ms hier sind
reproduzierbar.

## Entscheidung

- Direkte Ausgabe ist nur etwa 0,35 s schneller, unter der Schwelle von 0,5 s
  aus der Spec, und schaltet während des Anrufs Kodis Bediengeräusche bis zur
  nächsten Wiedergabe stumm. **Standard bleibt Kodi** (`direkte_ausgabe` =
  `false`); die Einstellung bleibt als Option. „Bediengeräusche: nie“ ist dafür
  nicht nötig.
- `ALSA_DELAY_MS` = 90, `KODI_DELAY_MS` = 450, `HDMI_DEVICE` bleibt
  `hdmi:CARD=vc4hdmi0,DEV=0`.
- Echo: `webrtc` (CPU unkritisch). Wirkung mit echtem Raumhall zeigt erst das
  Gespräch.

## Anmeldung mit dem Anrufprozess (Task 12)

- QR-Code mit Forkgram gescannt: Die App meldet „Es ist ein Fehler aufgetreten“,
  Telegram bestätigt die Anmeldung nicht, und der Code wird nach etwa 30 s
  erneuert. Mit der offiziellen Telegram-App noch nicht ausprobiert; möglich ist,
  dass Telegram das Annehmen über einen inoffiziellen Client ablehnt.
- Anmeldung per Telefonnummer, Code und Zwei-Faktor-Passwort: funktioniert.
  Kontakte werden geladen. Session `600`, im Log stehen Nummer, Code und
  Passwort nur als `***`.
- Telegram schickt keinen neuen Code, solange der letzte noch gilt; der alte
  bleibt dann einzugeben.
