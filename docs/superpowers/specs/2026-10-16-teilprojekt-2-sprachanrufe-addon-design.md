# Teilprojekt 2: 1-zu-1-Sprachanrufe im Kodi-Add-on

Stand: 2026-10-16

Gesamtvorhaben und Teilprojekt 1 siehe
`2026-10-14-teilprojekt-1-machbarkeitstest-design.md` und
`../../ergebnisse-teilprojekt-1.md`.

## Ziel

Ein Kodi-Add-on, mit dem man vom Sofa aus per Fernbedienung Telegram-Kontakte
anruft und Anrufe annimmt. Nur Sprache, nur 1-zu-1. Dazu werden die zwei
Schwächen aus dem Machbarkeitstest angegangen: die Verzögerung von 1 bis 2 s
und das Echo bei der Gegenseite.

### Festgelegt

- Genutzt wird der bestehende persönliche Telegram-Account.
- Erreichbar ist man nur, solange das Add-on geöffnet ist. Kein
  Hintergrunddienst, keine Hinweise über anderen Kodi-Inhalten.
- Favoriten sind eine eigene Liste im Add-on, zusammengestellt am Fernseher.
  Sie gelten nur dort.
- Eigene Vollbildoberfläche, unabhängig vom Kodi-Skin.
- Tonweg der Gegenseite: erst messen, dann zwischen direkter ALSA-Ausgabe und
  Kodi entscheiden (siehe „Tonweg“).
- Echo: echte Echounterdrückung mit WebRTC (LiveKit-Paket), Dämpfen als
  Rückfallebene.
- Anmeldung per QR-Code, wahlweise per Telefonnummer.
- Aufbau: Kodi-Add-on plus eigener Anrufprozess.

### Erfolgskriterien

1. Add-on öffnen und einen Favoriten mit OK anrufen.
2. Einen eingehenden Anruf mit der Fernbedienung annehmen.
3. Mit Zurück oder Stopp auflegen.
4. Die Gegenseite hört sich bei normaler Lautstärke nicht selbst, beide können
   gleichzeitig reden.
5. Kodi stürzt nie mit ab, auch wenn der Anrufprozess abstürzt.
6. Die Verzögerung ist per Zählprobe gemessen und mit Teilprojekt 1
   verglichen.

## Bausteine

Das Add-on `script.telegram.calls` ist ein Programm-Add-on
(`xbmc.python.script`), kein Dienst.

| Teil | Läuft in | Aufgabe |
|---|---|---|
| Oberfläche (`resources/lib/ui/`, Fenster-XML unter `resources/skins/Default/1080i/`) | Kodi | Fenster für Anmeldung, Favoriten, Alle Kontakte, Klingeln, Anruf; Fernbedienung |
| Verbindung zum Anrufprozess (`resources/lib/worker.py`) | Kodi | Prozess starten und beenden, Befehle senden, Ereignisse empfangen, Absturz erkennen und neu starten |
| Anrufprozess (`worker/`) | eigener Prozess: `python3` des Systems mit `vendor/` im Suchpfad | Telethon (Anmeldung, Kontakte, Signalisierung), ntgcalls über py-tgcalls (Anruf), Mikrofon, Echounterdrückung, Tonausgabe, Klingelton |
| `vendor/` | — | ntgcalls, py-tgcalls, Telethon, LiveKit, protobuf und Abhängigkeiten, in festen Versionen gebaut von `build-bundle.sh` (aus Teilprojekt 1 übernommen und erweitert) |

Die Logik der Oberfläche (Zustände, Reaktion auf Ereignisse, Favoriten) liegt
in Modulen ohne `xbmc`-Import, damit sie ohne Kodi testbar ist. Die
Fensterklassen sind dünn und rufen diese Module auf.

### Gespeicherte Daten

Ordner `addon_data/script.telegram.calls/`
(`/storage/.kodi/userdata/addon_data/…`):

| Datei | Inhalt | Rechte |
|---|---|---|
| `telegram.session` | Telegram-Session | `600` |
| `favoriten.json` | Telegram-IDs in Reihenfolge | `600` |
| `bilder/` | Profilbilder der Kontakte, Cache | `700` |
| `worker.sock` | Socket zwischen Add-on und Anrufprozess | `600` |
| `settings.xml` | Kodi-Einstellungen des Add-ons, darin `api_id` und `api_hash` | von Kodi verwaltet |

