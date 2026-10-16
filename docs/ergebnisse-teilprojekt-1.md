# Ergebnisse Teilprojekt 1: Machbarkeitstest

Stand: 2026-10-16. Gerät: Raspberry Pi 5, LibreELEC 12, Kodi 21, Ausgabe per
HDMI an einen Denon-AVR (5.1), Mikrofon der USB-Webcam. Getestet mit
`spike/call.py` gegen einen echten Telegram-Kontakt.

## Ergebnis: machbar

ntgcalls 3.0.3 trägt auf dem Pi 5. Testanrufe in beide Richtungen waren klar
verständlich und liefen ohne Abbruch.

| Kriterium | Ergebnis |
|---|---|
| Gespräch in beide Richtungen | klar verständlich, kein Abbruch, Mikrofon ohne Aussetzer |
| CPU-Last des Prozesses | etwa 5–6 % |
| Verzögerung | anfangs etwa 3–6 s, nach den Korrekturen „1 bis 2 Sekunden“ (Zählprobe) |
| Echo | ja: die Gegenseite hört sich selbst über Boxen und Webcam |

## Aufbau, der funktioniert

- **Ton der Gegenseite:** ntgcalls liefert s16le, 48 kHz, Stereo über eine
  Shell-Senke an `rtp_send.py`. Das Skript sendet RTP L16 an 127.0.0.1, Kodi
  spielt den Stream über eine SDP-Datei ab.
- **Mikrofon:** `mic_capture.py` liest die Webcam direkt per ALSA (`aplay -C`)
  und verwirft alles, was über 0,18 s Rückstau hinausgeht.
- PulseAudio und Kodi-Einstellungen bleiben unberührt.

## Probleme und Lösungen

| Problem | Ursache | Lösung |
|---|---|---|
| Ton piepsig und knisternd | HDMI-Weg zum Denon: nach dessen Einschalten ist 44,1 kHz gestört (betrifft auch Spotify) | 48 kHz senden, per SDP-Datei; Soloist ebenso umgestellt |
| ntgcalls-Absturz („corrupted size vs. prev_size“) | Fehler in ntgcalls bei 44,1 kHz | 48 kHz anfordern |
| Shell-Befehl startet nicht | ntgcalls sucht Programme immer über `PATH` | `python3` statt `/usr/bin/python3` |
| „Error creating demuxer“ bei der SDP | `inputstream.ffmpeg` lehnt `rtp` per Whitelist ab | keine inputstream-Eigenschaft am ListItem |
| Gegenseite hört dich mit über 1 s Verzögerung | Mikrofon-Rückstau aus der Klingelphase | `mic_capture.py` mit begrenzter Warteschlange |
| Gegenseite hört nichts | Webcam-Regler `Mic Capture Volume` stand auf 0 | auf 10 von 15 gesetzt (gilt bis zum Abstecken) |

## Wo die verbleibende Verzögerung steckt

Gemessen: RTP-Eingang in Kodi bis zum Schall an der Webcam 1,77 s
(Kreuzkorrelation). Fast die ganze hörbare Verzögerung entsteht also auf
unserer Seite in der Wiedergabe über Kodi und Denon. Netz und Telegram machen
den kleineren Teil aus. Die Mikrofonrichtung ist mit 0,18 s Puffer kurz.

## Offen für Teilprojekt 2

1. **Wiedergabe-Verzögerung senken.** Ansatzpunkte, jeweils erst messen:
   - Kodis Puffer für den RTP-Stream (ffmpeg wartet beim Öffnen auf Daten zur
     Formaterkennung, dazu kommt Kodis Wiedergabepuffer). Mit SDP ist das
     Format bekannt, die Erkennung lässt sich womöglich kürzen.
   - Ausgabe ohne Kodi direkt an ALSA, solange der Anruf läuft. Geht nur,
     wenn Kodi das HDMI-Gerät freigibt; das berührt Kodi-Einstellungen und
     braucht vorher das Okay.
   - Denon: Klangverarbeitung (Upmix, Audyssey) kostet Zeit; ein direkter
     Modus kann helfen.
2. **Echo:** Mikrofon dämpfen, während die Gegenseite spricht (einfach), oder
   echte Echounterdrückung mit dem gesendeten Ton als Referenz. Je kürzer die
   Wiedergabe-Verzögerung, desto leichter wird beides.
3. Wiedergabe im Add-on wie Soloist per `xbmc.Player().play()`.
