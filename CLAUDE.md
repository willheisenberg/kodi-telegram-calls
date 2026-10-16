# kodi-telegram-calls

Kodi-Add-on für Telegram-Anrufe auf LibreELEC (Raspberry Pi 5). Specs unter
`docs/superpowers/specs/`, Machbarkeitstest unter `spike/`.

## Zielgerät

`ssh root@192.168.178.10`, LibreELEC 12.2.1, Kodi 21. Das Gerät ist der
Wohnzimmer-Pi und wird parallel genutzt. Dort laufen unter anderem Soloist
(Spotify, `~/githubprojects/kodi-soloist`) und ein Party-Bot im Docker-Add-on.

## Regeln für Arbeiten am Pi

- **PulseAudio nicht verändern.** Keine `pactl load-module`/`unload-module`,
  kein `set-default-sink`/`-source`, keine `move-*`. PulseAudio gehört
  Soloist: Es spielt in die Null-Senke `soloist`, `module-rtp-send` streamt
  deren Monitor an Kodi. `module-switch-on-connect` ist aktiv und macht jedes
  neu geladene Gerät zum Standard. Am 2026-10-14 hat genau das Soloists
  RTP-Stream auf eine fremde Quelle verschoben und Spotify stumm gemacht.
- **Kein PulseAudio-Gerät in ntgcalls benutzen.** Audio läuft über ALSA bzw.
  über Shell-Quellen (`MediaSource.SHELL`), nicht über `MediaDevices`-Geräte
  (`MediaSource.DEVICE`). Das PulseAudio-Modul von ntgcalls 3.0.3 liefert
  zudem verzerrte Aufnahmen.
- **Kodi-Einstellungen nicht ändern** und Kodi nicht ohne Rückfrage stoppen.
- **Vor und nach jedem Test auf dem Pi** `python3 check.py --guard` ausführen.
  Der Wächter meldet, wenn Soloists Audioweg oder die Standardgeräte nicht
  mehr stimmen.
- Session-Datei (`tgcalls.session`) und `config.ini` nie kopieren, ausgeben
  oder überschreiben.

## Erkenntnisse aus dem Machbarkeitstest

- **Piepsiger, knisternder Ton bei 44,1 kHz kommt vom HDMI-Weg zum Denon,
  nicht von unserem Code.** Nach dem Einschalten des Denon (Kodi meldet dann
  „Unable to open the required number of channels“) klingt alles mit
  44,1 kHz zu hoch und knistert, auch Spotify über Soloist. Ein einziges
  kurzes Öffnen des HDMI-Ausgangs mit 48 kHz behebt es bis zum nächsten
  Einschalten (2026-10-15 nachgewiesen). In ALSA sieht der Ausgang in beiden
  Zuständen gleich aus. Abhilfe: Kodi-Ausgabe fest auf 48 kHz oder den
  Anruf-Ton mit 48 kHz senden.
- **Kodi bekommt den Ton als RTP L16 mit 48 kHz über eine SDP-Datei**
  (`spike/anruf.sdp`, Payload-Typ 96). Ohne SDP spielt Kodi RTP nur mit
  44,1 kHz Stereo (statischer Typ 10). Das ListItem darf kein
  `inputstream: inputstream.ffmpeg` haben, sonst lehnt Kodis ffmpeg-Whitelist
  `rtp` ab („Error creating demuxer“). Im Add-on später wie Soloist:
  `xbmc.Player().play()` mit Musik-ListItem.
- **ntgcalls-Shell-Befehle:** Programme ohne Pfad angeben (`python3`, nicht
  `/usr/bin/python3`); ntgcalls sucht immer über `PATH`.
- **Ton der Gegenseite mit 48 kHz anfordern.** Mit 44,1 kHz stürzte ntgcalls
  3.0.3 ab (Heap-Beschädigung).
- **Verzögerung:** RTP → Kodi → Denon → Webcam gemessen 1,77 s
  (Kreuzkorrelation). Mikrofon direkt per `aplay` hatte 1,25 s Dauer-Rückstau
  aus der Klingelphase; `mic_capture.py` begrenzt ihn auf 0,18 s.
- **Echo:** Das Webcam-Mikrofon hört die Boxen; die Gegenseite hört sich
  selbst um die ganze Runde verspätet. Noch keine Echounterdrückung.
- Webcam-Mikrofon: ALSA-Regler `Mic Capture Volume` stand auf 0 von 15, am
  2026-10-15 auf 10 gesetzt. Gilt bis zum Abstecken.