`api_id` und `api_hash` trägt der Nutzer einmal in den Add-on-Einstellungen
ein. Die Werte und die Session aus Teilprojekt 1 werden nicht übernommen.

### Schnittstelle Add-on ↔ Anrufprozess

Unix-Socket, eine JSON-Nachricht pro Zeile, Feld `typ` plus Nutzdaten.

Befehle (Add-on → Prozess): `login_qr`, `login_phone {nummer}`,
`login_code {code}`, `login_password {passwort}`, `contacts`,
`call {id}`, `accept`, `decline`, `hangup`, `mute {an}`, `logout`, `quit`.

Ereignisse (Prozess → Add-on): `ready {angemeldet}`, `qr {url}`,
`need_code`, `need_password`, `login_ok`, `login_error {grund}`,
`contacts {liste}`, `incoming {id, name}`, `outgoing_state {wählt|klingelt}`,
`connected`, `ended {grund}`, `play_kodi {sdp_pfad}`, `stop_kodi`,
`status {telegram_verbunden, mikrofon_ok}`, `error {text}`.

Unbekannte Befehle beantwortet der Prozess mit `error`. Passwort und Code
werden nicht protokolliert.

### Lebensdauer

- Beim Öffnen startet das Add-on den Anrufprozess und wartet auf `ready`. Ab
  dann ist man erreichbar.
- Beim Schließen sendet das Add-on `quit`. Ist der Prozess nach 3 s nicht
  beendet, wird er hart beendet. Dasselbe beim Beenden von Kodi
  (`xbmc.Monitor().abortRequested()`).
- Endet der Prozess unerwartet, endet ein laufender Anruf. Lief ein Gespräch,
  zeigt der Anrufbildschirm wie bei jedem Ende groß „Verbindung abgebrochen“;
  sonst zeigt das Add-on kurz „Anrufteil neu gestartet“. Es startet den
  Prozess neu und verbindet sich wieder. (Geändert am 2026-10-28: die kleine
  Einblendung war am Fernseher nicht lesbar.)

## Bildschirme und Bedienung

**Anmeldung** (nur ohne gültige Session): großer QR-Code mit der Anleitung
„In Telegram: Einstellungen → Geräte → Gerät verbinden“. Der Code erneuert
sich selbständig, bevor Telegram ihn verfallen lässt. Knopf „Mit
Telefonnummer anmelden“ öffnet nacheinander die Kodi-Tastatur für Nummer,
Code und bei Bedarf das Zwei-Faktor-Passwort. Gespeichert wird nur die
Session.

**Startseite (Favoriten):** Kacheln mit Profilbild und Name, als letzte
Kachel „Alle Kontakte“. OK ruft sofort an. Kontextmenü: „Aus Favoriten
entfernen“, „Nach vorne“, „Nach hinten“. Leere Liste: „Noch keine Favoriten –
unter Alle Kontakte hinzufügen“.

**Alle Kontakte:** alphabetische Liste der Telegram-Kontakte, darunter die
Gruppen, ausgegraut mit „Gruppenanrufe folgen“. OK ruft an, Kontextmenü „Zu
Favoriten hinzufügen“. Buchstabensprung und Suche über die Tastatur.

**Anrufbildschirm:** großes Profilbild, Name, Status („Wählt …“,
„Klingelt …“, „Verbunden 02:13“). Knöpfe „Stumm“ und „Auflegen“, Fokus auf
„Auflegen“. Zurück und Stopp legen auf. Lautstärke am Receiver; bei direkter
Ausgabe wirkt Kodis Regler nicht, das steht in der Hilfe des Add-ons.

**Klingelbildschirm:** erscheint über jedem Add-on-Fenster. Bild, Name,
„ruft an“, Knöpfe „Annehmen“ (Fokus) und „Ablehnen“. OK nimmt an, Zurück
lehnt ab. Nach 45 s gilt der Anruf als verpasst.

**Rundherum:**
- Beim Klingeln wird der Bildschirmschoner beendet; während Klingeln und
  Gespräch bleibt er aus.
