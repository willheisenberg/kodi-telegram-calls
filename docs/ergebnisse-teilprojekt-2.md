# Ergebnisse Teilprojekt 2: 1-zu-1-Sprachanrufe im Kodi-Add-on

Stand: 2026-10-28. Gerät: Raspberry Pi 5, LibreELEC 12.2.1, Kodi 21.3, HDMI an
einen Denon-AVR, Mikrofon der USB-Webcam C922. Abnahme mit echten Anrufen von
und zu Freunden, bedient mit der Fernbedienung. Spec:
`docs/superpowers/specs/2026-10-16-teilprojekt-2-sprachanrufe-addon-design.md`.

## Ergebnis: abgenommen

| Punkt | Ergebnis |
|---|---|
| Anmeldung | per Telefonnummer; QR-Scan mit Forkgram scheitert („Es ist ein Fehler aufgetreten“), offizielle App nicht getestet |
| Kontakte, Favoriten, Suche | funktioniert (Fernprüfung per JSON-RPC und Screenshots) |
| Ausgehender Anruf | klar verständlich, kaum Verzögerung |
| Eingehender Anruf | Klingeldialog über jedem Fenster, annehmen und ablehnen per Fernbedienung |
| Nicht angenommen | nach 45 s „Verpasst“; so gewünscht |
| Verzögerung | Kodi-Anteil stabil 0,5–0,7 s (gemessen); im Gespräch „1 bis 2 Sekunden“ geschätzt |
| Absturz des Anrufteils im Gespräch | Kodi läuft weiter, Anruffenster zeigt groß „Verbindung abgebrochen“, Anrufteil nach 1,5–2 s neu gestartet, Startseite bedienbar; bei der Gegenseite erst „Wiederaufbau der Verbindung“, dann „abgebrochen“ |
| Neustartlimit | nach 4 Abstürzen in 60 s Hinweis „Der Anrufteil stürzt wiederholt ab“ |
| Spotify | pausiert beim Anrufbeginn, läuft nach dem Auflegen nicht von selbst weiter |
| Mikrofon nach Wieder-Anstecken | Regler wird von selbst auf 10 von 15 gestellt |

Zweiter Anruf während eines Gesprächs: wird mit dem Grund „besetzt“
verworfen (`PhoneCallDiscardReasonBusy`); am 2026-10-28 mit vorgetäuschtem
Gespräch auf der Box geprüft, beim Anrufer kam das Besetztzeichen.

Nicht gesondert abgenommen: Echo-Qualität aus Sicht der Gegenseite (keine
Beschwerde gemeldet), Fokus im Klingeldialog nach der Korrektur (danach ohne
Beanstandung angenommen und abgelehnt).

## Verzögerung: Ursache und Lösung

Angenommene Anrufe hatten anfangs mal keine, mal 6, mal 10 s Verzögerung.
Messung direkt an Kodi (Stille per RTP, Kodis Wiedergabezeit per JSON-RPC):

| Fall | Verzögerung von Kodi |
|---|---|
| gleichmäßiger Strom | 0,5–0,7 s |
| nach 1,5 s ohne Daten | Kodi meldet „stream stalled“, spielt 7 s nichts, danach dauerhaft 7,1 s |
| weitere 3 s Pause danach | kein neuer Leerlauf, Kodi spielt aus seinem Polster, 4,1 s |
| mit Taktgeber, 1,5 s Blockade des Senders | 0,5–0,7 s, kein „stream stalled“ |
| mit Taktgeber, Ton in Schüben (alle 60 ms sechs Blöcke) | 0,5–0,7 s |

- Kodi behandelt die SDP-Datei als Datei, nicht als Live-Strom. Live sind nur
  Adressen mit `udp://` oder `rtp://` (`CDVDInputStreamFFmpeg::Open`); bei
  Dateien füllt Kodi nach einem Leerlauf den ganzen Puffer
  (`CACHESTATE_FULL`).
- Den Leerlauf meldet Kodi schon, wenn seine Paketwarteschlange etwa 0,1 s
  leer ist, nicht erst, wenn sein Gesamtpuffer leer ist.
- Auslöser: py-tgcalls blockiert beim Annehmen den Anrufprozess etwa 1 s,
  und Telegram liefert den Ton teils in Schüben.
- Lösung: `worker/pacer.py`. Ein eigener Thread schreibt alle 10 ms genau
  10 ms an die Ausgabe, aus einer Warteschlange (höchstens 0,3 s, das Älteste
  wird verworfen) oder Stille. Auch der Klingelton läuft durch ihn.
- `rtp://` ohne SDP wäre live, geht aber nur mit 44,1 kHz (ausgeschlossen,
  siehe Teilprojekt 1).

Die Einstellung „Direkte Ausgabe, wenn HDMI frei ist“ spart weitere etwa
0,35 s, lässt aber Kodis Bediengeräusche bis zur nächsten Wiedergabe stumm
(`docs/messtest-teilprojekt-2.md`). Standard bleibt die Ausgabe über Kodi.

## Probleme und Lösungen

