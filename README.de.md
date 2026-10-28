![Telegram Calls for Kodi](assets/banner.png)

# Telegram-Anrufe für Kodi

[English](README.md) · **Deutsch**

**Telegram-Sprachanrufe am Fernseher führen und annehmen: ein Kodi-Add-on für
LibreELEC mit dem eigenen Telegram-Account, dem Mikrofon einer USB-Webcam und
dem AV-Receiver, komplett mit der Fernbedienung bedienbar.**

Erreichbar ist man nur, solange das Add-on geöffnet ist. Es gibt keinen
Hintergrunddienst und keine Einblendungen über anderen Kodi-Inhalten.

> Dieses Add-on ist ein inoffizielles Projekt und steht in keiner Verbindung
> zu Telegram. Für die Anrufe nutzt es
> [ntgcalls](https://github.com/pytgcalls/ntgcalls) /
> [py-tgcalls](https://github.com/pytgcalls/pytgcalls), für das Konto
> [Telethon](https://github.com/LonamiWebs/Telethon).

---

## Stand

| Teil | Stand |
|---|---|
| 1. Machbarkeitstest (Anruf von der Kommandozeile) | fertig |
| 2. 1-zu-1-Sprachanrufe im Add-on | funktioniert, Abnahme mit echten Gesprächen steht aus |
| 3. 1-zu-1-Video im Vollbild | geplant |
| 4. Gruppenanrufe | geplant |

## Voraussetzungen

| | |
|---|---|
| Gerät | Raspberry Pi 5 (aarch64), getestet. Die mitgelieferten Bibliotheken sind für aarch64 gebaut. |
| System | LibreELEC 12 mit Kodi 21 „Omega“ (Python 3.11) |
| Mikrofon | USB-Webcam mit Mikrofon (getestet: Logitech C922) |
| Tonausgabe | HDMI, z. B. an einen AV-Receiver |
| Telegram | der bestehende Account und eigene `api_id` / `api_hash` von <https://my.telegram.org> |

## Installation

Ein Release-ZIP gibt es noch nicht. Gebaut und kopiert wird von einem
Linux-Rechner aus:

```
tools/build-bundle.sh            # lädt die aarch64-Bibliotheken nach addon/…/vendor (etwa 220 MB)
tools/deploy.sh                  # kopiert das Add-on auf die Box und schaltet es in Kodi ein
```

`tools/deploy.sh` kopiert standardmäßig nach `root@192.168.178.10`; ein
anderes Ziel als zweites Argument angeben. Den Datenordner des Add-ons
(Session, Favoriten) fasst es nie an.

## Erster Start

1. `api_id` und `api_hash` in den Add-on-Einstellungen eintragen
   (**Add-ons → Programm-Add-ons → Telegram-Anrufe → Einstellungen**).
2. Add-on öffnen. Beim ersten Start erscheint ein QR-Code. Ihn in der
   offiziellen Telegram-App unter **Einstellungen → Geräte → Desktop-Gerät
   verbinden** scannen. Oder **Mit Telefonnummer anmelden** wählen: Telegram
   schickt einen Code in die App und fragt bei Bedarf das Passwort der
   zweistufigen Bestätigung ab.

Mit einem inoffiziellen Client (getestet: Forkgram) scheiterte das Scannen mit
„Es ist ein Fehler aufgetreten“; die Anmeldung per Telefonnummer funktioniert.

## Bedienung

- **Startseite:** Favoriten als Kacheln, dazu **Alle Kontakte**. OK auf einer
  Kachel ruft an.
- **Alle Kontakte:** alphabetisch, Gruppen am Ende (Gruppenanrufe folgen
  später). Das Kontextmenü bietet **Suchen …** und **Zu Favoriten
  hinzufügen / Aus Favoriten entfernen**. Auf der Startseite entfernt oder
  verschiebt das Kontextmenü einen Favoriten.
- **Im Gespräch:** **Stumm** und **Auflegen**. Zurück und Stopp legen
  ebenfalls auf. Die Lautstärke regelt man am Receiver.
- **Eingehender Anruf:** ein Klingeldialog über jedem Fenster des Add-ons. OK
  nimmt an, Zurück lehnt ab. Nach 45 s gilt der Anruf als verpasst. Ein
  zweiter Anruf während eines Gesprächs wird als besetzt abgelehnt.
- Läuft in Kodi etwas (z. B. Spotify), pausiert es beim Anrufbeginn.
- Zurück auf der Startseite fragt vor dem Schließen; geschlossen ist man nicht
  mehr erreichbar.

## Einstellungen

| Einstellung | Standard | |
|---|---|---|
| api_id / api_hash | – | von my.telegram.org |
| Dieses Gerät abmelden | – | meldet die Session bei Telegram ab und löscht sie (Add-on vorher schließen) |
| Direkte Ausgabe, wenn HDMI frei ist | aus | spielt den Anruf direkt auf HDMI statt über Kodi: etwa 0,35 s weniger Verzögerung, aber Kodis Bediengeräusche bleiben stumm, bis Kodi wieder etwas abspielt |
| Echo-Verfahren | WebRTC | WebRTC-Echounterdrückung, Mikrofon dämpfen oder aus |
| Mikrofon | `plughw:CARD=Webcam,DEV=0` | ALSA-Gerät (Expertenstufe) |

## Aufbau

```
Kodi-Add-on (Python in Kodi)          Anrufprozess (System-Python, eigener Prozess)
  Fenster, Fernbedienung    ◀─ Unix-Socket, JSON-Zeilen ─▶  Telethon: Anmeldung, Kontakte
  spielt den Anrufton ab                                    ntgcalls: der Anruf
       ▲                                                    Webcam-Mikrofon ─▶ Echounterdrückung ─▶ Telegram
       └──────── RTP 48 kHz + SDP-Datei ◀───────────────── Telegram ─▶ Tonausgabe
```

- **Eigener Prozess:** ntgcalls ist nativer Code. Stürzt er ab, endet der
  Anruf, Kodi läuft weiter, und das Add-on startet den Anrufprozess neu
  (höchstens dreimal pro Minute).
- **Nur 48 kHz:** Nach dem Einschalten eines AV-Receivers kann 44,1 kHz über
  HDMI zu hoch klingen und knistern; außerdem stürzt ntgcalls 3.0.3 beim
  Empfang mit 44,1 kHz ab.
- **Ton über Kodi** als Standard: etwa 0,45 s vom Netz bis zu den Boxen im
  Testaufbau.
- **Echounterdrückung** mit der WebRTC-Audioverarbeitung aus dem
  [LiveKit](https://github.com/livekit/python-sdks)-Paket. Die Webcam hört die
  Boxen; der Ton der Gegenseite dient als Referenz, verzögert um die gemessene
  Ausgabeverzögerung.
- **PulseAudio wird nicht benutzt:** Mikrofon und Ausgabe laufen über ALSA,
  andere Add-ons mit PulseAudio (z. B.
  [Soloist](https://github.com/willheisenberg/kodi-soloist)) bleiben unberührt.

## Datenschutz und Sicherheit

- Die Telegram-Session (Vollzugriff auf das Konto) bleibt auf der Box, ist nur
  für root lesbar und wird von den Werkzeugen nie kopiert.
- Telefonnummer, Anmeldecode und Passwort gehen nur an Telegram und werden
  weder gespeichert noch protokolliert.
- Der Socket zwischen Add-on und Anrufprozess ist nur für root zugänglich und
  nimmt nur eine feste Liste von Befehlen an.

## Fehlersuche

- `addon_data/script.telegram.calls/worker.log` ist das Log des
  Anrufprozesses; in `kodi.log` stehen die Meldungen des Add-ons mit dem
  Präfix `script.telegram.calls:`.
- „Kein Mikrofon“: prüfen, ob die Webcam angeschlossen ist. Die C922 setzt
  ihren ALSA-Regler `Mic Capture Volume` beim Wieder-Anstecken auf 0; der
  Anrufprozess stellt ihn von selbst auf 10 von 15 (`amixer -c Webcam`).
- `tools/wctl.py` bedient den Anrufprozess ohne Kodi von der Kommandozeile
  (anmelden, Kontakte, anrufen, annehmen).

## Entwicklung

```
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q      # 148 Tests, ohne Kodi und Telegram
.venv/bin/ruff check .
tools/make_icon.sh       # Icon und Banner aus assets/*.svg (braucht rsvg-convert)
```

Der Code muss mit Python 3.11 (LibreELEC 12) kompatibel bleiben. Entwürfe und
Messungen liegen in `docs/`.

## Lizenz

Noch nicht festgelegt. Die mitgelieferten Bibliotheken behalten ihre eigenen
Lizenzen (ntgcalls und py-tgcalls: LGPL-3.0, Telethon: MIT, LiveKit:
Apache-2.0). Der Hörer im Icon ist das „call“-Icon aus Googles Material Icons
(Apache-2.0).