- Läuft in Kodi eine Wiedergabe, pausiert das Add-on sie beim Anrufen oder
  Annehmen. Danach geht sie nicht von selbst weiter.
- Zurück auf der Startseite fragt: „Telegram-Anrufe schließen? Du bist dann
  nicht mehr erreichbar.“ Während eines Anrufs legt Zurück nur auf.
- Ein zweiter eingehender Anruf während eines Gesprächs wird als besetzt
  abgelehnt.

## Tonweg

```
Webcam-Mikrofon ─ALSA─▶ Echounterdrückung ─▶ ntgcalls ─▶ Gegenseite
                              ▲ Referenz (um gemessene Verzögerung versetzt)
Gegenseite ─▶ ntgcalls ─48 kHz┴─▶ Ausgabe: direkt ALSA  oder  RTP+SDP → Kodi
```

- **Frames im Prozess:** Mikrofon und Ton der Gegenseite laufen über die
  Schnittstelle von ntgcalls für externe Frames durch den Anrufprozess, damit
  die Echounterdrückung beide sieht. Ob das mit ntgcalls/py-tgcalls 3.0.x
  funktioniert, klärt Planschritt 1. Falls nicht: Shell-Quellen wie in
  Teilprojekt 1, ergänzt um einen Hilfsprozess, der beide Richtungen
  verarbeitet.
- **Format:** immer 48 kHz, 16 Bit. 44,1 kHz ist ausgeschlossen (HDMI-Problem
  mit dem Denon, Absturz von ntgcalls; siehe Ergebnisse Teilprojekt 1).
- **Ausgaben** mit gemeinsamer Schnittstelle (`start`, `write`, `stop`,
  `verzoegerung`):
  - *Direkt:* `aplay` auf `hdmi:CARD=vc4hdmi0,DEV=0` mit kleinem Puffer.
  - *Kodi:* RTP L16 an 127.0.0.1 mit SDP-Datei wie in Teilprojekt 1; der
    Prozess meldet `play_kodi`, das Add-on startet `xbmc.Player().play()`
    mit Musik-ListItem ohne `inputstream`-Eigenschaft.
  - Ist der HDMI-Ausgang bei Anrufbeginn belegt, wird automatisch die
    Kodi-Ausgabe genommen.
- **Klingelton:** im Prozess erzeugt, über dieselbe Ausgabe.
- **Mikrofon:** ALSA direkt, Rückstau begrenzt wie in `mic_capture.py`.
  PulseAudio wird nicht benutzt.

### Messtest (Planschritt 1)

Mit Kreuzkorrelation wie in Teilprojekt 1 (Testton hinaus, Webcam hört mit):

1. Verzögerung über die direkte Ausgabe und über Kodi.
2. Ist der HDMI-Ausgang eine Minute nach dem letzten Ton frei? Verhalten von
   Kodi, wenn es während unserer direkten Ausgabe ein Bediengeräusch spielen
   will (Fehlermeldung, Absturz, Hänger).
3. Wirksamkeit und CPU-Last der Echounterdrückung auf dem Pi.
4. Funktionieren externe Frames in ntgcalls/py-tgcalls 3.0.x.

Vorher und nachher `check.py --guard`. Kodi-Einstellungen werden dabei nicht
geändert.

### Entscheidungsregel

Die direkte Ausgabe wird Standard, wenn sie mindestens 0,5 s schneller ist
und Kodi sie ohne Fehler verträgt. Kodi spielt Bediengeräusche, solange
nichts läuft (`audiooutput.guisoundmode` = 1), und hält den Ausgang danach
eine Minute offen (`audiooutput.streamsilence` = 1). Die direkte Ausgabe als
Standard braucht deshalb voraussichtlich „Bediengeräusche: nie“. Diese
Einstellung wird nur mit Zustimmung des Nutzers geändert; die Messwerte
werden ihm dazu vorgelegt. Ohne Zustimmung bleibt Kodi Standard, und die
direkte Ausgabe wird nur genommen, wenn der Ausgang gerade frei ist.

### Echo

