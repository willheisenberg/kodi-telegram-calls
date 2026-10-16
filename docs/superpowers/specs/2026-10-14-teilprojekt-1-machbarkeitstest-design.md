# Teilprojekt 1: Machbarkeitstest Sprachanruf auf LibreELEC

Stand: 2026-10-14

## Gesamtvorhaben

Ein Kodi-Add-on für LibreELEC auf dem Raspberry Pi 5, das ausschließlich
Telegram-Anrufe macht: Sprache und Video, 1-zu-1 und Gruppen, im Vollbild auf
dem TV, vollständig per Fernbedienung bedienbar.

Festgelegte Rahmenbedingungen:

- Genutzt wird der bestehende persönliche Telegram-Account.
- Erreichbar ist man nur, solange das Add-on geöffnet ist. Es gibt keinen
  Hintergrunddienst und keine Benachrichtigungen über anderen Kodi-Inhalten.
- Startbildschirm mit Favoriten, zusätzlich ein Menüpunkt für alle Kontakte
  und Gruppen.
- Gruppenanrufe sollen gestartet und laufenden Gruppenanrufen soll
  beigetreten werden können.

Das Vorhaben ist in vier Teilprojekte zerlegt, jedes mit eigener Spec und
eigenem Plan:

1. Machbarkeitstest: ausgehender Sprachanruf per Kommandozeile (dieses Dokument)
2. 1-zu-1-Sprachanrufe im Kodi-Add-on
3. 1-zu-1-Video im Vollbild
4. Gruppenanrufe

## Ziel von Teilprojekt 1

Auf dem Pi 5 unter LibreELEC ruft ein Kommandozeilen-Skript einen
Telegram-Kontakt an. Die Gegenseite ist über den TV zu hören und hört
ihrerseits das Webcam-Mikrofon. Kein Video, keine Kodi-Oberfläche.

Der Test beantwortet, ob ntgcalls auf diesem Gerät trägt, bevor Arbeit in die
Oberfläche fließt.

### Erfolgskriterium

Ein zweiminütiges Gespräch in beide Richtungen ohne Abbruch, dazu:

- gemessene CPU-Last des Prozesses während des Gesprächs,
- geschätzte Verzögerung (Zählprobe mit der Gegenseite),
- Aussage, ob Echo auftritt.

## Technische Grundlage

### Bibliotheken

- **ntgcalls 3.0.x** (LGPL-3.0): native Anruf-Bibliothek. MarshalX/tgcalls
  wird nicht verwendet, dort gab es seit Januar 2023 keinen Commit mehr.
- **py-tgcalls 3.0.x**: Python-Schicht über ntgcalls. Bringt Beispiele für
  Privatanrufe (`example/p2p_example`), Mikrofonaufnahme
  (`example/capture_mic`) und Telethon (`example/telethon_example`) mit sowie
  `MediaDevices` für Mikrofon, Lautsprecher und Kamera.
- **Telethon**: MTProto-Client für Anmeldung und Signalisierung. Gewählt, weil
  reines Python und damit ohne Kompilieren mitlieferbar.

### Befund auf dem Zielgerät (192.168.178.10, ausgelesen am 2026-10-14)

| Punkt | Wert |
|---|---|
| System | LibreELEC 12.2.1, RPi5.aarch64, Kernel 6.12.56, 8 GB RAM |
| Kodi | 21.3 Omega |
| Python | 3.11.13, ohne pip |
| glibc | 2.38 (ntgcalls verlangt höchstens 2.28) |
| Fest verlinkte Bibliotheken von ntgcalls | alle vorhanden (libc, libstdc++, libgcc_s, libz und Verwandte) |
| Zur Laufzeit nachgeladen | `libasound.so.2` und `libpulse.so.0` vorhanden; `libva`, `libvdpau`, `libXcursor` fehlen |
| PulseAudio | Server läuft |
| Wiedergabegeräte | zwei HDMI-Ausgänge (vc4hdmi0, vc4hdmi1) |
| Aufnahmegeräte | keine, es ist keine Webcam angeschlossen |
| Kernelmodule | `uvcvideo.ko` und `snd-usb-audio.ko` vorhanden, nicht geladen |
| Werkzeuge | `aplay`, `v4l2-ctl`, `pactl` vorhanden; `arecord` und `ffmpeg` fehlen |
| Docker-Add-on | installiert (Rückfallebene steht bereit) |
| Freier Speicher | 46,8 GB unter `/storage` |

Die fehlenden Bibliotheken `libva`, `libvdpau` und `libXcursor` betreffen
Hardware-Videodekodierung und Bildschirmaufnahme. Für den Sprachtest sind sie
voraussichtlich unerheblich; `check.py` stellt das beim Import fest.

Nicht geprüft ist bisher, ob ntgcalls auf dem Gerät tatsächlich importiert
und einen Anruf aufbaut. Der Befund oben stammt aus der Analyse des Wheels
und aus Abfragen am Gerät, nicht aus einem Lauf.

## Ansatz

Mitgelieferte Wheels und LibreELECs eigenes Python. Die aarch64-Wheels werden
auf dem Entwicklungsrechner heruntergeladen und in einen Ordner `vendor/`
entpackt. Auf dem Pi startet das System-Python die Skripte mit `vendor/` im
Suchpfad. pip auf dem Pi ist nicht nötig.