| Problem | Ursache | Lösung |
|---|---|---|
| Party Video verdeckt den Anruf | es hält den Anrufton für Musik | Home-Fenster-Eigenschaft `partyvideo.suppress`, in Party Video ausgewertet; Anruffenster wird beim Auftauchen der Visualisierung nach vorn geholt |
| Kodi stürzt ab (SIGSEGV) beim Visual | Party Video importierte yt-dlp in Kodis Python | in Party Video behoben: yt-dlp im eigenen Prozess |
| Fokus im Klingeldialog springt zurück | Dialog wurde beim Nach-vorn-Holen neu gezeigt | nur beim Auftauchen der Visualisierung nach vorn holen, Dialog nicht neu zeigen |
| Radio startet mitten im Gespräch | Stopp der Kodi-Wiedergabe beim Annehmen; KodiMediaBot hält das für ein abgebrochenes Radio und startet es nach 5 s neu | Wiedergabe läuft vom Klingeln durch ins Gespräch |
| Sekunden Verzögerung bei angenommenen Anrufen | siehe oben | Taktgeber |
| „Kein Mikrofon“ trotz Webcam | C922 setzt `Mic Capture Volume` beim Anstecken auf 0 | Anrufprozess stellt ihn auf 10 |
| Absturzmeldung am TV unlesbar | kleine 4-s-Einblendung | Grund groß im Anruffenster |
| Anruf an Kontakt mit gesperrten Anrufen | `UserPrivacyRestrictedError` | eigener Grund „Anrufe nicht erlaubt (Datenschutz)“ |
| Auflegen genau beim Verbinden ließ den Anrufprozess „verbunden“ zurück (Abschlussreview) | Ausgabe wurde nach dem Auflegen fertig geöffnet | Zähler der Gesprächsenden; eine verspätet geöffnete Ausgabe wird gleich wieder geschlossen |
| zweiter Anruf kam beim Anrufer als „abgelehnt“ an (Abschlussreview) | py-tgcalls verwirft nur mit „aufgelegt“ | eigener `DiscardCallRequest` mit Grund „besetzt“ |
| zwei Add-on-Instanzen, verwaister Anrufprozess | JSON-RPC-Start startet eine zweite Instanz; Kodi gibt Skripten 5 s zum Beenden | Einzelinstanz-Sperre, abbrechbarer Start, Anrufprozess beendet sich 10 s nach Verbindungsende |

## Nebenbefunde

- Nach dem Auflegen startet der KodiMediaBot ein vorher gelaufenes Radio nach
  etwa 9 s wieder (seine Radio-Wiederverbindung). Gelassen; ändern ließe es
  sich nur im KodiMediaBot.
- Telegrams Test-DCs taugen nicht für automatische Anruftests: 99966-Nummern
  liefern auf allen drei Test-DCs `PHONE_CODE_INVALID`; laut TDLib-Maintainer
  sind die Testkonten abgeschaltet. Für Tests ohne Freunde braucht es ein
  zweites echtes Konto.

## Offene Kleinigkeiten (Abschlussreview, zurückgestellt)

Alle selten oder Komfort; keine verhindert die Nutzung.

- `Server.emit` wird aus Executor-Threads aufgerufen (`KodiSink.start/stop`
  über `asyncio.to_thread`); nicht thread-sicher. Sehr selten könnte
  `stop_kodi` verloren gehen und die SDP-Wiedergabe nach dem Gespräch
  weiterlaufen. Abhilfe: per `loop.call_soon_threadsafe` melden.
- Hängt `aplay` beim Beenden, verfällt das 1-s-`join` des Taktgebers; ein
  später `SinkError` des alten Taktgebers könnte den nächsten Anruf beenden.
  Abhilfe: Callback an die Taktgeber-Instanz binden.
- `create_task` ohne gehaltene Referenz (`_fail`, `_safe_send`); in einem Set
  halten wie in `server.py`.
- Nach einem Absturz verdrängt `ready` die Anzeige „Verbindung abgebrochen“
  schon nach 1,5–2 s statt nach 3 s; ein Anruf in diesem Moment wird stumm
  ignoriert.
- `worker.log` wird bei jedem Start geleert; nach einem Absturz fehlt der
  Traceback. Abhilfe: vorher nach `worker.log.1` rotieren.
- Abmelden bei offenem Add-on braucht 20 s bis zur Meldung (Startversuche
  mit Exit 3 bis zum Timeout).
- Echo: `KODI_DELAY_MS` = 450 stammt aus der Messung vor dem Taktgeber; mit
  Taktgeber im Gesprächsbetrieb per Kreuzkorrelation nachmessen.
- `test_pacer.py`: Thread-Test mit echter Zeit (Lücke < 50 ms) könnte auf
  einer stark belasteten Maschine wackeln.
- Gleichzeitiges Anrufen in beide Richtungen (A ruft an, während man A
  anwählt) legt auch den eigenen Anruf auf.
- Ungetestet mit echten Anrufen: Auflegen genau im Moment des Verbindens
  (nur per Test nachgestellt).

## Offen für Teilprojekt 3 (Video)

- Ein zweites Telegram-Konto für automatische Ende-zu-Ende-Tests wäre nützlich.
- Video über Kodi trifft auf dieselbe Puffer-Logik; ein gleichmäßiger Takt
  (wie `pacer.py`) dürfte auch dort nötig sein.