- WebRTC-Audioverarbeitung aus dem LiveKit-Paket
  (`livekit.rtc.AudioProcessingModule`, Apache-2.0, aarch64-Wheel vorhanden,
  etwa 23 MB): Echounterdrückung, Rauschunterdrückung, Hochpass.
- Mikrofon-Frames gehen durch `process_stream`, der Ton der Gegenseite durch
  `process_reverse_stream`, jeweils in 10-ms-Blöcken.
- Die Referenz wird um die gemessene Verzögerung der gewählten Ausgabe
  versetzt (direkt voraussichtlich klein, Kodi etwa 1,8 s), damit der
  Rest-Versatz im Bereich der WebRTC-Verzögerungsschätzung liegt.
- Rückfallebene, falls die Unterdrückung auf dem Pi nicht genügt: Mikrofon
  dämpfen, solange die Gegenseite spricht.

### Webcam-Regler

Der Anrufprozess liest `Mic Capture Volume` der Webcam regelmäßig. Steht er
auf 0 (die C922 setzt ihn beim Wieder-Anstecken zurück), stellt er ihn auf 10
von 15. Erst wenn die Webcam fehlt oder sich der Regler nicht stellen lässt,
meldet er `status {mikrofon_ok: false}` und das Add-on zeigt einen Hinweis.
(Geändert am 2026-10-28 auf Wunsch des Nutzers; vorher nur Hinweis.)

## Sicherheit

- Session mit Rechten `600`, nie im Log, nie kopiert; `deploy.sh` schließt
  `addon_data` aus.
- Telefonnummer, Code und Passwort werden weder gespeichert noch
  protokolliert. Das Log nennt Kontakte mit Namen, nicht mit Nummer.
- Socket mit Rechten `600`, nur Befehle aus der festen Liste.
- „Abmelden“ in den Add-on-Einstellungen meldet die Session bei Telegram ab
  und löscht sie.
- Bibliotheken in festen Versionen.

## Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| Kein Netz oder Telegram nicht erreichbar | Hinweisleiste „Keine Verbindung zu Telegram“, neuer Versuch im Hintergrund |
| Session widerrufen | zurück zur Anmeldung |
| Wartezeit (FloodWait) bei der Anmeldung | „Bitte X Minuten warten“ |
| Kein Mikrofon oder Regler auf 0 | Hinweis; Anrufen gesperrt, bis das Mikrofon da ist |
| Abgelehnt, besetzt, 45 s keine Antwort, Verbindung abgebrochen | Grund 3 s auf dem Anrufbildschirm, dann zurück |
| Anrufprozess abgestürzt | Anruf endet, Prozess startet neu, Kodi läuft weiter |
| Bibliothek lässt sich nicht laden | Meldung mit Verweis auf das Log; Add-on bleibt bedienbar und schließt sauber |

## Tests

- **Automatisch auf dem Entwicklungsrechner** (pytest):
  - Schnittstelle: Nachrichten kodieren und dekodieren, unbekannte Befehle.
  - Favoritenspeicher: hinzufügen, entfernen, verschieben, kaputte Datei.
  - Wahl der Ausgabe samt Rückfall auf Kodi bei belegtem Ausgang.
  - Echounterdrückung mit künstlichen Signalen: Sprache plus um eine bekannte
    Zeit verzögertes Echo; das Echo muss deutlich leiser werden.
  - Zustandslogik der Oberfläche ohne Kodi.
- **Auf dem Pi ohne Kodi:** Der Anrufprozess lässt sich wie `call.py` von der
  Kommandozeile bedienen (anrufen, annehmen).
- **Abnahme mit einem echten Kontakt:** die Erfolgskriterien 1–6, dazu den
  Anrufprozess während eines Gesprächs absichtlich beenden.
- Vor und nach jedem Test auf dem Pi `check.py --guard`.

## Installation

`deploy.sh` kopiert das Add-on nach
`/storage/.kodi/addons/script.telegram.calls/` (ohne `addon_data`) und lässt
Kodi per JSON-RPC die lokalen Add-ons neu einlesen. Kodi wird nicht neu
gestartet.

## Nicht enthalten

Video (Teilprojekt 3), Gruppenanrufe (Teilprojekt 4), Erreichbarkeit bei
geschlossenem Add-on, Chat, mehrere Accounts.