Rückfallebene: ein Debian-Container im vorhandenen Docker-Add-on, falls
ntgcalls unter LibreELEC nicht läuft und sich das nicht durch mitgelieferte
Bibliotheken beheben lässt.

## Bausteine

Projektverzeichnis: `~/githubprojects/kodi-telegram-calls/`, Unterordner
`spike/`. Ziel auf dem Pi: `/storage/tgcalls-test/`.

| Datei | Aufgabe | Läuft auf |
|---|---|---|
| `spike/build-bundle.sh` | Lädt die Wheels für `manylinux_2_28_aarch64` und die angegebene Python-Version (Standard 3.11) mit `pip download --only-binary=:all:` und entpackt sie nach `spike/vendor/`. Bricht ab, wenn für ein Paket kein passendes Wheel existiert. | Entwicklungsrechner |
| `spike/deploy.sh` | Kopiert `spike/` ohne Session- und Konfigurationsdateien per `scp` nach `/storage/tgcalls-test/`. | Entwicklungsrechner |
| `spike/check.py` | Prüft Python-Version gegen die des Bundles, importiert ntgcalls und Telethon, listet Mikrofone und Lautsprecher aus `MediaDevices`. Gibt je Prüfpunkt OK oder FEHLER mit Ursache aus. | Pi |
| `spike/login.py` | Einmalige Anmeldung: Telefonnummer, Code, bei Bedarf Zwei-Faktor-Passwort. Legt die Session-Datei mit Rechten `600` an. | Pi |
| `spike/call.py` | Ruft einen Kontakt an (Benutzername oder Telefonnummer als Argument), verbindet Mikrofon und Lautsprecher, gibt Statuswechsel aus, legt bei Strg+C sauber auf. Optionen `--mic` und `--speaker` wählen ein Gerät aus der Liste von `check.py`. | Pi |
| `spike/config.example.ini` | Vorlage für `api_id` und `api_hash`. | beide |

`vendor/`, `config.ini` und `*.session` stehen in `.gitignore`.

### Zugangsdaten

- `api_id` und `api_hash` legt der Nutzer auf my.telegram.org an und trägt sie
  auf dem Pi in `/storage/tgcalls-test/config.ini` ein (Rechte `600`).
- Telefonnummer, Code und Passwort werden nur interaktiv abgefragt und nicht
  gespeichert.
- Die Session-Datei gewährt Vollzugriff auf den Account. Sie verlässt den Pi
  nicht und wird von `deploy.sh` weder kopiert noch überschrieben.
- Widerruf jederzeit in der Telegram-App unter „Geräte“.

## Testablauf

1. Webcam anschließen. Prüfen, dass `uvcvideo` und `snd_usb_audio` geladen
   werden und die Karte in `/proc/asound/cards` erscheint.
2. `build-bundle.sh` und `deploy.sh` auf dem Entwicklungsrechner ausführen.
3. `check.py` auf dem Pi ausführen.
4. `login.py` einmal ausführen.
5. `systemctl stop kodi`, dann `call.py <kontakt>`. Gespräch führen, Messwerte
   notieren, `systemctl start kodi`.
6. Derselbe Anruf bei laufendem Kodi, um zu sehen, ob sich das Audiogerät
   teilen lässt (direkt über ALSA oder über den PulseAudio-Server).
7. Ergebnisse in `docs/ergebnisse-teilprojekt-1.md` festhalten.

## Fragen, die der Test beantwortet

- Läuft ntgcalls unter LibreELECs Python und Bibliotheken?
- Funktionieren Aufnahme und Wiedergabe, auch über HDMI?
- Lässt sich das Audiogerät mit laufendem Kodi teilen, und über welchen Weg?
- Wie hoch sind CPU-Last und Verzögerung bei reinem Ton?
- Tritt Echo auf, weil der TV-Lautsprecher ins Webcam-Mikrofon zurückspielt?
- Verlangt py-tgcalls ein `ffmpeg`-Programm, obwohl nur Geräte genutzt werden?

## Fehlerbehandlung

Jedes Skript endet mit einer klaren Meldung und einem Exit-Code ungleich null
statt zu hängen:

- Konfiguration fehlt oder ist unvollständig
- nicht angemeldet (Session fehlt oder wurde widerrufen)
- Kontakt nicht gefunden
- kein Mikrofon oder kein Lautsprecher gefunden
- Anruf abgelehnt, besetzt oder nach 45 Sekunden nicht angenommen
- Verbindung während des Gesprächs abgebrochen

## Abbruchkriterien

- Scheitert `check.py` am Import und lässt sich das nicht durch mitgelieferte
  Bibliotheken beheben, wird der Test im Docker-Container wiederholt.
- Scheitert auch dort der Anruf selbst, wird vor Teilprojekt 2 eine
  Alternative geprüft (Matrix oder SIP).

## Nicht enthalten

Eingehende Anrufe, Video, Kodi-Oberfläche, Favoriten, Gruppen, Echo-Unterdrückung.
Die Python-Skripte sind Wegwerf-Code. In Teilprojekt 2 übernommen werden
`build-bundle.sh` und die dokumentierten Ergebnisse.
