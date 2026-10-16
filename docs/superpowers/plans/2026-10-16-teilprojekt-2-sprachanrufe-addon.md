# Teilprojekt 2: Sprachanrufe im Kodi-Add-on – Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Kodi-Add-on `script.telegram.calls`, mit dem man per Fernbedienung Telegram-Kontakte anruft und Anrufe annimmt, mit Echounterdrückung und möglichst kurzer Verzögerung.

**Architecture:** Das Add-on (Kodi-Python) zeichnet nur die Oberfläche und startet beim Öffnen einen eigenen Anrufprozess mit dem System-Python. Der Prozess enthält Telethon, ntgcalls/py-tgcalls, Mikrofon, WebRTC-Echounterdrückung und Tonausgabe; beide sprechen über einen Unix-Socket mit JSON-Zeilen. Die Logik beider Seiten liegt in Modulen ohne Kodi- und Telegram-Import, damit sie auf dem Entwicklungsrechner testbar ist.

**Tech Stack:** Python 3.11 (LibreELEC 12.2), Kodi 21 (`xbmc.python` 3.0.1, WindowXML), Telethon 1.45.0, py-tgcalls 3.0.0, ntgcalls 3.0.3, LiveKit 1.1.21 (`AudioProcessingModule`), qrcode 8.2 + pypng, numpy, ALSA-Werkzeuge (`aplay`, `amixer`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-16-teilprojekt-2-sprachanrufe-addon-design.md`; Vorgeschichte: `docs/ergebnisse-teilprojekt-1.md`, `CLAUDE.md` (Projektregeln).

## Global Constraints

- **Nicht committen.** Das Projekt ist kein Git-Repo, und der Nutzer erlaubt Commits nur auf ausdrückliche Anweisung. Wo ein Plan sonst „Commit“ hätte, steht „Stand festhalten“: Tests grün, Änderungen liegen im Arbeitsverzeichnis. Subagenten ist Committen ausdrücklich untersagt.
- **Code muss unter Python 3.11 laufen** (LibreELEC). Auf dem Entwicklungsrechner läuft 3.14: keine Syntax ab 3.12 (keine `type`-Anweisung, keine Generics-Syntax `def f[T]`, in f-Strings keine gleichen Anführungszeichen innerhalb der Klammern).
- **Ton immer 48 kHz, 16 Bit.** 44,1 kHz nie: HDMI zum Denon klingt dann nach dem Einschalten zu hoch, ntgcalls 3.0.3 stürzt beim Empfang mit 44,1 kHz ab.
- **PulseAudio nicht benutzen und nicht verändern** (gehört Soloist). Mikrofon und Ausgabe nur über ALSA bzw. RTP an Kodi.
- **Kodi-Einstellungen nicht ändern, Kodi nicht ohne Rückfrage stoppen oder neu starten.** Insbesondere `audiooutput.guisoundmode` ändert nur der Nutzer.
- **Vor und nach jedem Test auf dem Pi:** `ssh root@192.168.178.10 'cd /storage/tgcalls-test && python3 check.py --guard'` muss OK melden.
- **Sessions und Zugangsdaten nie kopieren, ausgeben oder überschreiben**: `/storage/tgcalls-test/tgcalls.session`, `config.ini`, `addon_data/script.telegram.calls/telegram.session`. Telefonnummer, Code, Passwort nie protokollieren. Core-Dumps enthalten Schlüssel: nicht kopieren.
- **ListItem für den SDP-Stream ohne `inputstream`-Eigenschaft** (sonst lehnt Kodis ffmpeg-Whitelist `rtp` ab).
- **RTP-Port des Anrufs: 23533** (Soloist nutzt 23433).
- **Webcam-Regler nicht automatisch verstellen**; nur melden.
- Pi: `ssh root@192.168.178.10`. Add-on-Ziel `/storage/.kodi/addons/script.telegram.calls/`, Testziel `/storage/tgcalls-addon/`, Daten `/storage/.kodi/userdata/addon_data/script.telegram.calls/`.
- Sprache von Oberfläche, Meldungen und Kommentaren: Deutsch mit Umlauten.

## Review Focus

1. **Add-on wird während eines Anrufs oder Klingelns geschlossen** (Zurück bestätigt, Kodi beendet): Der Prozess muss beim `quit` erst auflegen, dann enden. Test: `test_shutdown_legt_auf` (Task 8), `test_quit_beendet_prozess` (Task 11).
2. **HDMI-Ausgang beim Anrufbeginn belegt oder `aplay` scheitert sofort:** Rückfall auf die Kodi-Ausgabe statt Stille. Tests: `test_open_sink_faellt_bei_belegtem_hdmi_auf_kodi_zurueck`, `test_open_sink_faellt_zurueck_wenn_aplay_sofort_endet` (Task 5).
3. **Zweiter eingehender Anruf während eines Gesprächs:** wird als besetzt abgelehnt, das laufende Gespräch bleibt unberührt, die Oberfläche zeigt nichts. Tests: `test_zweiter_anruf_wird_abgewiesen` (Task 8), `test_incoming_waehrend_anruf_wird_ignoriert` (Task 13).
4. **Anrufprozess stürzt mitten im Gespräch ab:** Oberfläche verlässt den Anrufbildschirm, meldet den Neustart, startet höchstens dreimal pro Minute neu. Tests: `test_verlust_beendet_anruf_und_startet_neu` (Task 13), `test_absturz_meldet_lost` (Task 11).
5. **Anrufprozess zweimal gestartet** (Abmelden in den Einstellungen bei offenem Add-on, Rest eines alten Prozesses): Sperrdatei verhindert zwei Telethon-Clients auf derselben Session; ein verwaister Socket von einem Absturz stört den Neustart nicht. Tests: `test_sperre_verhindert_zweiten_prozess` (Task 10), `test_alter_socket_wird_ersetzt` (Task 10).

---

## Dateistruktur

```
kodi-telegram-calls/
├── pyproject.toml                         pytest- und ruff-Konfiguration
├── requirements-dev.txt                   Testumgebung (.venv) auf dem Entwicklungsrechner
├── addon/script.telegram.calls/           das Add-on, wird 1:1 auf den Pi kopiert
│   ├── addon.xml
│   ├── default.py                         Einstieg: Oberfläche oder Abmelden
│   ├── resources/
│   │   ├── settings.xml
│   │   ├── language/resource.language.{de_de,en_gb}/strings.po
│   │   ├── lib/tgc/
│   │   │   ├── protocol.py                Nachrichtenformat (Add-on und Prozess)
│   │   │   ├── favorites.py               Favoritenliste
│   │   │   ├── workerclient.py            startet den Prozess, Socket-Verbindung
│   │   │   ├── appstate.py                Zustandslogik der Oberfläche
│   │   │   ├── skin.py                    Fenster-XML an Skin-Schriften anpassen
│   │   │   └── kodi_ui.py                 Fenster und Ausführung (einziges Modul mit xbmc)
│   │   └── skins/Default/
│   │       ├── 1080i/tgc-{login,home,contacts,call,ring}.xml
│   │       └── media/tgc-{white,kreis,avatar,alle}.png
│   ├── worker/                            Anrufprozess (System-Python)
│   │   ├── main.py                        Einstieg, Sperre, Befehlsverteilung
│   │   ├── server.py                      Unix-Socket-Server
│   │   ├── session.py                     Telethon: Anmeldung, Kontakte, Bilder
│   │   ├── tgbackend.py                   py-tgcalls: Anruf aufbauen, Frames
│   │   ├── callmanager.py                 Anrufzustände (ohne Telegram testbar)
│   │   ├── audio.py                       baut Ausgabe, Echo, Mikrofon, Klingelton
│   │   ├── rtp.py                         RTP-Versand und SDP
│   │   ├── sinks.py                       Ausgabe direkt per ALSA oder über Kodi
│   │   ├── echo.py                        WebRTC-Echounterdrückung, Dämpfen
│   │   ├── mic.py                         Webcam-Mikrofon, Reglerprüfung
│   │   └── ringtone.py                    Klingelton
│   └── vendor/                            gebaut von tools/build-bundle.sh
├── tools/
│   ├── build-bundle.sh                    aarch64-Wheels nach vendor/
│   ├── deploy.sh                          Add-on auf den Pi kopieren
│   ├── make_media.py                      erzeugt die PNGs in skins/Default/media
│   ├── wctl.py                            Anrufprozess ohne Kodi bedienen
│   └── messtest/                          Wegwerf-Skripte für Task 2
├── tests/                                 pytest
└── spike/                                 Teilprojekt 1, bleibt unverändert
```

---

### Task 1: Gerüst, Bibliotheksbündel und Testumgebung

**Files:**
- Create: `pyproject.toml`, `requirements-dev.txt`, `tools/build-bundle.sh`, `tools/messtest/import_check.py`, `tools/deploy.sh`
- Create: Verzeichnisse `addon/script.telegram.calls/{worker,resources/lib/tgc}`, `tests/`
- Create: `addon/script.telegram.calls/resources/lib/tgc/__init__.py` (leer)

**Interfaces:**
- Produces: `tools/build-bundle.sh` → `addon/script.telegram.calls/vendor/` mit `PYTHON_VERSION`; `tools/deploy.sh [ziel] [host]`; `.venv/bin/pytest` läuft mit `pythonpath` auf `resources/lib` und `worker`.

- [ ] **Step 1: Konfiguration anlegen**

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = [
    "addon/script.telegram.calls/resources/lib",
    "addon/script.telegram.calls/worker",
]

[tool.ruff]
target-version = "py311"
line-length = 120
extend-exclude = ["addon/script.telegram.calls/vendor", "spike"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B"]

[tool.ruff.lint.isort]
known-first-party = ["tgc", "audio", "callmanager", "echo", "main", "mic", "ringtone", "rtp", "server",
                     "session", "sinks", "tgbackend"]
```

`requirements-dev.txt` (Telegram-Bibliotheken in denselben Versionen wie im Bündel, damit Tests sie importieren können):

```
pytest
ruff
numpy
livekit==1.1.21
qrcode==8.2
pypng==0.20220715.0
telethon==1.45.0
py-tgcalls==3.0.0
ntgcalls==3.0.3
```

- [ ] **Step 2: Testumgebung bauen**

Run:
```bash
cd ~/githubprojects/kodi-telegram-calls
python3 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt
mkdir -p addon/script.telegram.calls/worker addon/script.telegram.calls/resources/lib/tgc tests tools/messtest
touch addon/script.telegram.calls/resources/lib/tgc/__init__.py
.venv/bin/python -c "import livekit.rtc, numpy, qrcode, telethon, pytgcalls, ntgcalls; print('ok')"
```
Expected: `ok`

- [ ] **Step 3: `tools/build-bundle.sh` schreiben**

```bash
#!/usr/bin/env bash
# Lädt die aarch64-Wheels für LibreELECs Python nach addon/script.telegram.calls/vendor/.
# Aufruf: tools/build-bundle.sh [python-version]   (Standard: 3.11 = LibreELEC 12.2)
set -euo pipefail

PYVER="${1:-3.11}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/addon/script.telegram.calls/vendor"

# pyaes gibt es auf PyPI nur als sdist; reines Python, wird lokal gebaut.
WHEELHOUSE="$(mktemp -d)"
trap 'rm -rf "$WHEELHOUSE"' EXIT
python3 -m pip wheel --no-deps --wheel-dir "$WHEELHOUSE" pyaes==1.6.1

rm -rf "$VENDOR"
python3 -m pip install \
    --find-links "$WHEELHOUSE" \
    --target "$VENDOR" \
    --only-binary=:all: \
    --implementation cp \
    --python-version "$PYVER" \
    --platform manylinux_2_28_aarch64 \
    --platform manylinux_2_17_aarch64 \
    --platform manylinux2014_aarch64 \
    --no-compile \
    py-tgcalls==3.0.0 ntgcalls==3.0.3 telethon==1.45.0 \
    livekit==1.1.21 qrcode==8.2 pypng==0.20220715.0 \
    typing_extensions  # von pip bei abweichender Host-Python-Version nicht mit aufgelöst

echo "$PYVER" > "$VENDOR/PYTHON_VERSION"
du -sh "$VENDOR"
```

Run: `chmod +x tools/build-bundle.sh && tools/build-bundle.sh`
Expected: endet ohne Fehler, Größe etwa 100–150 MB. Prüfen: `ls addon/script.telegram.calls/vendor | grep -E '^(ntgcalls|livekit|numpy|telethon|qrcode|png)'` listet alle sechs.

- [ ] **Step 4: `tools/deploy.sh` schreiben**

```bash
#!/usr/bin/env bash
# Kopiert das Add-on auf den Pi. addon_data (Session, Favoriten) bleibt unberührt.
# Aufruf: tools/deploy.sh [ziel] [host]
#   ziel Standard: /storage/.kodi/addons/script.telegram.calls
#   Testziel ohne Kodi: /storage/tgcalls-addon
set -euo pipefail

DEST="${1:-/storage/.kodi/addons/script.telegram.calls}"
HOST="${2:-root@192.168.178.10}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/addon/script.telegram.calls"
KODI_ADDON=/storage/.kodi/addons/script.telegram.calls

[ -d "$SRC/vendor" ] || { echo "vendor/ fehlt, zuerst tools/build-bundle.sh ausführen" >&2; exit 1; }
case "$DEST" in
    *addon_data*) echo "Ziel darf nicht in addon_data liegen" >&2; exit 1 ;;
esac

ssh "$HOST" "mkdir -p '$DEST' && rm -rf '$DEST/vendor' '$DEST/worker' '$DEST/resources'"
tar -C "$SRC" --exclude=__pycache__ -czf - . | ssh "$HOST" "tar -C '$DEST' -xzf -"

if [ "$DEST" = "$KODI_ADDON" ]; then
    # Kodi das neue bzw. geänderte Add-on einlesen lassen und es einschalten.
    ssh "$HOST" "kodi-send -a 'UpdateLocalAddons' >/dev/null && sleep 3 && python3 -c '
import json, socket
s = socket.create_connection((\"127.0.0.1\", 9090), timeout=5)
s.sendall(json.dumps({\"jsonrpc\": \"2.0\", \"id\": 1, \"method\": \"Addons.SetAddonEnabled\",
                      \"params\": {\"addonid\": \"script.telegram.calls\", \"enabled\": True}}).encode())
print(s.recv(4096).decode())
'"
fi
echo "Kopiert nach $HOST:$DEST"
```

Run: `chmod +x tools/deploy.sh && bash -n tools/deploy.sh`
Expected: keine Ausgabe (Syntax ok).

- [ ] **Step 5: `tools/messtest/import_check.py` schreiben**

```python
#!/usr/bin/env python3
"""Prüft auf dem Pi, ob das Bündel lädt, auch LiveKits native Bibliothek.

Aufruf: python3 import_check.py <add-on-ordner>
"""
import os
import sys

addon = sys.argv[1]
sys.path.insert(0, os.path.join(addon, 'vendor'))
want = open(os.path.join(addon, 'vendor', 'PYTHON_VERSION')).read().strip()
have = f'{sys.version_info.major}.{sys.version_info.minor}'
print(f'Python: Gerät {have}, Bündel {want}', 'OK' if have == want else 'FEHLER')

import ntgcalls  # noqa: E402
import numpy  # noqa: E402
import png  # noqa: E402, F401  (nur Ladeprüfung)
import pytgcalls  # noqa: E402
import qrcode  # noqa: E402, F401  (nur Ladeprüfung)
import telethon  # noqa: E402
from livekit.rtc import AudioProcessingModule  # noqa: E402

AudioProcessingModule(echo_cancellation=True, noise_suppression=True, high_pass_filter=True)
print('ntgcalls', getattr(ntgcalls, '__version__', '?'), '| telethon', telethon.__version__,
      '| numpy', numpy.__version__, '| pytgcalls', pytgcalls.__version__, '| qrcode, png ok')
print('LiveKit-Echounterdrückung: OK')
```

- [ ] **Step 6: Auf den Pi kopieren und prüfen**

Run:
```bash
ssh root@192.168.178.10 'cd /storage/tgcalls-test && python3 check.py --guard'
tools/deploy.sh /storage/tgcalls-addon
scp tools/messtest/import_check.py root@192.168.178.10:/storage/tgcalls-addon/
ssh root@192.168.178.10 'python3 /storage/tgcalls-addon/import_check.py /storage/tgcalls-addon'
ssh root@192.168.178.10 'cd /storage/tgcalls-test && python3 check.py --guard'
```
Expected: `Python: Gerät 3.11, Bündel 3.11 OK`, Versionszeile, `LiveKit-Echounterdrückung: OK`; beide Wächterläufe OK. Scheitert LiveKit am Laden: Fehlermeldung festhalten und Task 2 Schritt „Echo-CPU“ als gescheitert werten (Rückfallebene Dämpfen).

- [ ] **Step 7: Stand festhalten** – kein Commit. Ergebnis von Step 6 notieren für `docs/messtest-teilprojekt-2.md` (Task 2).

---

### Task 2: Messtest auf dem Pi und Entscheidung (Spike, Wegwerf-Code)

Die Skripte in `tools/messtest/` sind Wegwerf-Code. Ergebnis ist das Dokument `docs/messtest-teilprojekt-2.md` und eine Entscheidung des Nutzers. **Ohne diese Entscheidung nicht mit Task 5 weitermachen** (die Tasks 3 und 4 hängen nicht davon ab).

**Files:**
- Create: `tools/messtest/tonweg.py`, `tools/messtest/geraet.py`, `tools/messtest/kollision.py`, `tools/messtest/frames_probe.py`, `tools/messtest/apm_probe.py`
- Create: `docs/messtest-teilprojekt-2.md`

**Interfaces:**
- Consumes: `/storage/tgcalls-test/` aus Teilprojekt 1 (`common.py` mit `make_client`, `kodi_rpc`, `die`; `rtp_send.py` mit `sdp(port)` und RTP-Versand von stdin; die dortige Session). Das Bündel unter `/storage/tgcalls-addon/vendor` aus Task 1.
- Produces: Messwerte `ALSA_DELAY_MS`, `KODI_DELAY_MS`, das funktionierende ALSA-Gerät `HDMI_DEVICE`, Framegröße und Richtung/Gerät empfangener Frames, CPU der Echounterdrückung, Entscheidung `direkte_ausgabe` (Standardwert der Einstellung, Task 15).

- [ ] **Step 1: `tools/messtest/tonweg.py` schreiben**

```python
#!/usr/bin/env python3
"""Messtest: Verzögerung vom Abspielen bis zum Schall am Webcam-Mikrofon.

Aufruf auf dem Pi:
  python3 tonweg.py alsa [--device hdmi:CARD=vc4hdmi0,DEV=0]
  python3 tonweg.py kodi
Spielt dreimal 1 s Rauschen und sucht es per Kreuzkorrelation in der Aufnahme.
Nutzt rtp_send.py und common.py aus Teilprojekt 1 (/storage/tgcalls-test).
"""
import argparse
import subprocess
import sys
import threading
import time

sys.path.insert(0, '/storage/tgcalls-test')
sys.path.insert(0, '/storage/tgcalls-addon/vendor')
import numpy as np  # noqa: E402
import rtp_send  # noqa: E402
from common import kodi_rpc  # noqa: E402

RATE = 48000
MIC = 'plughw:CARD=Webcam,DEV=0'
PORT = 23533
SDP = '/storage/tgcalls-addon/messtest.sdp'


def burst(seed):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(RATE) * 6000).clip(-32000, 32000).astype(np.int16)


def stereo(mono):
    return np.repeat(mono, 2).tobytes()


def record(seconds, out):
    proc = subprocess.run(['aplay', '-C', '-q', '-D', MIC, '-f', 'S16_LE', '-r', str(RATE), '-c', '1',
                           '-t', 'raw', '-d', str(seconds)], capture_output=True)
    out.append(np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float64))


def find(recording, signal):
    size = 1 << (len(recording) + len(signal)).bit_length()
    corr = np.fft.irfft(np.fft.rfft(recording, size) * np.conj(np.fft.rfft(signal, size)), size)
    corr = corr[:len(recording)]
    lag = int(np.argmax(corr))
    return lag, corr[lag] / (np.std(corr) + 1e-9)


def run_alsa(device, seed):
    sig = burst(seed)
    pcm = stereo(np.concatenate([np.zeros(RATE // 2, np.int16), sig, np.zeros(2 * RATE, np.int16)]))
    rec = []
    t_rec = time.monotonic()
    th = threading.Thread(target=record, args=(5, rec))
    th.start()
    time.sleep(0.5)
    t_play = time.monotonic()
    p = subprocess.run(['aplay', '-q', '-D', device, '-f', 'S16_LE', '-r', str(RATE), '-c', '2', '-t', 'raw',
                        '--buffer-time=60000'], input=pcm, capture_output=True)
    th.join()
    if p.returncode != 0:
        sys.exit(f'aplay auf {device} scheiterte: {p.stderr.decode().strip()}')
    return sig, rec[0], t_rec, t_play + 0.5


def run_kodi(seed):
    if kodi_rpc('Player.GetActivePlayers'):
        sys.exit('Kodi spielt gerade etwas, bitte erst beenden.')
    sig = burst(seed)
    with open(SDP, 'w') as f:
        f.write(rtp_send.sdp(PORT))
    sender = subprocess.Popen(['python3', '/storage/tgcalls-test/rtp_send.py', str(PORT)], stdin=subprocess.PIPE)
    state = {'stop': False}
    queue = []

    def pump():
        start, n = time.monotonic(), 0
        while not state['stop']:
            chunk = queue.pop(0) if queue else bytes(1920)  # 10 ms Stereo, sonst Stille
            sender.stdin.write(chunk)
            sender.stdin.flush()
            n += 1
            time.sleep(max(0, start + n * 0.01 - time.monotonic()))

    th = threading.Thread(target=pump)
    th.start()
    time.sleep(0.5)
    kodi_rpc('Player.Open', {'item': {'file': SDP}})
    time.sleep(4)  # Kodi puffert an
    rec = []
    t_rec = time.monotonic()
    rt = threading.Thread(target=record, args=(6, rec))
    rt.start()
    time.sleep(0.5)
    pcm = stereo(sig)
    t_burst = time.monotonic()  # die Warteschlange ist leer, der nächste 10-ms-Takt sendet den Anfang
    queue.extend(pcm[i:i + 1920] for i in range(0, len(pcm), 1920))
    rt.join()
    state['stop'] = True
    th.join()
    for player in kodi_rpc('Player.GetActivePlayers'):
        kodi_rpc('Player.Stop', {'playerid': player['playerid']})
    sender.stdin.close()
    sender.wait()
    return sig, rec[0], t_rec, t_burst


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('weg', choices=['alsa', 'kodi'])
    parser.add_argument('--device', default='hdmi:CARD=vc4hdmi0,DEV=0')
    args = parser.parse_args()
    delays = []
    for seed in range(3):
        sig, rec, t_rec, t_play = run_alsa(args.device, seed) if args.weg == 'alsa' else run_kodi(seed)
        lag, quality = find(rec, sig.astype(np.float64))
        delay = (t_rec + lag / RATE - t_play) * 1000
        print(f'Lauf {seed + 1}: {delay:.0f} ms (Güte {quality:.1f}, unter 8 unsicher)')
        delays.append(delay)
        time.sleep(1)
    print(f'{args.weg}: Median {sorted(delays)[1]:.0f} ms')


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: `tools/messtest/geraet.py` und `tools/messtest/kollision.py` schreiben**

`geraet.py`:

```python
#!/usr/bin/env python3
"""Messtest: zeigt jede Sekunde, ob Kodi den HDMI-Ausgang belegt. Aufruf: geraet.py [sekunden]"""
import sys
import time

STATUS = '/proc/asound/vc4hdmi0/pcm0p/sub0/status'
seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 90
for _ in range(seconds):
    try:
        first = open(STATUS).readline().strip()
    except OSError as e:
        first = f'nicht lesbar: {e}'
    print(f'{time.strftime("%H:%M:%S")} {first}', flush=True)
    time.sleep(1)
```

`kollision.py`:

```python
#!/usr/bin/env python3
"""Messtest: spielt 30 s einen leisen Ton direkt per ALSA und zeigt danach neue Audio-Zeilen im Kodi-Log.

Während der 30 s in Kodi mit der Fernbedienung navigieren (Bediengeräusche auslösen).
Aufruf: kollision.py [alsa-gerät]
"""
import math
import os
import subprocess
import sys

LOG = '/storage/.kodi/temp/kodi.log'
device = sys.argv[1] if len(sys.argv) > 1 else 'hdmi:CARD=vc4hdmi0,DEV=0'
rate = 48000
frame = bytearray()
for i in range(rate):
    v = int(1500 * math.sin(2 * math.pi * 440 * i / rate))
    frame += v.to_bytes(2, 'little', signed=True) * 2
start = os.path.getsize(LOG)
print('Ton läuft 30 s. Jetzt in Kodi navigieren.', flush=True)
p = subprocess.run(['aplay', '-q', '-D', device, '-f', 'S16_LE', '-r', str(rate), '-c', '2', '-t', 'raw'],
                   input=bytes(frame) * 30, capture_output=True)
print('aplay:', 'OK' if p.returncode == 0 else p.stderr.decode().strip())
with open(LOG, errors='replace') as f:
    f.seek(start)
    lines = [line.rstrip() for line in f if any(k in line for k in ('ALSA', 'ActiveAE', 'CAESink', 'AESink'))]
print(f'{len(lines)} neue Audio-Zeilen im Kodi-Log:')
print('\n'.join(lines[-40:]))
```

- [ ] **Step 3: `tools/messtest/frames_probe.py` schreiben**

```python
#!/usr/bin/env python3
"""Messtest: externe Frames in ntgcalls/py-tgcalls 3.0.x – Ton senden und empfangen ohne Shell.

Läuft in /storage/tgcalls-test (Session und Bündel aus Teilprojekt 1).
Aufruf: python3 frames_probe.py <kontakt>
Sendet 10 s einen 440-Hz-Ton, danach Stille; Strg+C legt auf.
"""
import array
import asyncio
import collections
import math
import signal
import sys
import time

from common import die, make_client

RATE = 48000


def tone_frame(n):
    return array.array('h', (int(8000 * math.sin(2 * math.pi * 440 * (n * 480 + i) / RATE))
                             for i in range(480))).tobytes()


async def main():
    from ntgcalls import MediaSource
    from pytgcalls import PyTgCalls
    from pytgcalls import filters as fl
    from pytgcalls.types import CallConfig, ChatUpdate, Device
    from pytgcalls.types.raw import AudioParameters, AudioStream, Stream

    client = make_client()
    await client.connect()
    if not await client.is_user_authorized():
        die('Nicht angemeldet.')
    peer = await client.get_entity(sys.argv[1])
    calls = PyTgCalls(client)
    stats = collections.Counter()
    sizes = collections.Counter()
    kinds = set()
    ended = asyncio.Event()

    @calls.on_update(fl.stream_frame())
    async def on_frames(_, update):
        kinds.add((str(update.direction), str(update.device)))
        for f in update.frames:
            stats['bytes'] += len(f.frame)
            sizes[len(f.frame)] += 1

    @calls.on_update(fl.chat_update(ChatUpdate.Status.LEFT_CALL))
    async def on_left(_, update):
        print('Anruf beendet:', update.status)
        ended.set()

    await calls.start()
    await calls.play(peer.id, Stream(microphone=AudioStream(MediaSource.EXTERNAL, '', AudioParameters(RATE, 1))),
                     config=CallConfig(timeout=45))
    await calls.record(peer.id, Stream(microphone=AudioStream(MediaSource.EXTERNAL, '', AudioParameters(RATE, 2))))
    print('Verbunden. Sende 10 s Ton (440 Hz), dann Stille. Strg+C legt auf.')
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, ended.set)

    async def sender():
        start, n, errors = time.monotonic(), 0, 0
        while not ended.is_set():
            pcm = tone_frame(n) if n < 1000 else bytes(960)
            try:
                await calls.send_frame(peer.id, Device.MICROPHONE, pcm)
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print('send_frame:', type(e).__name__, e)
            n += 1
            await asyncio.sleep(max(0, start + n * 0.01 - time.monotonic()))

    async def reporter():
        while not ended.is_set():
            await asyncio.sleep(2)
            share = stats['bytes'] / (RATE * 2 * 2 * 2)
            print(f'Empfang {share:.0%} Echtzeit, Framegrößen {dict(sizes)}, Richtung/Gerät {kinds}', flush=True)
            stats.clear()
            sizes.clear()

    await asyncio.gather(sender(), reporter())
    try:
        await calls.leave_call(peer.id)
    except Exception:
        pass
    await client.disconnect()


asyncio.run(main())
```

- [ ] **Step 4: `tools/messtest/apm_probe.py` schreiben**

```python
#!/usr/bin/env python3
"""Messtest: CPU-Bedarf und Wirkung der WebRTC-Echounterdrückung auf dem Pi (künstliches Echo, 20 s)."""
import sys
import time

sys.path.insert(0, '/storage/tgcalls-addon/vendor')
import numpy as np  # noqa: E402
from livekit.rtc import AudioFrame, AudioProcessingModule  # noqa: E402

RATE, FRAME, SECONDS, DELAY = 48000, 480, 20, int(0.3 * 48000)
LEAD = int(0.15 * RATE)  # Referenz 150 ms früher, wie MARGIN_MS in worker/echo.py
rng = np.random.default_rng(1)
n = RATE * SECONDS
t = np.arange(n) / RATE
far = ((np.sin(2 * np.pi * 300 * t) * np.sin(2 * np.pi * 3 * t)
        + 0.5 * rng.standard_normal(n) * (np.sin(2 * np.pi * 0.7 * t) > 0)) * 6000).astype(np.int16)
mic = np.zeros(n, np.int16)
mic[DELAY:] = (0.5 * far[:-DELAY]).astype(np.int16)
apm = AudioProcessingModule(echo_cancellation=True, noise_suppression=True, high_pass_filter=True)
apm.set_stream_delay_ms(150)
out = []
cpu = time.process_time()
for i in range(0, n, FRAME):
    start = i - DELAY + LEAD
    ref = far[start:start + FRAME] if start >= 0 else np.zeros(FRAME, np.int16)
    apm.process_reverse_stream(AudioFrame(ref.tobytes(), RATE, 1, FRAME))
    frame = AudioFrame(mic[i:i + FRAME].tobytes(), RATE, 1, FRAME)
    apm.process_stream(frame)
    out.append(np.frombuffer(bytes(frame.data), np.int16))
cpu = time.process_time() - cpu
res = np.concatenate(out).astype(float)[-3 * RATE:]
src = mic.astype(float)[-3 * RATE:]
damping = 10 * np.log10((np.mean(src ** 2) + 1e-9) / (np.mean(res ** 2) + 1e-9))
print(f'CPU: {100 * cpu / SECONDS:.1f} % eines Kerns, Dämpfung letzte 3 s: {damping:.1f} dB')
```

- [ ] **Step 5: Skripte kopieren, Wächter vorher**

Run:
```bash
ssh root@192.168.178.10 'cd /storage/tgcalls-test && python3 check.py --guard'
scp tools/messtest/{tonweg,geraet,kollision,apm_probe}.py root@192.168.178.10:/storage/tgcalls-addon/
scp tools/messtest/frames_probe.py root@192.168.178.10:/storage/tgcalls-test/
ssh root@192.168.178.10 'amixer -c Webcam cget name="Mic Capture Volume" | tail -1'
```
Expected: Wächter OK; Regler zeigt `values=10` (steht er auf 0: dem Nutzer melden, er entscheidet über das Hochsetzen).

- [ ] **Step 6: Echo-CPU messen** (kein Nutzer nötig)

Run: `ssh root@192.168.178.10 'python3 /storage/tgcalls-addon/apm_probe.py'`
Expected: eine Zeile `CPU: … % eines Kerns, Dämpfung …`. Ziel: unter 15 % eines Kerns, Dämpfung über 30 dB.

- [ ] **Step 7: Nutzer um die Messungen mit Ton bitten**

Der Nutzer muss dabei sein (Denon an, Webcam-Mikrofon hört die Boxen, Raum ruhig, Kodi spielt nichts). Ihm die Befehle geben und um die Ausgaben bitten; selbst per SSH starten nur, wenn er „los“ sagt:

1. `python3 /storage/tgcalls-addon/geraet.py 90` – währenddessen einmal in Kodi navigieren, dann nichts mehr drücken. Notieren, wie viele Sekunden nach dem letzten Tastendruck `closed` erscheint.
2. Wenn `closed`: `python3 /storage/tgcalls-addon/tonweg.py alsa`. Scheitert `aplay` mit dem Gerät `hdmi:CARD=vc4hdmi0,DEV=0`, mit `--device plughw:CARD=vc4hdmi0,DEV=0` wiederholen. Das funktionierende Gerät notieren.
3. `python3 /storage/tgcalls-addon/tonweg.py kodi`
4. `python3 /storage/tgcalls-addon/kollision.py <gerät aus 2>` – während der 30 s in Kodi navigieren. Danach fragen: Hat Kodi gehangen, gab es hörbare Störungen? Log-Zeilen notieren.
5. `cd /storage/tgcalls-test && python3 frames_probe.py <kontakt>` – Gegenseite soll sagen, ob sie 10 s einen Ton hört und dann Stille; am Pi ist die Gegenseite in diesem Test nicht zu hören (ihr Ton geht nirgends hin). Ausgabe notieren: Empfang ~100 % Echtzeit? Framegrößen? Richtung/Gerät? Fehler bei `send_frame`?

Danach Wächter: `ssh root@192.168.178.10 'cd /storage/tgcalls-test && python3 check.py --guard'` → OK.

- [ ] **Step 8: `docs/messtest-teilprojekt-2.md` schreiben**

```markdown
# Messtest Teilprojekt 2

Stand: <Datum>. Gerät wie in Teilprojekt 1.

| Messung | Ergebnis |
|---|---|
| Bündel lädt (import_check) | <OK/Fehler> |
| HDMI frei nach letztem Ton | <n s> |
| Verzögerung direkt (ALSA, Gerät <gerät>) | <Median> ms |
| Verzögerung über Kodi | <Median> ms |
| Kodi bei Bediengeräusch während direkter Ausgabe | <Verhalten, Log-Auszug> |
| Externe Frames senden | <Gegenseite hört Ton: ja/nein, Fehler> |
| Externe Frames empfangen | <% Echtzeit, Framegröße, Richtung/Gerät> |
| Echounterdrückung CPU / Dämpfung | <% / dB> |

## Entscheidung

<siehe Step 9>
```

- [ ] **Step 9: Entscheidung einholen – STOPP bis zur Antwort**

Regel aus der Spec: Direkte Ausgabe wird Standard, wenn sie mindestens 0,5 s schneller ist und Kodi sie ohne Fehler verträgt. Dann dem Nutzer vorlegen: Messwerte, und die Frage, ob er „Bediengeräusche: nie“ (`audiooutput.guisoundmode`) selbst einstellen möchte, damit der Ausgang beim Anrufen meist frei ist. Nichts selbst ändern.

Ergebnis in `docs/messtest-teilprojekt-2.md` unter „Entscheidung“ eintragen:
- `direkte_ausgabe` Standard: `true`, wenn direkt mindestens 0,5 s schneller und verträglich, sonst `false`.
- `HDMI_DEVICE`, `ALSA_DELAY_MS`, `KODI_DELAY_MS` (Mediane, auf 10 ms gerundet).
- Abbruchkriterium: Funktionieren externe Frames nicht (Gegenseite hört nichts oder kein Empfang), **Plan anhalten** und mit dem Nutzer den Rückfall aus der Spec besprechen (Shell-Quellen plus Hilfsprozess); die Tasks 5–11 müssen dann überarbeitet werden.
- Echo: Liegt die CPU über 25 % eines Kerns oder lädt LiveKit nicht, wird `daempfen` der Standard der Einstellung `echo` (Task 15), sonst `webrtc`.


---

### Task 3: Nachrichtenprotokoll

**Files:**
- Test: `tests/test_protocol.py`

**Interfaces:**
- Produces: `tgc.protocol.encode(typ, **data) -> bytes` (eine JSON-Zeile mit `\n`), `decode(line: bytes) -> dict` (wirft `ProtocolError`), `check_command(message: dict)` (wirft `ProtocolError` bei unbekanntem Befehl oder fehlendem Pflichtfeld), `redact(message) -> dict`, `COMMANDS`, `EVENTS`. Feldnamen genau wie in der Spec: `login_phone{nummer}`, `login_code{code}`, `login_password{passwort}`, `call{id}`, `mute{an}`; Ereignisse u. a. `qr{url, bild}`, `login_error{grund, erneut?}`, `contacts{liste: [{id, name, bild, gruppe}]}`, `incoming{id, name}`, `outgoing_state{zustand: waehlt|klingelt}`, `ended{grund}`, `play_kodi{sdp_pfad}`, `status{telegram_verbunden, mikrofon_ok}`, `error{text}`, `ready{angemeldet}`.

- [ ] **Step 1: Tests schreiben**

`tests/test_protocol.py`:

```python
import pytest

from tgc import protocol


def test_hin_und_zurueck():
    line = protocol.encode('call', id=42)
    assert line.endswith(b'\n')
    assert protocol.decode(line) == {'typ': 'call', 'id': 42}


def test_umlaute_bleiben_lesbar():
    assert 'Jürgen'.encode() in protocol.encode('incoming', id=1, name='Jürgen')


@pytest.mark.parametrize('line', [b'kein json\n', b'[1, 2]\n', b'{"id": 1}\n', b'{"typ": 3}\n', b'\xff\n'])
def test_decode_weist_muell_ab(line):
    with pytest.raises(protocol.ProtocolError):
        protocol.decode(line)


def test_unbekannter_befehl():
    with pytest.raises(protocol.ProtocolError, match='unbekannter Befehl'):
        protocol.check_command({'typ': 'rm_rf'})


def test_fehlendes_pflichtfeld():
    with pytest.raises(protocol.ProtocolError, match='id'):
        protocol.check_command({'typ': 'call'})


def test_gueltiger_befehl():
    protocol.check_command({'typ': 'mute', 'an': True})


def test_redact_versteckt_geheimes_ohne_original_zu_aendern():
    message = {'typ': 'login_password', 'passwort': 'geheim'}
    assert protocol.redact(message) == {'typ': 'login_password', 'passwort': '***'}
    assert message['passwort'] == 'geheim'
```

- [ ] **Step 2: Tests laufen lassen, sie müssen scheitern**

Run: `.venv/bin/pytest -q tests/test_protocol.py`
Expected: FAIL mit `ImportError: cannot import name 'protocol' from 'tgc'`

- [ ] **Step 3: Implementierung schreiben**

`addon/script.telegram.calls/resources/lib/tgc/protocol.py`:

```python
"""Nachrichten zwischen Add-on und Anrufprozess.

Eine Nachricht ist ein JSON-Objekt auf einer Zeile mit dem Feld "typ". Add-on
(Kodi-Python) und Anrufprozess benutzen diese Datei gemeinsam; sie importiert
deshalb nur die Standardbibliothek.
"""
import json

# Befehl (Add-on -> Prozess) -> Pflichtfelder
COMMANDS = {
    'login_qr': (),
    'login_phone': ('nummer',),
    'login_code': ('code',),
    'login_password': ('passwort',),
    'contacts': (),
    'call': ('id',),
    'accept': (),
    'decline': (),
    'hangup': (),
    'mute': ('an',),
    'logout': (),
    'quit': (),
}
# Ereignisse (Prozess -> Add-on)
EVENTS = frozenset({
    'ready', 'qr', 'need_code', 'need_password', 'login_ok', 'login_error',
    'contacts', 'incoming', 'outgoing_state', 'connected', 'ended',
    'play_kodi', 'stop_kodi', 'status', 'error',
})
SECRET_FIELDS = frozenset({'nummer', 'code', 'passwort'})


class ProtocolError(ValueError):
    pass


def encode(typ, **data):
    return (json.dumps({'typ': typ, **data}, ensure_ascii=False) + '\n').encode('utf-8')


def decode(line):
    try:
        message = json.loads(line)
    except (ValueError, UnicodeDecodeError) as e:
        raise ProtocolError(f'kein gültiges JSON: {e}') from None
    if not isinstance(message, dict) or not isinstance(message.get('typ'), str):
        raise ProtocolError('Nachricht ohne Feld "typ"')
    return message


def check_command(message):
    fields = COMMANDS.get(message['typ'])
    if fields is None:
        raise ProtocolError(f'unbekannter Befehl: {message["typ"]}')
    missing = [f for f in fields if f not in message]
    if missing:
        raise ProtocolError(f'{message["typ"]}: es fehlt {", ".join(missing)}')


def redact(message):
    """Kopie für das Log: Telefonnummer, Code und Passwort ausgeblendet."""
    return {k: ('***' if k in SECRET_FIELDS else v) for k, v in message.items()}
```

- [ ] **Step 4: Tests und ruff grün**

Run: `.venv/bin/pytest -q tests/test_protocol.py && .venv/bin/ruff check .`
Expected: `11 passed`, ruff `All checks passed!`

- [ ] **Step 5: Stand festhalten** – kein Commit; volle Testsuite `.venv/bin/pytest -q` grün.

---

### Task 4: Favoritenliste

**Files:**
- Test: `tests/test_favorites.py`

**Interfaces:**
- Produces: `tgc.favorites.Favorites(path)` mit Attribut `ids: list[int]` und Methoden `add(user_id)`, `remove(user_id)`, `move(user_id, step)`; speichert sofort, Datei mit Rechten `600`; kaputte Datei ergibt leere Liste.

- [ ] **Step 1: Tests schreiben**

`tests/test_favorites.py`:

```python
import os
import stat

from tgc.favorites import Favorites


def test_hinzufuegen_ohne_doppelte_und_dauerhaft(tmp_path):
    path = str(tmp_path / 'favoriten.json')
    fav = Favorites(path)
    fav.add(5)
    fav.add(7)
    fav.add(5)
    assert fav.ids == [5, 7]
    assert Favorites(path).ids == [5, 7]


def test_entfernen(tmp_path):
    fav = Favorites(str(tmp_path / 'f.json'))
    fav.add(1)
    fav.add(2)
    fav.remove(1)
    fav.remove(99)
    assert fav.ids == [2]


def test_verschieben_bleibt_in_den_grenzen(tmp_path):
    fav = Favorites(str(tmp_path / 'f.json'))
    for i in (1, 2, 3):
        fav.add(i)
    fav.move(3, -1)
    assert fav.ids == [1, 3, 2]
    fav.move(1, -5)
    assert fav.ids == [1, 3, 2]
    fav.move(1, 10)
    assert fav.ids == [3, 2, 1]
    fav.move(42, 1)
    assert fav.ids == [3, 2, 1]


def test_kaputte_datei_ergibt_leere_liste(tmp_path):
    path = tmp_path / 'f.json'
    path.write_text('{kaputt')
    assert Favorites(str(path)).ids == []
    path.write_text('{"a": 1}')
    assert Favorites(str(path)).ids == []


def test_unbrauchbare_eintraege_werden_ignoriert(tmp_path):
    path = tmp_path / 'f.json'
    path.write_text('[1, "2", true, 1, 3.5, 4]')
    assert Favorites(str(path)).ids == [1, 4]


def test_datei_nur_fuer_eigentuemer_lesbar(tmp_path):
    path = tmp_path / 'f.json'
    Favorites(str(path)).add(1)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
```

- [ ] **Step 2: Tests laufen lassen, sie müssen scheitern**

Run: `.venv/bin/pytest -q tests/test_favorites.py`
Expected: FAIL mit `ModuleNotFoundError: No module named 'tgc.favorites'`

- [ ] **Step 3: Implementierung schreiben**

`addon/script.telegram.calls/resources/lib/tgc/favorites.py`:

```python
"""Favoritenliste des Add-ons: Telegram-IDs in fester Reihenfolge, nur auf diesem Gerät."""
import json
import os


class Favorites:
    def __init__(self, path):
        self._path = path
        self.ids = self._load()

    def _load(self):
        try:
            with open(self._path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        ids = []
        for item in data:
            if isinstance(item, int) and not isinstance(item, bool) and item not in ids:
                ids.append(item)
        return ids

    def add(self, user_id):
        if user_id not in self.ids:
            self.ids.append(user_id)
            self._save()

    def remove(self, user_id):
        if user_id in self.ids:
            self.ids.remove(user_id)
            self._save()

    def move(self, user_id, step):
        """Verschiebt um step Plätze (negativ = nach vorne), begrenzt auf die Liste."""
        if user_id not in self.ids:
            return
        old = self.ids.index(user_id)
        new = min(max(old + step, 0), len(self.ids) - 1)
        if new != old:
            self.ids.insert(new, self.ids.pop(old))
            self._save()

    def _save(self):
        tmp = self._path + '.tmp'
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(self.ids, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._path)
```

- [ ] **Step 4: Tests und ruff grün**

Run: `.venv/bin/pytest -q tests/test_favorites.py && .venv/bin/ruff check .`
Expected: `6 passed`, ruff `All checks passed!`

- [ ] **Step 5: Stand festhalten** – kein Commit; volle Testsuite `.venv/bin/pytest -q` grün.

---

### Task 5: RTP-Versand und Tonausgaben

Hängt vom Messtest ab: Vor Step 3 die Werte aus `docs/messtest-teilprojekt-2.md` übernehmen: `HDMI_DEVICE` (funktionierendes Gerät), `ALSA_DELAY_MS` und `KODI_DELAY_MS` (Mediane, auf 10 ms gerundet). Die Werte unten (300 und 1770 ms) sind die Annahmen bis dahin; 1770 ms stammt aus Teilprojekt 1.

**Files:**
- Test: `tests/test_rtp.py`
- Test: `tests/test_sinks.py`

**Interfaces:**
- Produces: `rtp.sdp(port) -> str`, `rtp.RtpSender(port, address='127.0.0.1')` mit `send(pcm)` und `close()`; `sinks.AlsaSink`, `sinks.KodiSink(sdp_path, emit)` mit `start()`, `write(pcm)`, `stop()`, Attribut `delay_ms`; `sinks.SinkError`; `sinks.hdmi_busy(status_path) -> bool`; `sinks.open_sink(prefer_direct, sdp_path, emit, busy=hdmi_busy, alsa_command=None) -> Sink`. `emit` ist überall `emit(typ, **daten)` wie `Server.emit` (Task 10). pcm: s16le, 48 kHz, Stereo.

- [ ] **Step 1: Tests schreiben**

`tests/test_rtp.py`:

```python
import socket
import struct

import rtp


def test_sdp_beschreibt_48khz_stereo():
    text = rtp.sdp(23533)
    assert 'm=audio 23533 RTP/AVP 96' in text
    assert 'a=rtpmap:96 L16/48000/2' in text


def test_pakete_mit_fortlaufendem_kopf_und_netzwerk_byte_reihenfolge():
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(('127.0.0.1', 0))
    receiver.settimeout(2)
    sender = rtp.RtpSender(receiver.getsockname()[1])
    pcm = struct.pack('<h', 0x0102) + bytes(4 * rtp.BYTES_PER_PACKET)  # 4 Pakete + 2 Byte Rest
    sender.send(pcm)
    packets = [receiver.recv(2048) for _ in range(4)]
    heads = [struct.unpack('!BBHII', p[:12]) for p in packets]
    assert all(h[0] == 0x80 and h[1] == 96 for h in heads)
    assert [(h[2] - heads[0][2]) & 0xFFFF for h in heads] == [0, 1, 2, 3]
    assert [(h[3] - heads[0][3]) & 0xFFFFFFFF for h in heads] == [0, 240, 480, 720]
    assert all(len(p) == 12 + rtp.BYTES_PER_PACKET for p in packets)
    assert packets[0][12:14] == b'\x01\x02'
    sender.send(bytes(rtp.BYTES_PER_PACKET - 2))  # füllt den Rest zu einem fünften Paket auf
    assert len(receiver.recv(2048)) == 12 + rtp.BYTES_PER_PACKET
    sender.close()
    receiver.close()
```

`tests/test_sinks.py`:

```python
import sys

import pytest

import sinks


def collect():
    events = []
    return events, lambda typ, **data: events.append((typ, data))


def test_hdmi_busy_liest_den_alsa_zustand(tmp_path):
    status = tmp_path / 'status'
    status.write_text('closed\n')
    assert sinks.hdmi_busy(str(status)) is False
    status.write_text('state: RUNNING\nowner_pid   : 123\n')
    assert sinks.hdmi_busy(str(status)) is True
    assert sinks.hdmi_busy(str(tmp_path / 'fehlt')) is True


def test_kodi_ausgabe_schreibt_sdp_und_meldet_play_kodi(tmp_path):
    events, emit = collect()
    sdp_path = str(tmp_path / 'anruf.sdp')
    sink = sinks.open_sink(False, sdp_path, emit)
    assert isinstance(sink, sinks.KodiSink)
    assert 'L16/48000/2' in open(sdp_path).read()
    assert events == [('play_kodi', {'sdp_pfad': sdp_path})]
    sink.write(bytes(1920))
    sink.stop()
    assert events[-1] == ('stop_kodi', {})


def test_open_sink_nimmt_alsa_wenn_frei(tmp_path):
    events, emit = collect()
    command = [sys.executable, '-c', 'import sys; sys.stdin.buffer.read()']
    sink = sinks.open_sink(True, str(tmp_path / 'a.sdp'), emit, busy=lambda: False, alsa_command=command)
    assert isinstance(sink, sinks.AlsaSink)
    sink.write(bytes(1920))
    sink.stop()
    assert events == []


def test_open_sink_faellt_bei_belegtem_hdmi_auf_kodi_zurueck(tmp_path):
    events, emit = collect()
    sink = sinks.open_sink(True, str(tmp_path / 'a.sdp'), emit, busy=lambda: True)
    assert isinstance(sink, sinks.KodiSink)
    sink.stop()


def test_open_sink_faellt_zurueck_wenn_aplay_sofort_endet(tmp_path):
    events, emit = collect()
    command = [sys.executable, '-c', 'import sys; sys.stderr.write("Gerät belegt"); sys.exit(1)']
    sink = sinks.open_sink(True, str(tmp_path / 'a.sdp'), emit, busy=lambda: False, alsa_command=command)
    assert isinstance(sink, sinks.KodiSink)
    assert events[0][0] == 'play_kodi'
    sink.stop()


def test_alsa_schreiben_nach_ende_meldet_fehler():
    sink = sinks.AlsaSink(command=[sys.executable, '-c', 'import time; time.sleep(0.4)'])
    sink.start()
    sink._proc.wait()
    with pytest.raises(sinks.SinkError):
        for _ in range(100):
            sink.write(bytes(65536))
    sink.stop()
```

- [ ] **Step 2: Tests laufen lassen, sie müssen scheitern**

Run: `.venv/bin/pytest -q tests/test_rtp.py tests/test_sinks.py`
Expected: FAIL mit `ModuleNotFoundError: No module named 'rtp'`

- [ ] **Step 3: Implementierung schreiben**

`addon/script.telegram.calls/worker/rtp.py`:

```python
"""RTP-Versand des Anruftons an Kodi: L16, 48 kHz, Stereo, beschrieben durch eine SDP-Datei.

Ohne SDP spielt Kodi RTP nur mit 44,1 kHz; das klingt über HDMI zum Denon nach
dessen Einschalten zu hoch und knistert (docs/ergebnisse-teilprojekt-1.md).
"""
import array
import random
import socket
import struct
import sys

RATE = 48000
CHANNELS = 2
PAYLOAD_TYPE = 96
SAMPLES_PER_PACKET = 240  # 5 ms, 960 Byte Nutzlast
BYTES_PER_PACKET = SAMPLES_PER_PACKET * CHANNELS * 2


def sdp(port):
    """SDP-Beschreibung des Streams, die Kodi (ffmpeg) zum Abspielen braucht."""
    return (
        'v=0\r\n'
        'o=- 0 0 IN IP4 127.0.0.1\r\n'
        's=Telegram-Anruf\r\n'
        'c=IN IP4 127.0.0.1\r\n'
        't=0 0\r\n'
        f'm=audio {port} RTP/AVP {PAYLOAD_TYPE}\r\n'
        f'a=rtpmap:{PAYLOAD_TYPE} L16/{RATE}/{CHANNELS}\r\n'
    )


class RtpSender:
    def __init__(self, port, address='127.0.0.1'):
        self._target = (address, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._ssrc = random.getrandbits(32)
        self._sequence = random.getrandbits(16)
        self._timestamp = random.getrandbits(32)
        self._pending = bytearray()

    def send(self, pcm):
        """pcm: s16le, 48 kHz, Stereo, beliebige Länge; ein Rest wartet auf den nächsten Aufruf."""
        self._pending += pcm
        while len(self._pending) >= BYTES_PER_PACKET:
            samples = array.array('h', bytes(self._pending[:BYTES_PER_PACKET]))
            del self._pending[:BYTES_PER_PACKET]
            if sys.byteorder == 'little':
                samples.byteswap()  # RTP verlangt L16 in Netzwerk-Byte-Reihenfolge
            header = struct.pack('!BBHII', 0x80, PAYLOAD_TYPE, self._sequence, self._timestamp, self._ssrc)
            self._sock.sendto(header + samples.tobytes(), self._target)
            self._sequence = (self._sequence + 1) & 0xFFFF
            self._timestamp = (self._timestamp + SAMPLES_PER_PACKET) & 0xFFFFFFFF

    def close(self):
        self._sock.close()
```

`addon/script.telegram.calls/worker/sinks.py`:

```python
"""Ausgabe des Anruftons: direkt per ALSA auf HDMI oder über Kodi (RTP + SDP).

Beide Ausgaben haben dieselbe Schnittstelle: start(), write(pcm), stop() und
delay_ms (Verzögerung bis zum Schall am Mikrofon, gemessen in Task 2,
docs/messtest-teilprojekt-2.md). pcm ist s16le, 48 kHz, Stereo.
"""
import logging
import subprocess
import time

from rtp import RtpSender, sdp

log = logging.getLogger('worker.sinks')

HDMI_DEVICE = 'hdmi:CARD=vc4hdmi0,DEV=0'
HDMI_STATUS = '/proc/asound/vc4hdmi0/pcm0p/sub0/status'
RTP_PORT = 23533  # Soloist nutzt 23433
ALSA_DELAY_MS = 300
KODI_DELAY_MS = 1770
STARTUP_CHECK_S = 0.2


class SinkError(RuntimeError):
    pass


def hdmi_busy(status_path=HDMI_STATUS):
    """True, wenn jemand (meist Kodi) den HDMI-Ausgang offen hält oder der Zustand unklar ist."""
    try:
        with open(status_path) as f:
            return f.read().strip() != 'closed'
    except OSError:
        return True


class AlsaSink:
    delay_ms = ALSA_DELAY_MS

    def __init__(self, device=HDMI_DEVICE, command=None):
        self._command = command or ['aplay', '-q', '-D', device, '-f', 'S16_LE', '-r', '48000', '-c', '2',
                                    '-t', 'raw', '--buffer-time=60000']
        self._proc = None

    def start(self):
        self._proc = subprocess.Popen(self._command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(STARTUP_CHECK_S)
        if self._proc.poll() is not None:
            raise SinkError(f'aplay endete sofort: {self._proc.stderr.read().decode(errors="replace").strip()}')

    def write(self, pcm):
        try:
            self._proc.stdin.write(pcm)
            self._proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            raise SinkError('aplay ist beendet') from None

    def stop(self):
        if self._proc is None:
            return
        try:
            self._proc.stdin.close()
        except OSError:
            pass
        self._proc.terminate()
        try:
            self._proc.wait(2)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
        self._proc = None


class KodiSink:
    """Sendet per RTP; das Add-on spielt die SDP-Datei mit xbmc.Player ab (Ereignis play_kodi)."""

    delay_ms = KODI_DELAY_MS

    def __init__(self, sdp_path, emit, port=RTP_PORT):
        self._sdp_path = sdp_path
        self._emit = emit
        self._port = port
        self._rtp = None

    def start(self):
        with open(self._sdp_path, 'w') as f:
            f.write(sdp(self._port))
        self._rtp = RtpSender(self._port)
        self._emit('play_kodi', sdp_pfad=self._sdp_path)

    def write(self, pcm):
        self._rtp.send(pcm)

    def stop(self):
        if self._rtp is None:
            return
        self._emit('stop_kodi')
        self._rtp.close()
        self._rtp = None


def open_sink(prefer_direct, sdp_path, emit, busy=hdmi_busy, alsa_command=None):
    """Startet die direkte Ausgabe, wenn gewünscht und möglich, sonst die über Kodi."""
    if prefer_direct and not busy():
        sink = AlsaSink(command=alsa_command)
        try:
            sink.start()
            log.info('Ausgabe direkt per ALSA')
            return sink
        except (OSError, SinkError) as e:
            log.warning('Direkte Ausgabe nicht möglich, nehme Kodi: %s', e)
            sink.stop()
    sink = KodiSink(sdp_path, emit)
    sink.start()
    log.info('Ausgabe über Kodi')
    return sink
```

- [ ] **Step 4: Tests und ruff grün**

Run: `.venv/bin/pytest -q tests/test_rtp.py tests/test_sinks.py && .venv/bin/ruff check .`
Expected: `8 passed`, ruff `All checks passed!`

- [ ] **Step 5: Stand festhalten** – kein Commit; volle Testsuite `.venv/bin/pytest -q` grün.

---

### Task 6: Echounterdrückung

Die WebRTC-Tests brauchen das LiveKit-Paket aus `.venv`. Sie wurden beim Planen mit livekit 1.1.21 ausprobiert: Dämpfung über 80 dB bei bekannter Verzögerung, unter 10 dB ohne Referenz.

**Files:**
- Test: `tests/test_echo.py`

**Interfaces:**
- Produces: `echo.make_echo(mode, delay_ms)` mit `mode` in `webrtc | daempfen | aus`; alle Verfahren haben `add_reference(mono: bytes)` und `process(mic: bytes) -> bytes` (genau 960 Byte = 10 ms Mono, sonst `ValueError`); `echo.stereo_to_mono(pcm) -> bytes`; Konstanten `FRAME`, `FRAME_BYTES`. `add_reference` wird aus dem Netz-Thread, `process` aus dem Mikrofon-Thread aufgerufen.

- [ ] **Step 1: Tests schreiben**

`tests/test_echo.py`:

```python
import numpy as np
import pytest

import echo

RATE = 48000


def speechlike(seconds, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(RATE * seconds) / RATE
    burst = np.sin(2 * np.pi * 0.7 * t) > 0
    signal = np.sin(2 * np.pi * 300 * t) * np.sin(2 * np.pi * 3 * t) + 0.5 * rng.standard_normal(t.size) * burst
    return (signal * 6000).astype(np.int16)


def damping_db(canceller, far, mic):
    """Schickt far als Referenz und mic durch process(); Dämpfung der letzten 3 s in dB."""
    out = []
    for i in range(0, far.size, echo.FRAME):
        canceller.add_reference(far[i:i + echo.FRAME].tobytes())
        out.append(np.frombuffer(canceller.process(mic[i:i + echo.FRAME].tobytes()), np.int16))
    result = np.concatenate(out).astype(np.float64)[-3 * RATE:]
    source = mic.astype(np.float64)[-3 * RATE:]
    return 10 * np.log10((np.mean(source ** 2) + 1e-9) / (np.mean(result ** 2) + 1e-9))


def echo_of(far, delay_ms, gain=0.5):
    delay = delay_ms * RATE // 1000
    mic = np.zeros_like(far)
    mic[delay:] = (far[:-delay] * gain).astype(np.int16)
    return mic


def test_webrtc_entfernt_echo_bei_bekannter_verzoegerung():
    far = speechlike(10)
    assert damping_db(echo.EchoCanceller(300), far, echo_of(far, 300)) > 30


def test_webrtc_vertraegt_zu_kurz_geschaetzte_verzoegerung():
    far = speechlike(10)
    assert damping_db(echo.EchoCanceller(150), far, echo_of(far, 300)) > 30


def test_ohne_referenz_bleibt_das_echo():
    far = speechlike(10)
    silent = np.zeros_like(far)
    canceller = echo.EchoCanceller(300)
    out = []
    mic = echo_of(far, 300)
    for i in range(0, far.size, echo.FRAME):
        canceller.add_reference(silent[i:i + echo.FRAME].tobytes())
        out.append(np.frombuffer(canceller.process(mic[i:i + echo.FRAME].tobytes()), np.int16))
    result = np.concatenate(out).astype(np.float64)[-3 * RATE:]
    source = mic.astype(np.float64)[-3 * RATE:]
    assert 10 * np.log10(np.mean(source ** 2) / np.mean(result ** 2)) < 15


def test_falsche_blocklaenge_wird_abgewiesen():
    with pytest.raises(ValueError):
        echo.PassThrough().process(bytes(100))


def test_stereo_zu_mono_mittelt():
    stereo = np.array([100, 300, -50, 50], dtype=np.int16).tobytes()
    assert np.frombuffer(echo.stereo_to_mono(stereo), np.int16).tolist() == [200, 0]


def test_ducker_daempft_waehrend_und_nach_der_gegenseite():
    ducker = echo.Ducker(delay_ms=100, threshold=500, gain=0.1, tail_ms=0)
    loud = (np.ones(echo.FRAME) * 3000).astype(np.int16).tobytes()
    quiet = bytes(echo.FRAME_BYTES)
    mic = (np.ones(echo.FRAME) * 1000).astype(np.int16).tobytes()
    assert ducker.process(mic) == mic
    ducker.add_reference(loud)
    for _ in range(10):  # 100 ms Nachlauf
        assert np.frombuffer(ducker.process(mic), np.int16)[0] == 100
    ducker.add_reference(quiet)
    assert ducker.process(mic) == mic


def test_make_echo_waehlt_verfahren():
    assert isinstance(echo.make_echo('webrtc', 300), echo.EchoCanceller)
    assert isinstance(echo.make_echo('daempfen', 300), echo.Ducker)
    assert isinstance(echo.make_echo('aus', 300), echo.PassThrough)
```

- [ ] **Step 2: Tests laufen lassen, sie müssen scheitern**

Run: `.venv/bin/pytest -q tests/test_echo.py`
Expected: FAIL mit `ModuleNotFoundError: No module named 'echo'`

- [ ] **Step 3: Implementierung schreiben**

`addon/script.telegram.calls/worker/echo.py`:

```python
"""Echounterdrückung: Das Webcam-Mikrofon hört die Boxen, die Gegenseite soll sich nicht selbst hören.

Alle Verfahren haben dieselbe Schnittstelle: add_reference(mono) bekommt den
Ton der Gegenseite, process(mic) einen 10-ms-Block vom Mikrofon und gibt den
bereinigten Block zurück. Ton: s16le, 48 kHz, Mono.

WebRTC (LiveKit) verkraftet eine zu früh kommende Referenz (ausprobiert:
300 ms), aber keine zu späte (100 ms zu spät: nur noch 12 dB Dämpfung). Die
Referenz wird deshalb um die Verzögerung der Ausgabe abzüglich MARGIN_MS
verzögert.
"""
import threading

import numpy as np

RATE = 48000
FRAME = RATE // 100
FRAME_BYTES = FRAME * 2
MARGIN_MS = 150
MAX_EXTRA_MS = 200  # so viel darf sich die Referenz über die Vorgabe hinaus stauen


def stereo_to_mono(pcm):
    samples = np.frombuffer(pcm, dtype=np.int16).reshape(-1, 2).astype(np.int32)
    return ((samples[:, 0] + samples[:, 1]) // 2).astype(np.int16).tobytes()


class _ReferenceDelay:
    """Verzögert die Referenz; wird vom Netz-Thread gefüllt und vom Mikrofon-Thread geleert."""

    def __init__(self, delay_ms):
        self._lock = threading.Lock()
        self._buf = bytearray(max(0, delay_ms) * RATE // 1000 * 2)
        self._max = len(self._buf) + MAX_EXTRA_MS * RATE // 1000 * 2

    def push(self, mono):
        with self._lock:
            self._buf += mono
            if len(self._buf) > self._max:
                del self._buf[:len(self._buf) - self._max]

    def pop(self):
        with self._lock:
            out = bytes(self._buf[:FRAME_BYTES])
            del self._buf[:FRAME_BYTES]
        return out.ljust(FRAME_BYTES, b'\0')


def _check(mic):
    if len(mic) != FRAME_BYTES:
        raise ValueError(f'Mikrofonblock muss {FRAME_BYTES} Byte haben, nicht {len(mic)}')


class EchoCanceller:
    def __init__(self, delay_ms, margin_ms=MARGIN_MS, apm=None):
        from livekit.rtc import AudioFrame, AudioProcessingModule

        self._frame = AudioFrame
        self._apm = apm or AudioProcessingModule(echo_cancellation=True, noise_suppression=True,
                                                 high_pass_filter=True)
        self._apm.set_stream_delay_ms(margin_ms)
        self._ref = _ReferenceDelay(delay_ms - margin_ms)

    def add_reference(self, mono):
        self._ref.push(mono)

    def process(self, mic):
        _check(mic)
        self._apm.process_reverse_stream(self._frame(self._ref.pop(), RATE, 1, FRAME))
        frame = self._frame(mic, RATE, 1, FRAME)
        self._apm.process_stream(frame)
        return bytes(frame.data)


class Ducker:
    """Rückfallebene: dämpft das Mikrofon, solange die Gegenseite spricht, samt Nachlauf."""

    def __init__(self, delay_ms, threshold=500, gain=0.1, tail_ms=300):
        self._threshold = threshold
        self._gain = gain
        self._hold_frames = (delay_ms + tail_ms) // 10
        self._lock = threading.Lock()
        self._hold = 0

    def add_reference(self, mono):
        samples = np.frombuffer(mono, dtype=np.int16).astype(np.float64)
        if samples.size and np.sqrt(np.mean(samples ** 2)) > self._threshold:
            with self._lock:
                self._hold = self._hold_frames

    def process(self, mic):
        _check(mic)
        with self._lock:
            active = self._hold > 0
            self._hold = max(0, self._hold - 1)
        if not active:
            return mic
        return (np.frombuffer(mic, dtype=np.int16) * self._gain).astype(np.int16).tobytes()


class PassThrough:
    def __init__(self, delay_ms=0):
        pass

    def add_reference(self, mono):
        pass

    def process(self, mic):
        _check(mic)
        return mic


def make_echo(mode, delay_ms):
    """mode: 'webrtc' | 'daempfen' | 'aus' (Einstellung echo des Add-ons)."""
    if mode == 'webrtc':
        return EchoCanceller(delay_ms)
    if mode == 'daempfen':
        return Ducker(delay_ms)
    return PassThrough()
```

- [ ] **Step 4: Tests und ruff grün**

Run: `.venv/bin/pytest -q tests/test_echo.py && .venv/bin/ruff check .`
Expected: `7 passed`, ruff `All checks passed!`

- [ ] **Step 5: Stand festhalten** – kein Commit; volle Testsuite `.venv/bin/pytest -q` grün.

---

### Task 7: Mikrofon, Klingelton und Ton-Fabrik

**Files:**
- Test: `tests/test_mic.py`
- Test: `tests/test_ringtone.py`
- Test: `tests/test_audio.py`

**Interfaces:**
- Consumes: `sinks.open_sink` (Task 5), `echo.make_echo` (Task 6).
- Produces: `mic.MicCapture(on_frame, device=DEVICE, command=None)` mit `start()`, `stop()`, ruft `on_frame(960 Byte)` im eigenen Thread; `mic.card_of(device)`, `mic.mic_volume(card, run)`, `mic.mic_ok(card, cards_path, run) -> bool`; `ringtone.RingTone().run(sink)` (Coroutine, läuft bis zum Abbruch); `audio.AudioFactory(init, data_dir, emit)` mit `open_sink()`, `make_echo(delay_ms)`, `make_mic(on_frame)`, `ringtone()`. `init` enthält `direkt`, `echo`, `mikrofon` (Task 10).

- [ ] **Step 1: Tests schreiben**

`tests/test_mic.py`:

```python
import subprocess
import sys
import threading

import mic

AMIXER_OUTPUT = """numid=3,iface=MIXER,name='Mic Capture Volume'
  ; type=INTEGER,access=rw---R--,values=1,min=0,max=15,step=0
  : values=%d
"""


def fake_amixer(value):
    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout=AMIXER_OUTPUT % value, stderr='')
    return run


def test_liefert_bloecke_zu_10_ms():
    frames = []
    done = threading.Event()

    def on_frame(chunk):
        frames.append(chunk)
        if len(frames) == 4:
            done.set()

    command = [sys.executable, '-c', 'import sys; sys.stdout.buffer.write(bytes(960 * 4 + 100))']
    capture = mic.MicCapture(on_frame, command=command)
    capture.start()
    assert done.wait(5)
    capture.stop()
    assert [len(f) for f in frames] == [960] * 4


def test_fehler_im_verarbeiter_beendet_das_lesen_nicht():
    frames = []

    def on_frame(chunk):
        frames.append(chunk)
        raise RuntimeError('kaputt')

    command = [sys.executable, '-c', 'import sys; sys.stdout.buffer.write(bytes(960 * 3))']
    capture = mic.MicCapture(on_frame, command=command)
    capture.start()
    capture._thread.join(5)
    capture.stop()
    assert len(frames) == 3


def test_karte_aus_geraetename():
    assert mic.card_of('plughw:CARD=Webcam,DEV=0') == 'Webcam'
    assert mic.card_of('default') == 'default'


def test_reglerwert():
    assert mic.mic_volume('Webcam', run=fake_amixer(10)) == 10


def test_mic_ok(tmp_path):
    cards = tmp_path / 'cards'
    cards.write_text(' 0 [vc4hdmi0       ]: vc4-hdmi\n 2 [Webcam         ]: USB-Audio - C922\n')
    assert mic.mic_ok('Webcam', str(cards), run=fake_amixer(10)) is True
    assert mic.mic_ok('Webcam', str(cards), run=fake_amixer(0)) is False
    cards.write_text(' 0 [vc4hdmi0       ]: vc4-hdmi\n')
    assert mic.mic_ok('Webcam', str(cards), run=fake_amixer(10)) is False
```

`tests/test_ringtone.py`:

```python
import asyncio

import numpy as np

import ringtone


def test_zyklus_ton_dann_stille():
    samples = np.frombuffer(ringtone.ring_cycle(), np.int16).reshape(-1, 2)
    assert len(samples) == 3 * 48000
    assert np.abs(samples[:38400]).max() > 3000
    assert np.abs(samples[39000:]).max() == 0


class Sink:
    def __init__(self):
        self.chunks = []

    def write(self, pcm):
        self.chunks.append(pcm)


def test_laeuft_in_echtzeit_bis_zum_abbruch():
    sink = Sink()

    async def run():
        task = asyncio.create_task(ringtone.RingTone().run(sink))
        await asyncio.sleep(0.25)
        task.cancel()

    asyncio.run(run())
    assert 2 <= len(sink.chunks) <= 4
    assert all(len(c) == ringtone.CHUNK_BYTES for c in sink.chunks)
```

`tests/test_audio.py`:

```python
import audio
import echo
import mic


def test_factory_folgt_den_einstellungen(tmp_path):
    events = []
    factory = audio.AudioFactory({'direkt': False, 'echo': 'daempfen', 'mikrofon': 'plughw:CARD=X,DEV=0'},
                                 str(tmp_path), lambda typ, **d: events.append(typ))
    assert isinstance(factory.make_echo(300), echo.Ducker)
    capture = factory.make_mic(lambda chunk: None)
    assert isinstance(capture, mic.MicCapture) and 'plughw:CARD=X,DEV=0' in capture._command
    sink = factory.open_sink()
    assert events == ['play_kodi'] and (tmp_path / 'anruf.sdp').exists()
    sink.stop()
```

- [ ] **Step 2: Tests laufen lassen, sie müssen scheitern**

Run: `.venv/bin/pytest -q tests/test_mic.py tests/test_ringtone.py tests/test_audio.py`
Expected: FAIL mit `ModuleNotFoundError: No module named 'mic'`

- [ ] **Step 3: Implementierung schreiben**

`addon/script.telegram.calls/worker/mic.py`:

```python
"""Webcam-Mikrofon per ALSA: 10-ms-Blöcke (s16le, 48 kHz, Mono) in einem eigenen Thread.

Läuft nur während eines Gesprächs. Der Thread liest ohne Pause, deshalb staut
sich in ALSA nichts; was vor dem Verbinden ankommt, verwirft CallManager.
"""
import logging
import re
import subprocess
import threading

log = logging.getLogger('worker.mic')

RATE = 48000
FRAME_BYTES = RATE // 100 * 2
DEVICE = 'plughw:CARD=Webcam,DEV=0'


class MicCapture:
    def __init__(self, on_frame, device=DEVICE, command=None):
        self._on_frame = on_frame
        self._command = command or ['aplay', '-C', '-q', '-D', device, '-f', 'S16_LE', '-r', str(RATE),
                                    '-c', '1', '-t', 'raw', '--buffer-time=40000']
        self._proc = None
        self._thread = None

    def start(self):
        self._proc = subprocess.Popen(self._command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._thread = threading.Thread(target=self._read, name='mikrofon', daemon=True)
        self._thread.start()

    def _read(self):
        stream = self._proc.stdout
        while True:
            chunk = stream.read(FRAME_BYTES)
            if len(chunk) < FRAME_BYTES:
                return
            try:
                self._on_frame(chunk)
            except Exception:
                log.exception('Mikrofonblock nicht verarbeitet')

    def stop(self):
        if self._proc is None:
            return
        self._proc.terminate()
        try:
            self._proc.wait(2)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
        if self._thread is not None:
            self._thread.join(2)
        self._proc = None


def card_of(device):
    """'plughw:CARD=Webcam,DEV=0' -> 'Webcam'."""
    match = re.search(r'CARD=([^,]+)', device)
    return match.group(1) if match else device


def mic_volume(card, run=subprocess.run):
    """Wert des Reglers 'Mic Capture Volume' oder None, wenn er sich nicht lesen lässt."""
    try:
        result = run(['amixer', '-c', card, 'cget', 'name=Mic Capture Volume'],
                     capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r': values=(\d+)', result.stdout)
    return int(match.group(1)) if match else None


def mic_ok(card, cards_path='/proc/asound/cards', run=subprocess.run):
    """Karte vorhanden und Regler nicht auf 0 (ein fehlender Regler zählt als in Ordnung)."""
    try:
        with open(cards_path) as f:
            cards = f.read()
    except OSError:
        return False
    if f'[{card}' not in cards:
        return False
    return mic_volume(card, run) != 0
```

`addon/script.telegram.calls/worker/ringtone.py`:

```python
"""Klingelton für eingehende Anrufe: Doppelton 0,8 s, Pause 2,2 s; s16le, 48 kHz, Stereo."""
import asyncio
import time

import numpy as np

RATE = 48000
TONE_S = 0.8
CYCLE_S = 3.0
CHUNK_S = 0.1
CHUNK_BYTES = int(RATE * CHUNK_S) * 4


def ring_cycle():
    n_tone = int(RATE * TONE_S)
    t = np.arange(n_tone) / RATE
    wave = 0.25 * (np.sin(2 * np.pi * 523.25 * t) + np.sin(2 * np.pi * 659.25 * t)) / 2
    fade = np.minimum(1.0, np.minimum(t, TONE_S - t) / 0.02)  # 20 ms ein- und ausblenden gegen Knacken
    mono = np.zeros(int(RATE * CYCLE_S))
    mono[:n_tone] = wave * fade
    return np.repeat((mono * 32767).astype(np.int16), 2).tobytes()


class RingTone:
    def __init__(self):
        self._cycle = ring_cycle()

    async def run(self, sink):
        """Schreibt den Ton in Echtzeit in die Ausgabe, bis die Aufgabe abgebrochen wird."""
        start, pos, n = time.monotonic(), 0, 0
        while True:
            sink.write(self._cycle[pos:pos + CHUNK_BYTES])
            pos = (pos + CHUNK_BYTES) % len(self._cycle)
            n += 1
            await asyncio.sleep(max(0.0, start + n * CHUNK_S - time.monotonic()))
```

`addon/script.telegram.calls/worker/audio.py`:

```python
"""Baut für CallManager Ausgabe, Echounterdrückung, Mikrofon und Klingelton nach den Einstellungen."""
import os

import echo
import mic
import ringtone
import sinks


class AudioFactory:
    def __init__(self, init, data_dir, emit):
        self._direct = bool(init.get('direkt', False))
        self._echo_mode = init.get('echo', 'webrtc')
        self._mic_device = init.get('mikrofon') or mic.DEVICE
        self._sdp_path = os.path.join(data_dir, 'anruf.sdp')
        self._emit = emit

    def open_sink(self):
        return sinks.open_sink(self._direct, self._sdp_path, self._emit)

    def make_echo(self, delay_ms):
        return echo.make_echo(self._echo_mode, delay_ms)

    def make_mic(self, on_frame):
        return mic.MicCapture(on_frame, self._mic_device)

    def ringtone(self):
        return ringtone.RingTone()
```

- [ ] **Step 4: Tests und ruff grün**

Run: `.venv/bin/pytest -q tests/test_mic.py tests/test_ringtone.py tests/test_audio.py && .venv/bin/ruff check .`
Expected: `8 passed`, ruff `All checks passed!`

- [ ] **Step 5: Stand festhalten** – kein Commit; volle Testsuite `.venv/bin/pytest -q` grün.

---

### Task 8: Anrufsteuerung

Herzstück des Anrufprozesses, ohne Telegram testbar. Telegram steckt hinter einem Backend mit `start_call(user_id, timeout)`, `accept(user_id)`, `hang_up(user_id)`, `send_audio(user_id, pcm)`; Fehler beim Wählen kommen als `CallFailed(grund)`.

**Files:**
- Test: `tests/test_callmanager.py`

**Interfaces:**
- Consumes: `echo.stereo_to_mono`, `sinks.SinkError`, eine AudioFactory wie in Task 7.
- Produces: `callmanager.CallManager(backend, emit, audio, name_for, ring_timeout=45)` mit Befehlen `call(user_id)`, `accept()`, `decline()`, `hangup()`, `set_mute(on)`, `shutdown()` (alle Coroutinen) und Ereignis-Eingängen `on_incoming(user_id)` (Coroutine), `on_ringing(user_id)`, `on_remote_ended(user_id, grund)` (Coroutine), `on_frames(user_id, pcm_stereo)`; `name_for` ist eine Coroutine `user_id -> str`. `callmanager.CallFailed(grund)`, `callmanager.State`. Gründe in `ended`: aufgelegt, beendet, abgelehnt, besetzt, keine_antwort, verpasst, abgebrochen, tonausgabe, fehler.

- [ ] **Step 1: Tests schreiben**

`tests/test_callmanager.py`:

```python
import asyncio

import pytest

import callmanager
from callmanager import CallFailed, CallManager, State
from sinks import SinkError


class FakeBackend:
    def __init__(self):
        self.started, self.accepted, self.hung_up, self.sent = [], [], [], []
        self.start_error = None
        self.start_wait = None

    async def start_call(self, user_id, timeout):
        self.started.append(user_id)
        if self.start_wait is not None:
            await self.start_wait.wait()
        if self.start_error:
            raise CallFailed(self.start_error)

    async def accept(self, user_id):
        self.accepted.append(user_id)

    async def hang_up(self, user_id):
        self.hung_up.append(user_id)

    async def send_audio(self, user_id, pcm):
        self.sent.append((user_id, pcm))


class FakeSink:
    delay_ms = 300

    def __init__(self):
        self.written, self.stopped, self.fail = [], False, False

    def write(self, pcm):
        if self.fail:
            raise SinkError('weg')
        self.written.append(pcm)

    def stop(self):
        self.stopped = True


class FakeEcho:
    def __init__(self):
        self.references, self.processed = [], []

    def add_reference(self, mono):
        self.references.append(mono)

    def process(self, mic):
        self.processed.append(mic)
        return mic


class FakeMic:
    def __init__(self, on_frame):
        self.on_frame, self.started, self.stopped = on_frame, False, False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class FakeRing:
    def __init__(self, audio):
        self.audio = audio

    async def run(self, sink):
        self.audio.ringing = True
        try:
            await asyncio.Event().wait()
        finally:
            self.audio.ringing = False


class FakeAudio:
    def __init__(self):
        self.sinks, self.echo, self.mic, self.ringing, self.open_error = [], None, None, False, None

    def open_sink(self):
        if self.open_error:
            raise self.open_error
        self.sinks.append(FakeSink())
        return self.sinks[-1]

    def make_echo(self, delay_ms):
        self.echo = FakeEcho()
        return self.echo

    def make_mic(self, on_frame):
        self.mic = FakeMic(on_frame)
        return self.mic

    def ringtone(self):
        return FakeRing(self)


async def name_for(user_id):
    return f'Kontakt {user_id}'


def setup(**kwargs):
    events = []
    backend, audio = FakeBackend(), FakeAudio()
    manager = CallManager(backend, lambda typ, **d: events.append((typ, d)), audio, name_for, **kwargs)
    return manager, backend, audio, events


def types(events):
    return [e[0] for e in events]


def run(coro):
    return asyncio.run(coro)


def test_ausgehender_anruf_verbindet():
    manager, backend, audio, events = setup()
    run(manager.call(7))
    assert backend.started == [7]
    assert events[0] == ('outgoing_state', {'zustand': 'waehlt'})
    assert types(events)[-1] == 'connected'
    assert manager.state is State.CONNECTED
    assert audio.mic.started and len(audio.sinks) == 1


def test_abgelehnt_ohne_tonausgabe():
    manager, backend, audio, events = setup()
    backend.start_error = 'abgelehnt'
    run(manager.call(7))
    assert events[-1] == ('ended', {'grund': 'abgelehnt'})
    assert manager.state is State.IDLE and audio.sinks == []


def test_auflegen_beim_waehlen():
    async def scenario():
        manager, backend, audio, events = setup()
        backend.start_wait = asyncio.Event()
        task = asyncio.create_task(manager.call(7))
        await asyncio.sleep(0.01)
        await manager.hangup()
        await asyncio.wait_for(task, 1)
        return manager, backend, events

    manager, backend, events = run(scenario())
    assert backend.hung_up == [7]
    assert events[-1] == ('ended', {'grund': 'aufgelegt'})
    assert types(events).count('ended') == 1 and 'connected' not in types(events)


def test_klingeln_beim_waehlen_wird_gemeldet():
    async def scenario():
        manager, backend, audio, events = setup()
        backend.start_wait = asyncio.Event()
        task = asyncio.create_task(manager.call(7))
        await asyncio.sleep(0.01)
        manager.on_ringing(7)
        manager.on_ringing(8)
        backend.start_wait.set()
        await task
        return events

    events = run(scenario())
    assert events[1] == ('outgoing_state', {'zustand': 'klingelt'})
    assert types(events).count('outgoing_state') == 2


def test_eingehend_klingeln_und_annehmen():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.on_incoming(9)
        await asyncio.sleep(0.01)
        rang = audio.ringing
        await manager.accept()
        await asyncio.sleep(0.01)
        return manager, backend, audio, events, rang

    manager, backend, audio, events, rang = run(scenario())
    assert events[0] == ('incoming', {'id': 9, 'name': 'Kontakt 9'})
    assert rang is True and audio.ringing is False
    assert backend.accepted == [9]
    assert types(events)[-1] == 'connected'
    assert len(audio.sinks) == 1  # Klingelton und Gespräch nutzen dieselbe Ausgabe


def test_zweiter_anruf_wird_abgewiesen():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.call(7)
        await manager.on_incoming(8)
        return manager, backend, events

    manager, backend, events = run(scenario())
    assert backend.hung_up == [8]
    assert manager.state is State.CONNECTED and manager.peer == 7
    assert 'incoming' not in types(events)


def test_nicht_angenommen_gilt_als_verpasst():
    async def scenario():
        manager, backend, audio, events = setup(ring_timeout=0.05)
        await manager.on_incoming(9)
        await asyncio.sleep(0.2)
        return manager, backend, audio, events

    manager, backend, audio, events = run(scenario())
    assert events[-1] == ('ended', {'grund': 'verpasst'})
    assert backend.hung_up == [9] and audio.sinks[0].stopped


def test_anrufer_legt_beim_klingeln_auf():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.on_incoming(9)
        await manager.on_remote_ended(9, 'beendet')
        return events

    assert run(scenario())[-1] == ('ended', {'grund': 'verpasst'})


def test_ablehnen():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.on_incoming(9)
        await manager.decline()
        return backend, events

    backend, events = run(scenario())
    assert backend.hung_up == [9] and events[-1] == ('ended', {'grund': 'abgelehnt'})


def test_gegenseite_legt_auf():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.call(7)
        await manager.on_remote_ended(7, 'beendet')
        return audio, events

    audio, events = run(scenario())
    assert events[-1] == ('ended', {'grund': 'beendet'})
    assert audio.mic.stopped and audio.sinks[0].stopped


def test_ton_der_gegenseite_geht_an_ausgabe_und_echo():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.call(7)
        manager.on_frames(7, bytes(1920))
        manager.on_frames(8, bytes(1920))
        return audio

    audio = run(scenario())
    assert audio.sinks[0].written == [bytes(1920)]
    assert audio.echo.references == [bytes(960)]


def test_mikrofon_geht_durch_echo_an_telegram_und_stumm_sendet_stille():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.call(7)
        loud = b'\x01\x02' * 480
        audio.mic.on_frame(loud)
        await manager.set_mute(True)
        audio.mic.on_frame(loud)
        await asyncio.sleep(0.01)
        return backend, audio, loud

    backend, audio, loud = run(scenario())
    assert audio.echo.processed == [loud, bytes(960)]
    assert backend.sent == [(7, loud), (7, bytes(960))]


def test_shutdown_legt_auf():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.call(7)
        await manager.shutdown()
        return manager, backend, events

    manager, backend, events = run(scenario())
    assert backend.hung_up == [7] and events[-1] == ('ended', {'grund': 'aufgelegt'})
    assert manager.state is State.IDLE


def test_tonausgabe_laesst_sich_nicht_oeffnen():
    manager, backend, audio, events = setup()
    audio.open_error = OSError('kaputt')
    run(manager.call(7))
    assert backend.hung_up == [7] and events[-1] == ('ended', {'grund': 'tonausgabe'})


def test_tonausgabe_faellt_im_gespraech_aus():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.call(7)
        audio.sinks[0].fail = True
        manager.on_frames(7, bytes(1920))
        manager.on_frames(7, bytes(1920))
        await asyncio.sleep(0.05)
        return backend, events

    backend, events = run(scenario())
    assert backend.hung_up == [7]
    assert events[-1] == ('ended', {'grund': 'tonausgabe'}) and types(events).count('ended') == 1


def test_anruf_waehrend_anruf_meldet_fehler():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.call(7)
        await manager.call(8)
        return backend, events

    backend, events = run(scenario())
    assert backend.started == [7] and events[-1] == ('error', {'text': 'Es läuft schon ein Anruf'})


def test_ring_timeout_standard():
    assert callmanager.RING_TIMEOUT == 45


@pytest.mark.parametrize('method', ['accept', 'decline', 'hangup'])
def test_befehle_ohne_anruf_tun_nichts(method):
    manager, backend, audio, events = setup()
    run(getattr(manager, method)())
    assert events == [] and backend.hung_up == []
```

- [ ] **Step 2: Tests laufen lassen, sie müssen scheitern**

Run: `.venv/bin/pytest -q tests/test_callmanager.py`
Expected: FAIL mit `ModuleNotFoundError: No module named 'callmanager'`

- [ ] **Step 3: Implementierung schreiben**

`addon/script.telegram.calls/worker/callmanager.py`:

```python
"""Ablauf eines 1-zu-1-Anrufs: Zustände, Ton und Meldungen an das Add-on.

Ohne Telegram testbar: Telegram steckt hinter dem Backend (tgbackend.py), der
Ton hinter der AudioFactory (audio.py). Gründe in 'ended': aufgelegt, beendet,
abgelehnt, besetzt, keine_antwort, verpasst, abgebrochen, tonausgabe, fehler.
"""
import asyncio
import enum
import logging

from echo import stereo_to_mono
from sinks import SinkError

log = logging.getLogger('worker.call')

RING_TIMEOUT = 45


class CallFailed(Exception):
    def __init__(self, grund):
        super().__init__(grund)
        self.grund = grund


class State(enum.Enum):
    IDLE = 'idle'
    OUTGOING = 'outgoing'
    INCOMING = 'incoming'
    CONNECTED = 'connected'


class CallManager:
    def __init__(self, backend, emit, audio, name_for, ring_timeout=RING_TIMEOUT):
        self._backend = backend
        self._emit = emit
        self._audio = audio
        self._name_for = name_for
        self._ring_timeout = ring_timeout
        self.state = State.IDLE
        self.peer = None
        self._sink = None
        self._echo = None
        self._mic = None
        self._ring_task = None
        self._timeout_task = None
        self._dial_task = None
        self._muted = False
        self._sink_failed = False
        self._loop = None

    # --- Befehle vom Add-on ---------------------------------------------

    async def call(self, user_id):
        if self.state is not State.IDLE:
            self._emit('error', text='Es läuft schon ein Anruf')
            return
        self._loop = asyncio.get_running_loop()
        self.state, self.peer = State.OUTGOING, user_id
        self._emit('outgoing_state', zustand='waehlt')
        self._dial_task = asyncio.current_task()
        try:
            await self._backend.start_call(user_id, self._ring_timeout)
        except CallFailed as e:
            await self._end(e.grund)
            return
        except asyncio.CancelledError:
            return  # hangup() hat aufgelegt und aufgeräumt
        finally:
            self._dial_task = None
        if self.state is State.OUTGOING and self.peer == user_id:
            await self._connected()

    async def accept(self):
        if self.state is not State.INCOMING:
            return
        self._stop_ringing()
        user_id = self.peer
        try:
            await self._backend.accept(user_id)
        except CallFailed as e:
            await self._end(e.grund)
            return
        if self.state is State.INCOMING and self.peer == user_id:
            await self._connected()

    async def decline(self):
        if self.state is not State.INCOMING:
            return
        await self._hang_up_quietly(self.peer)
        await self._end('abgelehnt')

    async def hangup(self):
        if self.state not in (State.OUTGOING, State.CONNECTED):
            return
        if self._dial_task is not None:
            self._dial_task.cancel()
        await self._hang_up_quietly(self.peer)
        await self._end('aufgelegt')

    async def set_mute(self, on):
        self._muted = bool(on)

    async def shutdown(self):
        """Beim Beenden des Prozesses: laufenden Anruf sauber auflegen."""
        if self.state is State.IDLE:
            return
        if self._dial_task is not None:
            self._dial_task.cancel()
        await self._hang_up_quietly(self.peer)
        await self._end('aufgelegt')

    # --- Ereignisse von Telegram ----------------------------------------

    async def on_incoming(self, user_id):
        if self.state is not State.IDLE:
            log.info('Zweiter Anruf während eines Gesprächs: besetzt')
            await self._hang_up_quietly(user_id)
            return
        self._loop = asyncio.get_running_loop()
        self.state, self.peer = State.INCOMING, user_id
        name = await self._name_for(user_id)
        if self.state is not State.INCOMING or self.peer != user_id:
            return  # während der Namenssuche schon wieder beendet
        self._emit('incoming', id=user_id, name=name)
        self._timeout_task = asyncio.create_task(self._ring_timeout_after(user_id))
        if not await self._ensure_sink():
            return
        self._ring_task = asyncio.create_task(self._audio.ringtone().run(self._sink))

    def on_ringing(self, user_id):
        if self.state is State.OUTGOING and self.peer == user_id:
            self._emit('outgoing_state', zustand='klingelt')

    async def on_remote_ended(self, user_id, grund):
        # Beim Wählen meldet start_call() den Grund (abgelehnt, besetzt …) genauer.
        if user_id != self.peer or self.state in (State.IDLE, State.OUTGOING):
            return
        await self._end('verpasst' if self.state is State.INCOMING else grund)

    def on_frames(self, user_id, pcm):
        """Ton der Gegenseite (s16le, 48 kHz, Stereo)."""
        if self.state is not State.CONNECTED or user_id != self.peer or self._sink is None:
            return
        try:
            self._sink.write(pcm)
        except SinkError as e:
            if not self._sink_failed:
                self._sink_failed = True
                log.error('Tonausgabe ausgefallen: %s', e)
                asyncio.get_running_loop().create_task(self._fail('tonausgabe'))
            return
        self._echo.add_reference(stereo_to_mono(pcm))

    # --- intern ---------------------------------------------------------

    def _on_mic_frame(self, pcm):
        """Läuft im Mikrofon-Thread."""
        echo = self._echo
        if self.state is not State.CONNECTED or echo is None:
            return
        if self._muted:
            pcm = bytes(len(pcm))
        out = echo.process(pcm)
        self._loop.call_soon_threadsafe(self._send_audio, out)

    def _send_audio(self, pcm):
        if self.state is State.CONNECTED:
            self._loop.create_task(self._safe_send(self.peer, pcm))

    async def _safe_send(self, user_id, pcm):
        try:
            await self._backend.send_audio(user_id, pcm)
        except Exception as e:
            log.debug('Mikrofonblock nicht gesendet: %s', e)

    async def _ensure_sink(self):
        if self._sink is not None:
            return True
        try:
            self._sink = await asyncio.to_thread(self._audio.open_sink)
        except Exception:
            log.exception('Tonausgabe lässt sich nicht öffnen')
            await self._fail('tonausgabe')
            return False
        return True

    async def _connected(self):
        if not await self._ensure_sink():
            return
        self._echo = self._audio.make_echo(self._sink.delay_ms)
        self._muted = False
        self._sink_failed = False
        self.state = State.CONNECTED
        self._mic = self._audio.make_mic(self._on_mic_frame)
        self._mic.start()
        self._emit('connected')

    async def _ring_timeout_after(self, user_id):
        await asyncio.sleep(self._ring_timeout)
        if self.state is State.INCOMING and self.peer == user_id:
            self._timeout_task = None  # nicht sich selbst in _end() abbrechen
            await self._hang_up_quietly(user_id)
            await self._end('verpasst')

    async def _fail(self, grund):
        if self.state is State.IDLE:
            return
        await self._hang_up_quietly(self.peer)
        await self._end(grund)

    async def _hang_up_quietly(self, user_id):
        try:
            await self._backend.hang_up(user_id)
        except Exception:
            log.exception('Auflegen fehlgeschlagen')

    def _stop_ringing(self):
        for task in (self._ring_task, self._timeout_task):
            if task is not None:
                task.cancel()
        self._ring_task = self._timeout_task = None

    async def _end(self, grund):
        if self.state is State.IDLE:
            return
        self._stop_ringing()
        mic, sink = self._mic, self._sink
        self._mic = self._sink = self._echo = None
        self.state, self.peer = State.IDLE, None
        if mic is not None:
            await asyncio.to_thread(mic.stop)
        if sink is not None:
            await asyncio.to_thread(sink.stop)
        self._emit('ended', grund=grund)
```

- [ ] **Step 4: Tests und ruff grün**

Run: `.venv/bin/pytest -q tests/test_callmanager.py && .venv/bin/ruff check .`
Expected: `20 passed`, ruff `All checks passed!`

- [ ] **Step 5: Stand festhalten** – kein Commit; volle Testsuite `.venv/bin/pytest -q` grün.

---

### Task 9: Telegram-Anbindung

`tgbackend.py` übersetzt py-tgcalls in die Backend-Schnittstelle von Task 8, `session.py` kümmert sich um Anmeldung, Kontakte und Bilder. Die Telegram-Bibliotheken sind in `.venv` installiert (Task 1), die Tests ersetzen nur den Client bzw. `PyTgCalls`. Hat der Messtest (Task 2) andere Richtung/Gerät für empfangene Frames gezeigt als `Direction.INCOMING`, den Filter in `bind()` entsprechend anpassen.

**Files:**
- Test: `tests/test_tgbackend.py`
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: `callmanager.CallFailed` und die Ereignis-Eingänge des CallManagers (Task 8).
- Produces: `tgbackend.TgCallsBackend(client, calls)` mit `bind(manager)`, `start_call`, `accept`, `hang_up`, `send_audio`; `session.TelegramSession(client, emit, data_dir, on_authorized)` mit Coroutinen `login_qr()`, `login_phone(nummer)`, `login_code(code)`, `login_password(passwort)`, `logout()`, `send_contacts()`, `name_for(user_id)`; `session.SESSION_NAME = 'telegram'`; `session.display_name`, `session.contact_entries`, `session.wait_text`.

- [ ] **Step 1: Tests schreiben**

`tests/test_tgbackend.py`:

```python
import asyncio

import pytest
from pytgcalls import exceptions

import tgbackend
from callmanager import CallFailed


class FakeCalls:
    def __init__(self, play_error=None, record_error=None, leave_error=None):
        self.play_error, self.record_error, self.leave_error = play_error, record_error, leave_error
        self.played, self.recorded, self.left, self.frames = [], [], [], []

    async def play(self, chat_id, stream, config=None):
        self.played.append((chat_id, stream, config))
        if self.play_error:
            raise self.play_error

    async def record(self, chat_id, stream):
        self.recorded.append((chat_id, stream))
        if self.record_error:
            raise self.record_error

    async def leave_call(self, chat_id):
        self.left.append(chat_id)
        if self.leave_error:
            raise self.leave_error

    async def send_frame(self, chat_id, device, data):
        self.frames.append((chat_id, device, data))


def backend(calls):
    return tgbackend.TgCallsBackend(client=None, calls=calls)


def test_anruf_startet_mikrofon_und_empfang_mit_48khz():
    calls = FakeCalls()
    asyncio.run(backend(calls).start_call(7, 45))
    chat_id, stream, config = calls.played[0]
    assert chat_id == 7 and config.timeout == 45
    assert stream.microphone.parameters.bitrate == 48000 and stream.microphone.parameters.channels == 1
    assert calls.recorded[0][1].microphone.parameters.bitrate == 48000
    assert calls.recorded[0][1].microphone.parameters.channels == 2


@pytest.mark.parametrize('error, grund', [
    (exceptions.TimedOutAnswer(), 'keine_antwort'),
    (exceptions.CallDeclined(7), 'abgelehnt'),
    (exceptions.CallBusy(7), 'besetzt'),
    (exceptions.CallDiscarded(7), 'abgebrochen'),
])
def test_gruende_beim_waehlen(error, grund):
    with pytest.raises(CallFailed) as info:
        asyncio.run(backend(FakeCalls(play_error=error)).start_call(7, 45))
    assert info.value.grund == grund


def test_fehler_beim_empfang_legt_auf():
    calls = FakeCalls(record_error=RuntimeError('kaputt'))
    with pytest.raises(CallFailed) as info:
        asyncio.run(backend(calls).start_call(7, 45))
    assert info.value.grund == 'fehler' and calls.left == [7]


def test_auflegen_ohne_anruf_ist_kein_fehler():
    calls = FakeCalls(leave_error=exceptions.NotInCallError())
    asyncio.run(backend(calls).hang_up(7))
    assert calls.left == [7]


def test_mikrofon_geht_als_externer_frame_raus():
    calls = FakeCalls()
    asyncio.run(backend(calls).send_audio(7, b'ab'))
    assert calls.frames == [(7, tgbackend.Device.MICROPHONE, b'ab')]
```

`tests/test_session.py`:

```python
import asyncio
import datetime
import os
from types import SimpleNamespace

from telethon.errors import PasswordHashInvalidError, PhoneCodeInvalidError, SessionPasswordNeededError

import session


def user(uid, first, last=None, **kw):
    return SimpleNamespace(id=uid, first_name=first, last_name=last, username=None, bot=False, deleted=False,
                           is_self=False, photo=None, **kw)


def test_anzeigename():
    assert session.display_name(user(1, 'Anna', 'Beck')) == 'Anna Beck'
    assert session.display_name(SimpleNamespace(title='Familie')) == 'Familie'
    assert session.display_name(SimpleNamespace(first_name=None, last_name=None, username='xy')) == 'xy'
    assert session.display_name(SimpleNamespace()) == 'Unbekannt'


def test_kontaktliste_personen_vor_gruppen_alphabetisch():
    entries = session.contact_entries([user(2, 'zoe'), user(1, 'Ärger'), user(3, 'Anna')],
                                      [SimpleNamespace(id=9, title='Verein')], lambda i: f'/b/{i}.jpg')
    assert [e['name'] for e in entries] == ['Anna', 'zoe', 'Ärger', 'Verein']
    assert entries[-1] == {'id': 9, 'name': 'Verein', 'bild': '/b/9.jpg', 'gruppe': True}


def test_wartezeit_in_minuten():
    assert 'bitte 2 Minuten' in session.wait_text(61)
    assert 'bitte 1 Minute warten' in session.wait_text(5)


class FakeQr:
    def __init__(self, waits):
        self.url = 'tg://login?token=a'
        self.expires = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=30)
        self.waits = list(waits)
        self.recreated = 0

    async def wait(self, timeout=None):
        result = self.waits.pop(0)
        if isinstance(result, BaseException):
            raise result

    async def recreate(self):
        self.recreated += 1
        self.url = f'tg://login?token={self.recreated}'


class FakeClient:
    def __init__(self, qr=None, sign_in_errors=()):
        self.qr = qr
        self.sign_in_errors = list(sign_in_errors)
        self.sign_ins = []

    async def qr_login(self):
        return self.qr

    async def send_code_request(self, nummer):
        self.phone = nummer

    async def sign_in(self, **kwargs):
        self.sign_ins.append(kwargs)
        if self.sign_in_errors:
            raise self.sign_in_errors.pop(0)


def make(tmp_path, client):
    events, authorized = [], []

    async def on_authorized():
        authorized.append(True)

    sess = session.TelegramSession(client, lambda typ, **d: events.append((typ, d)), str(tmp_path), on_authorized)
    return sess, events, authorized


def test_qr_wird_erneuert_bis_gescannt(tmp_path):
    qr = FakeQr([TimeoutError(), None])
    sess, events, authorized = make(tmp_path, FakeClient(qr=qr))
    asyncio.run(sess.login_qr())
    qr_events = [d for t, d in events if t == 'qr']
    assert [d['url'] for d in qr_events] == ['tg://login?token=a', 'tg://login?token=1']
    assert qr_events[0]['bild'] != qr_events[1]['bild']
    assert os.path.exists(qr_events[1]['bild']) and not os.path.exists(qr_events[0]['bild'])
    assert events[-1] == ('login_ok', {}) and authorized == [True]


def test_qr_mit_zwei_faktor(tmp_path):
    sess, events, authorized = make(tmp_path, FakeClient(qr=FakeQr([SessionPasswordNeededError(None)])))
    asyncio.run(sess.login_qr())
    assert events[-1] == ('need_password', {}) and authorized == []


def test_telefon_code_und_passwort(tmp_path):
    client = FakeClient(sign_in_errors=[PhoneCodeInvalidError(None), SessionPasswordNeededError(None),
                                        PasswordHashInvalidError(None)])
    sess, events, authorized = make(tmp_path, client)

    async def scenario():
        await sess.login_phone('+491')
        await sess.login_code('111')
        await sess.login_code('222')
        await sess.login_password('falsch')
        await sess.login_password('richtig')

    asyncio.run(scenario())
    assert [t for t, d in events] == ['need_code', 'login_error', 'need_password', 'login_error', 'login_ok']
    assert events[1][1] == {'grund': 'Code falsch', 'erneut': 'code'}
    assert events[3][1] == {'grund': 'Passwort falsch', 'erneut': 'passwort'}
    assert client.sign_ins[0] == {'phone': '+491', 'code': '111'}
    assert authorized == [True]


def test_code_ohne_nummer(tmp_path):
    sess, events, _ = make(tmp_path, FakeClient())
    asyncio.run(sess.login_code('1'))
    assert events == [('login_error', {'grund': 'Zuerst die Telefonnummer eingeben'})]


def test_session_datei_wird_privat(tmp_path):
    path = tmp_path / 'telegram.session'
    path.write_text('x')
    os.chmod(path, 0o644)
    sess, events, _ = make(tmp_path, FakeClient(qr=FakeQr([None])))
    asyncio.run(sess.login_qr())
    assert oct(os.stat(path).st_mode & 0o777) == '0o600'
```

- [ ] **Step 2: Tests laufen lassen, sie müssen scheitern**

Run: `.venv/bin/pytest -q tests/test_tgbackend.py tests/test_session.py`
Expected: FAIL mit `ModuleNotFoundError: No module named 'tgbackend'`

- [ ] **Step 3: Implementierung schreiben**

`addon/script.telegram.calls/worker/tgbackend.py`:

```python
"""Telegram-Anrufe über py-tgcalls/ntgcalls, übersetzt in die Sprache von CallManager.

Mikrofon und Ton der Gegenseite laufen als externe Frames durch den Prozess,
damit die Echounterdrückung beide sieht (Messtest Teilprojekt 2).
"""
import logging

from ntgcalls import MediaSource
from pytgcalls import exceptions
from pytgcalls import filters as fl
from pytgcalls.types import CallConfig, ChatUpdate, Device, Direction
from pytgcalls.types.raw import AudioParameters, AudioStream, Stream
from telethon import events
from telethon.tl.types import PhoneCallWaiting, UpdatePhoneCall

from callmanager import CallFailed

log = logging.getLogger('worker.telegram')

MIC = AudioParameters(48000, 1)
SPEAKER = AudioParameters(48000, 2)  # 44,1 kHz bringt ntgcalls 3.0.3 zum Absturz


def mic_stream():
    return Stream(microphone=AudioStream(MediaSource.EXTERNAL, '', MIC))


def speaker_stream():
    # Bei record() steht der Ton der Gegenseite im Feld "microphone".
    return Stream(microphone=AudioStream(MediaSource.EXTERNAL, '', SPEAKER))


class TgCallsBackend:
    def __init__(self, client, calls):
        self._client = client
        self._calls = calls

    def bind(self, manager):
        """Leitet Telegram-Ereignisse an den CallManager weiter."""
        calls = self._calls

        @calls.on_update(fl.chat_update(ChatUpdate.Status.INCOMING_CALL))
        async def _incoming(_, update):
            await manager.on_incoming(update.chat_id)

        @calls.on_update(fl.chat_update(ChatUpdate.Status.LEFT_CALL))
        async def _left(_, update):
            grund = 'besetzt' if update.status & ChatUpdate.Status.BUSY_CALL else 'beendet'
            await manager.on_remote_ended(update.chat_id, grund)

        @calls.on_update(fl.stream_frame(Direction.INCOMING))
        async def _frames(_, update):
            for frame in update.frames:
                manager.on_frames(update.chat_id, frame.frame)

        @self._client.on(events.Raw(UpdatePhoneCall))
        async def _raw(update):
            call = update.phone_call
            if isinstance(call, PhoneCallWaiting) and call.receive_date:
                manager.on_ringing(call.participant_id)

    async def start_call(self, user_id, timeout):
        try:
            await self._calls.play(user_id, mic_stream(), config=CallConfig(timeout=timeout))
        except exceptions.TimedOutAnswer:
            raise CallFailed('keine_antwort') from None
        except exceptions.CallDeclined:
            raise CallFailed('abgelehnt') from None
        except exceptions.CallBusy:
            raise CallFailed('besetzt') from None
        except exceptions.CallDiscarded:
            raise CallFailed('abgebrochen') from None
        await self._record(user_id)

    async def accept(self, user_id):
        try:
            await self._calls.play(user_id, mic_stream())
        except (exceptions.CallDiscarded, exceptions.NotInCallError):
            raise CallFailed('verpasst') from None
        await self._record(user_id)

    async def _record(self, user_id):
        try:
            await self._calls.record(user_id, speaker_stream())
        except Exception:
            log.exception('Empfang des Tons ließ sich nicht starten')
            await self.hang_up(user_id)
            raise CallFailed('fehler') from None

    async def hang_up(self, user_id):
        try:
            await self._calls.leave_call(user_id)
        except exceptions.NotInCallError:
            pass

    async def send_audio(self, user_id, pcm):
        await self._calls.send_frame(user_id, Device.MICROPHONE, pcm)
```

`addon/script.telegram.calls/worker/session.py`:

```python
"""Telegram-Konto: Anmeldung per QR-Code oder Telefonnummer, Kontakte, Profilbilder.

Telefonnummer, Code und Passwort werden nur an Telegram weitergegeben, nie
gespeichert oder protokolliert. Gespeichert wird nur die Session (Rechte 600).
"""
import asyncio
import datetime
import logging
import math
import os

from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.tl.functions.contacts import GetContactsRequest

log = logging.getLogger('worker.session')

SESSION_NAME = 'telegram'  # Telethon hängt .session an


def display_name(entity):
    title = getattr(entity, 'title', None)
    if title:
        return title
    parts = [getattr(entity, 'first_name', None), getattr(entity, 'last_name', None)]
    name = ' '.join(p for p in parts if p)
    return name or getattr(entity, 'username', None) or 'Unbekannt'


def contact_entries(users, groups, avatar_for):
    """Liste für das Add-on: Personen alphabetisch, danach Gruppen alphabetisch."""
    def key(entry):
        return entry['name'].casefold()

    people = [{'id': u.id, 'name': display_name(u), 'bild': avatar_for(u.id), 'gruppe': False} for u in users]
    chats = [{'id': g.id, 'name': display_name(g), 'bild': avatar_for(g.id), 'gruppe': True} for g in groups]
    return sorted(people, key=key) + sorted(chats, key=key)


def wait_text(seconds):
    minutes = max(1, math.ceil(seconds / 60))
    return f'Telegram verlangt eine Pause: bitte {minutes} {"Minute" if minutes == 1 else "Minuten"} warten'


class TelegramSession:
    def __init__(self, client, emit, data_dir, on_authorized):
        self._client = client
        self._emit = emit
        self._on_authorized = on_authorized
        self._data_dir = data_dir
        self._avatar_dir = os.path.join(data_dir, 'bilder')
        self._session_file = os.path.join(data_dir, SESSION_NAME + '.session')
        self._names = {}
        self._phone = None
        self._login_task = None
        self._qr_count = 0

    # --- Anmeldung ------------------------------------------------------

    async def login_qr(self):
        self._cancel_login()
        self._login_task = asyncio.current_task()
        try:
            qr = await self._client.qr_login()
            while True:
                self._emit('qr', url=qr.url, bild=self._qr_image(qr.url))
                remaining = (qr.expires - datetime.datetime.now(datetime.UTC)).total_seconds()
                try:
                    await qr.wait(timeout=max(5.0, remaining - 2))
                    break
                except TimeoutError:
                    await qr.recreate()
        except asyncio.CancelledError:
            return
        except SessionPasswordNeededError:
            self._emit('need_password')
            return
        except FloodWaitError as e:
            self._emit('login_error', grund=wait_text(e.seconds))
            return
        finally:
            if self._login_task is asyncio.current_task():
                self._login_task = None
        await self._logged_in()

    async def login_phone(self, nummer):
        self._cancel_login()
        try:
            await self._client.send_code_request(nummer)
        except PhoneNumberInvalidError:
            self._emit('login_error', grund='Telefonnummer ungültig')
            return
        except FloodWaitError as e:
            self._emit('login_error', grund=wait_text(e.seconds))
            return
        self._phone = nummer
        self._emit('need_code')

    async def login_code(self, code):
        if self._phone is None:
            self._emit('login_error', grund='Zuerst die Telefonnummer eingeben')
            return
        try:
            await self._client.sign_in(phone=self._phone, code=code)
        except SessionPasswordNeededError:
            self._emit('need_password')
            return
        except PhoneCodeInvalidError:
            self._emit('login_error', grund='Code falsch', erneut='code')
            return
        except PhoneCodeExpiredError:
            self._emit('login_error', grund='Code abgelaufen')
            return
        except FloodWaitError as e:
            self._emit('login_error', grund=wait_text(e.seconds))
            return
        await self._logged_in()

    async def login_password(self, passwort):
        try:
            await self._client.sign_in(password=passwort)
        except PasswordHashInvalidError:
            self._emit('login_error', grund='Passwort falsch', erneut='passwort')
            return
        except FloodWaitError as e:
            self._emit('login_error', grund=wait_text(e.seconds))
            return
        await self._logged_in()

    async def logout(self):
        await self._client.log_out()

    async def _logged_in(self):
        self._phone = None
        try:
            os.chmod(self._session_file, 0o600)
        except OSError:
            pass
        await self._on_authorized()
        self._emit('login_ok')

    def _cancel_login(self):
        task = self._login_task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        self._login_task = None

    def _qr_image(self, url):
        """PNG mit neuem Namen, weil Kodi Bilder nach Pfad zwischenspeichert."""
        import qrcode
        import qrcode.image.pure

        for name in os.listdir(self._data_dir):
            if name.startswith('qr-') and name.endswith('.png'):
                os.remove(os.path.join(self._data_dir, name))
        self._qr_count += 1
        path = os.path.join(self._data_dir, f'qr-{self._qr_count}.png')
        qrcode.make(url, image_factory=qrcode.image.pure.PyPNGImage, box_size=12, border=2).save(path)
        return path

    # --- Kontakte -------------------------------------------------------

    async def send_contacts(self):
        result = await self._client(GetContactsRequest(hash=0))
        users = [u for u in result.users if not (u.bot or u.deleted or u.is_self)]
        groups = []
        async for dialog in self._client.iter_dialogs(limit=300):
            if dialog.is_group:
                groups.append(dialog.entity)
        for user in users:
            self._names[user.id] = display_name(user)
        self._emit('contacts', liste=contact_entries(users, groups, self._avatar_for))
        if await self._download_avatars(users + groups):
            self._emit('contacts', liste=contact_entries(users, groups, self._avatar_for))

    async def name_for(self, user_id):
        if user_id not in self._names:
            try:
                self._names[user_id] = display_name(await self._client.get_entity(user_id))
            except Exception as e:
                log.warning('Name für %s nicht gefunden: %s', user_id, e)
                return 'Unbekannt'
        return self._names[user_id]

    def _avatar_path(self, entity_id):
        return os.path.join(self._avatar_dir, f'{entity_id}.jpg')

    def _avatar_for(self, entity_id):
        path = self._avatar_path(entity_id)
        return path if os.path.exists(path) else ''

    async def _download_avatars(self, entities):
        os.makedirs(self._avatar_dir, mode=0o700, exist_ok=True)
        fetched = False
        for entity in entities:
            path = self._avatar_path(entity.id)
            if os.path.exists(path) or not getattr(entity, 'photo', None):
                continue
            try:
                if await self._client.download_profile_photo(entity, file=path, download_big=False):
                    fetched = True
            except Exception as e:
                log.warning('Profilbild %s nicht geladen: %s', entity.id, e)
        return fetched
```

- [ ] **Step 4: Tests und ruff grün**

Run: `.venv/bin/pytest -q tests/test_tgbackend.py tests/test_session.py && .venv/bin/ruff check .`
Expected: `16 passed`, ruff `All checks passed!`

- [ ] **Step 5: Stand festhalten** – kein Commit; volle Testsuite `.venv/bin/pytest -q` grün.

---

### Task 10: Socket-Server und Hauptprogramm des Anrufprozesses

**Files:**
- Test: `tests/test_server.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `tgc.protocol` (Task 3), `TelegramSession` (Task 9), `CallManager` (Task 8), `TgCallsBackend` (Task 9), `AudioFactory` und `mic` (Task 7).
- Produces: `server.Server(path, on_command)` mit `start()`, `emit(typ, **data)`, `close()`; `worker/main.py` als Programm: `python3 worker/main.py --data DIR`, erste stdin-Zeile JSON `{api_id, api_hash, direkt, echo, mikrofon}`, Socket `DIR/worker.sock`, Log auf stderr, Exit-Code 3 bei belegter Sperre `DIR/worker.lock`; `main.acquire_lock(path)`, `main.Worker`. Ein `UnauthorizedError` von Telegram (Session widerrufen) wird zu `ready{angemeldet: false}`.

- [ ] **Step 1: Tests schreiben**

`tests/test_server.py`:

```python
import asyncio
import json
import os
import stat

from server import Server


async def connect(path):
    reader, writer = await asyncio.open_unix_connection(path)
    return reader, writer


async def read_event(reader):
    return json.loads(await asyncio.wait_for(reader.readline(), 2))


def test_puffer_wird_beim_verbinden_nachgeliefert_und_befehle_kommen_an(tmp_path):
    async def scenario():
        received = []

        async def on_command(message):
            received.append(message)

        server = Server(str(tmp_path / 'w.sock'), on_command)
        await server.start()
        server.emit('ready', angemeldet=True)
        reader, writer = await connect(str(tmp_path / 'w.sock'))
        first = await read_event(reader)
        writer.write(b'{"typ": "call", "id": 5}\n')
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.close()
        await writer.wait_closed()
        await server.close()
        return first, received

    first, received = asyncio.run(scenario())
    assert first == {'typ': 'ready', 'angemeldet': True}
    assert received == [{'typ': 'call', 'id': 5}]


def test_unbekannter_befehl_ergibt_fehlerereignis(tmp_path):
    async def scenario():
        async def on_command(message):
            raise AssertionError('darf nicht aufgerufen werden')

        server = Server(str(tmp_path / 'w.sock'), on_command)
        await server.start()
        reader, writer = await connect(str(tmp_path / 'w.sock'))
        writer.write(b'{"typ": "rm_rf"}\nkein json\n')
        events = [await read_event(reader), await read_event(reader)]
        writer.close()
        await writer.wait_closed()
        await server.close()
        return events

    events = asyncio.run(scenario())
    assert [e['typ'] for e in events] == ['error', 'error']
    assert 'unbekannter Befehl' in events[0]['text']


def test_fehler_im_befehl_wird_gemeldet(tmp_path):
    async def scenario():
        async def on_command(message):
            raise RuntimeError('kaputt')

        server = Server(str(tmp_path / 'w.sock'), on_command)
        await server.start()
        reader, writer = await connect(str(tmp_path / 'w.sock'))
        writer.write(b'{"typ": "contacts"}\n')
        event = await read_event(reader)
        writer.close()
        await writer.wait_closed()
        await server.close()
        return event

    assert asyncio.run(scenario()) == {'typ': 'error', 'text': 'contacts: kaputt'}


def test_langer_befehl_blockiert_folgende_nicht(tmp_path):
    async def scenario():
        order = []
        release = asyncio.Event()

        async def on_command(message):
            order.append(message['typ'])
            if message['typ'] == 'call':
                await release.wait()

        server = Server(str(tmp_path / 'w.sock'), on_command)
        await server.start()
        reader, writer = await connect(str(tmp_path / 'w.sock'))
        writer.write(b'{"typ": "call", "id": 1}\n{"typ": "hangup"}\n')
        await writer.drain()
        await asyncio.sleep(0.05)
        release.set()
        writer.close()
        await writer.wait_closed()
        await server.close()
        return order

    assert asyncio.run(scenario()) == ['call', 'hangup']


def test_alter_socket_wird_ersetzt_und_ist_privat(tmp_path):
    path = tmp_path / 'w.sock'
    path.write_text('Rest')

    async def scenario():
        async def on_command(message):
            pass

        server = Server(str(path), on_command)
        await server.start()
        mode = stat.S_IMODE(os.stat(path).st_mode)
        reader, writer = await connect(str(path))
        writer.close()
        await writer.wait_closed()
        await server.close()
        return mode

    assert asyncio.run(scenario()) == 0o600
    assert not path.exists()
```

`tests/test_main.py`:

```python
import asyncio

import main


def test_sperre_verhindert_zweiten_prozess(tmp_path):
    path = str(tmp_path / 'worker.lock')
    first = main.acquire_lock(path)
    assert first is not None
    assert main.acquire_lock(path) is None
    main.os.close(first)
    again = main.acquire_lock(path)
    assert again is not None
    main.os.close(again)


class Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        async def method(*args):
            self.calls.append((name, args))
        return method


def make_worker(tmp_path, with_calls=True):
    worker = main.Worker({'api_id': 1, 'api_hash': 'x'}, str(tmp_path))
    events = []
    worker.server.emit = lambda typ, **d: events.append((typ, d))
    worker.session = Recorder()
    worker.calls = Recorder() if with_calls else None
    return worker, events


def test_befehle_werden_verteilt(tmp_path):
    worker, events = make_worker(tmp_path)

    async def scenario():
        for message in ({'typ': 'login_phone', 'nummer': '+49'}, {'typ': 'contacts'},
                        {'typ': 'call', 'id': '7'}, {'typ': 'mute', 'an': 1}, {'typ': 'hangup'}):
            await worker.on_command(message)

    asyncio.run(scenario())
    assert worker.session.calls == [('login_phone', ('+49',)), ('send_contacts', ())]
    assert worker.calls.calls == [('call', (7,)), ('set_mute', (True,)), ('hangup', ())]


def test_anrufbefehl_ohne_anmeldung(tmp_path):
    worker, events = make_worker(tmp_path, with_calls=False)
    asyncio.run(worker.on_command({'typ': 'call', 'id': 7}))
    assert events == [('error', {'text': 'Nicht angemeldet'})]


def test_quit_setzt_ende(tmp_path):
    async def scenario():
        worker, events = make_worker(tmp_path)
        await worker.on_command({'typ': 'quit'})
        return worker.quit.is_set()

    assert asyncio.run(scenario()) is True


def test_widerrufene_session_fuehrt_zur_anmeldung(tmp_path):
    from telethon.errors import UnauthorizedError

    worker, events = make_worker(tmp_path)

    async def revoked(*args):
        raise UnauthorizedError(None, 'AUTH_KEY_UNREGISTERED')

    worker.session.send_contacts = revoked
    asyncio.run(worker.on_command({'typ': 'contacts'}))
    assert events == [('ready', {'angemeldet': False})]

def test_import_verdraengt_installierte_pakete_nicht():
    """main.py darf vendor/ (aarch64) nur hinten anhängen; vorn würde es auf dem Entwicklungsrechner gewinnen."""
    import site
    import sys

    vendor = main.os.path.join(main.ADDON, 'vendor')
    site_packages = site.getsitepackages()[0]
    assert sys.path.index(vendor) > sys.path.index(site_packages)
```

- [ ] **Step 2: Tests laufen lassen, sie müssen scheitern**

Run: `.venv/bin/pytest -q tests/test_server.py tests/test_main.py`
Expected: FAIL mit `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: Implementierung schreiben**

`addon/script.telegram.calls/worker/server.py`:

```python
"""Unix-Socket-Server des Anrufprozesses: Befehle vom Add-on lesen, Ereignisse schicken.

Es gibt höchstens einen Gesprächspartner (das Add-on); eine neue Verbindung
ersetzt die alte. Ereignisse ohne verbundenes Add-on werden gepuffert und beim
Verbinden nachgeliefert. Jeder Befehl läuft als eigene Aufgabe, damit ein
langer Befehl (Anmeldung, Wählen) die folgenden (z. B. Auflegen) nicht blockiert.
"""
import asyncio
import logging
import os

from tgc.protocol import ProtocolError, check_command, decode, encode, redact

log = logging.getLogger('worker.server')

BACKLOG_LIMIT = 200


class Server:
    def __init__(self, path, on_command):
        self._path = path
        self._on_command = on_command
        self._server = None
        self._writer = None
        self._backlog = []
        self._tasks = set()

    async def start(self):
        if os.path.exists(self._path):
            os.unlink(self._path)  # Rest eines abgestürzten Prozesses
        old = os.umask(0o177)
        try:
            self._server = await asyncio.start_unix_server(self._client, path=self._path)
        finally:
            os.umask(old)
        os.chmod(self._path, 0o600)

    def emit(self, typ, **data):
        line = encode(typ, **data)
        writer = self._writer
        if writer is None or writer.is_closing():
            self._backlog.append(line)
            del self._backlog[:-BACKLOG_LIMIT]
            return
        writer.write(line)

    async def _client(self, reader, writer):
        if self._writer is not None:
            self._writer.close()
        self._writer = writer
        for line in self._backlog:
            writer.write(line)
        self._backlog.clear()
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    message = decode(line)
                    check_command(message)
                except ProtocolError as e:
                    self.emit('error', text=str(e))
                    continue
                log.info('Befehl %s', redact(message))
                task = asyncio.create_task(self._run(message))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        except ConnectionError:
            pass
        finally:
            if self._writer is writer:
                self._writer = None
            writer.close()

    async def _run(self, message):
        try:
            await self._on_command(message)
        except Exception as e:
            log.exception('Befehl %s fehlgeschlagen', message['typ'])
            self.emit('error', text=f'{message["typ"]}: {e}')

    async def close(self):
        for task in list(self._tasks):
            task.cancel()
        if self._writer is not None:
            try:
                await self._writer.drain()
            except ConnectionError:
                pass
            self._writer.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        if os.path.exists(self._path):
            os.unlink(self._path)
```

`addon/script.telegram.calls/worker/main.py`:

```python
#!/usr/bin/env python3
"""Anrufprozess: Telegram, Anruf und Ton außerhalb von Kodi.

Start: python3 worker/main.py --data <addon_data>
Die erste Zeile auf stdin ist JSON mit api_id, api_hash, direkt, echo und
mikrofon (so stehen die Werte nicht in der Prozessliste). Danach spricht das
Add-on über <data>/worker.sock mit dem Prozess (tgc/protocol.py).
Exit-Code 3: Ein anderer Anrufprozess läuft schon mit diesen Daten.
"""
import argparse
import asyncio
import fcntl
import json
import logging
import os
import signal
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
# Hinten anhängen: Auf dem Pi gibt es nur diese Pakete; auf dem Entwicklungsrechner gewinnen die installierten.
for _path in (os.path.join(ADDON, 'resources', 'lib'), os.path.join(ADDON, 'vendor')):
    if _path not in sys.path:
        sys.path.append(_path)

import mic  # noqa: E402
from server import Server  # noqa: E402

log = logging.getLogger('worker')

EXIT_LOCKED = 3
STATUS_INTERVAL = 5
RECONNECT_INTERVAL = 10


def acquire_lock(path):
    """Sperrdatei: verhindert zwei Telegram-Clients auf derselben Session. None, wenn belegt."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


class Worker:
    def __init__(self, init, data_dir):
        self.init = init
        self.data_dir = data_dir
        self.server = Server(os.path.join(data_dir, 'worker.sock'), self.on_command)
        self.quit = asyncio.Event()
        self.client = None
        self.session = None
        self.calls = None

    async def run(self):
        from telethon import TelegramClient

        from session import SESSION_NAME, TelegramSession

        self.client = TelegramClient(os.path.join(self.data_dir, SESSION_NAME),
                                     int(self.init['api_id']), self.init['api_hash'])
        self.session = TelegramSession(self.client, self.server.emit, self.data_dir, self.on_authorized)
        await self.server.start()
        status = asyncio.create_task(self.report_status())
        try:
            if await self.connect():
                authorized = await self.client.is_user_authorized()
                if authorized:
                    await self.on_authorized()
                self.server.emit('ready', angemeldet=authorized)
                await self.quit.wait()
        finally:
            status.cancel()
            await self.shutdown()

    async def connect(self):
        while not self.quit.is_set():
            try:
                await self.client.connect()
                return True
            except OSError as e:
                log.warning('Telegram nicht erreichbar: %s', e)
                try:
                    await asyncio.wait_for(self.quit.wait(), RECONNECT_INTERVAL)
                except TimeoutError:
                    pass
        return False

    async def on_authorized(self):
        if self.calls is not None:
            return
        from pytgcalls import PyTgCalls

        from audio import AudioFactory
        from callmanager import CallManager
        from tgbackend import TgCallsBackend

        pytg = PyTgCalls(self.client)
        await pytg.start()
        backend = TgCallsBackend(self.client, pytg)
        audio = AudioFactory(self.init, self.data_dir, self.server.emit)
        self.calls = CallManager(backend, self.server.emit, audio, self.session.name_for)
        backend.bind(self.calls)

    async def on_command(self, message):
        from telethon.errors import UnauthorizedError

        try:
            await self._dispatch(message)
        except UnauthorizedError as e:
            # Session in der Telegram-App abgemeldet oder widerrufen: zurück zur Anmeldung.
            log.warning('Nicht mehr angemeldet: %s', e)
            self.server.emit('ready', angemeldet=False)

    async def _dispatch(self, message):
        typ = message['typ']
        if typ == 'quit':
            self.quit.set()
            return
        session = self.session
        account = {
            'login_qr': lambda: session.login_qr(),
            'login_phone': lambda: session.login_phone(message['nummer']),
            'login_code': lambda: session.login_code(message['code']),
            'login_password': lambda: session.login_password(message['passwort']),
            'contacts': lambda: session.send_contacts(),
            'logout': self.logout,
        }
        if typ in account:
            await account[typ]()
            return
        if self.calls is None:
            self.server.emit('error', text='Nicht angemeldet')
            return
        calls = self.calls
        actions = {
            'call': lambda: calls.call(int(message['id'])),
            'accept': calls.accept,
            'decline': calls.decline,
            'hangup': calls.hangup,
            'mute': lambda: calls.set_mute(bool(message['an'])),
        }
        await actions[typ]()

    async def logout(self):
        """Nur für das Abmelden aus den Einstellungen: abmelden und beenden."""
        if self.calls is not None:
            await self.calls.shutdown()
        await self.session.logout()
        self.server.emit('ready', angemeldet=False)
        self.quit.set()

    async def report_status(self):
        last = None
        card = mic.card_of(self.init.get('mikrofon') or mic.DEVICE)
        while True:
            current = {
                'telegram_verbunden': bool(self.client and self.client.is_connected()),
                'mikrofon_ok': await asyncio.to_thread(mic.mic_ok, card),
            }
            if current != last:
                self.server.emit('status', **current)
                last = current
            await asyncio.sleep(STATUS_INTERVAL)

    async def shutdown(self):
        if self.calls is not None:
            await self.calls.shutdown()
        if self.client is not None:
            await self.client.disconnect()
        await self.server.close()


async def amain(init, data_dir):
    worker = Worker(init, data_dir)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, worker.quit.set)
    await worker.run()


def main():
    parser = argparse.ArgumentParser(description='Anrufprozess für script.telegram.calls')
    parser.add_argument('--data', required=True, help='Datenordner (addon_data des Add-ons)')
    args = parser.parse_args()
    os.umask(0o077)  # Session, Bilder, SDP: nur für den Eigentümer
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format='%(asctime)s %(name)s %(levelname)s: %(message)s')
    logging.getLogger('telethon').setLevel(logging.WARNING)
    os.makedirs(args.data, mode=0o700, exist_ok=True)
    lock = acquire_lock(os.path.join(args.data, 'worker.lock'))
    if lock is None:
        print('Anrufprozess läuft bereits', file=sys.stderr)
        sys.exit(EXIT_LOCKED)
    init = json.loads(sys.stdin.readline())
    asyncio.run(amain(init, args.data))


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Tests und ruff grün**

Run: `.venv/bin/pytest -q tests/test_server.py tests/test_main.py && .venv/bin/ruff check .`
Expected: `11 passed`, ruff `All checks passed!`

- [ ] **Step 5: `worker/main.py` ausführbar machen**

Run: `chmod +x addon/script.telegram.calls/worker/main.py`

- [ ] **Step 6: Stand festhalten** – kein Commit; volle Testsuite `.venv/bin/pytest -q` grün.

---

### Task 11: Prozess-Client des Add-ons

**Files:**
- Test: `tests/fake_worker.py`
- Test: `tests/test_workerclient.py`

**Interfaces:**
- Consumes: `tgc.protocol` (Task 3).
- Produces: `tgc.workerclient.WorkerClient(argv, init, sock_path, on_event, env=None, log_path=None, timeout=20)` mit `start()` (wirft `WorkerError` mit „Code N“, wenn der Prozess endet, oder „antwortet nicht“), `send(typ, **data)`, `stop(timeout=3)` (schickt `quit`, beendet notfalls hart), `returncode()`; `on_event` bekommt Ereignis-Dicts und bei unerwartetem Verbindungsende `{'typ': '_lost'}`.

- [ ] **Step 1: Tests schreiben**

`tests/fake_worker.py`:

```python
"""Ersatz für worker/main.py in Tests: Socket, ready-Ereignis, Echo der Befehle, quit."""
import json
import os
import socket
import sys

data = sys.argv[1]
init = json.loads(sys.stdin.readline())
path = os.path.join(data, 'worker.sock')
if os.path.exists(path):
    os.unlink(path)
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(path)
server.listen(1)
conn, _ = server.accept()
conn.sendall((json.dumps({'typ': 'ready', 'init': init}) + '\n').encode())
for line in conn.makefile('rb'):
    message = json.loads(line)
    if message['typ'] == 'quit':
        break
    if message['typ'] == 'crash':
        os._exit(9)
    conn.sendall((json.dumps({'typ': 'echo', 'befehl': message}) + '\n').encode())
conn.close()
```

`tests/test_workerclient.py`:

```python
import os
import queue
import sys

import pytest

from tgc.workerclient import WorkerClient, WorkerError

FAKE = os.path.join(os.path.dirname(__file__), 'fake_worker.py')


def client(tmp_path, argv=None, **kwargs):
    events = queue.Queue()
    worker = WorkerClient(argv or [sys.executable, FAKE, str(tmp_path)], {'api_id': 1},
                          str(tmp_path / 'worker.sock'), events.put, **kwargs)
    return worker, events


def test_start_liefert_ready_mit_init_daten(tmp_path):
    worker, events = client(tmp_path)
    worker.start()
    assert events.get(timeout=5) == {'typ': 'ready', 'init': {'api_id': 1}}
    worker.send('call', id=5)
    assert events.get(timeout=5) == {'typ': 'echo', 'befehl': {'typ': 'call', 'id': 5}}
    worker.stop()


def test_quit_beendet_prozess(tmp_path):
    worker, events = client(tmp_path)
    worker.start()
    events.get(timeout=5)
    proc = worker._proc
    worker.stop()
    assert proc.poll() == 0
    with pytest.raises(queue.Empty):
        events.get(timeout=0.3)  # kein _lost bei gewolltem Ende


def test_absturz_meldet_lost(tmp_path):
    worker, events = client(tmp_path)
    worker.start()
    events.get(timeout=5)
    worker.send('crash')
    assert events.get(timeout=5) == {'typ': '_lost'}
    worker.stop()


def test_sofortiges_ende_wird_als_fehler_gemeldet(tmp_path):
    worker, _ = client(tmp_path, argv=[sys.executable, '-c', 'import sys; sys.exit(3)'])
    with pytest.raises(WorkerError, match='Code 3'):
        worker.start()


def test_zeitueberschreitung(tmp_path):
    worker, _ = client(tmp_path, argv=[sys.executable, '-c', 'import time; time.sleep(30)'], timeout=0.5)
    with pytest.raises(WorkerError, match='antwortet nicht'):
        worker.start()


def test_log_datei_ist_privat(tmp_path):
    log = tmp_path / 'worker.log'
    worker, events = client(tmp_path, log_path=str(log))
    worker.start()
    events.get(timeout=5)
    worker.stop()
    assert oct(os.stat(log).st_mode & 0o777) == '0o600'
```

- [ ] **Step 2: Tests laufen lassen, sie müssen scheitern**

Run: `.venv/bin/pytest -q tests/test_workerclient.py`
Expected: FAIL mit `ModuleNotFoundError: No module named 'tgc.workerclient'`

- [ ] **Step 3: Implementierung schreiben**

`addon/script.telegram.calls/resources/lib/tgc/workerclient.py`:

```python
"""Startet den Anrufprozess und hält die Socket-Verbindung zu ihm (Add-on-Seite, ohne Kodi testbar).

Ereignisse kommen in einem eigenen Thread an und gehen an on_event(dict).
Bricht die Verbindung ab, ohne dass stop() aufgerufen wurde, kommt
{'typ': '_lost'}.
"""
import json
import os
import socket
import subprocess
import threading
import time

from tgc.protocol import ProtocolError, decode, encode


class WorkerError(RuntimeError):
    pass


class WorkerClient:
    def __init__(self, argv, init, sock_path, on_event, env=None, log_path=None, timeout=20):
        self._argv = argv
        self._init = init
        self._sock_path = sock_path
        self._on_event = on_event
        self._env = env
        self._log_path = log_path
        self._timeout = timeout
        self._proc = None
        self._sock = None
        self._lock = threading.Lock()
        self._stopping = False

    def start(self):
        self._stopping = False
        stderr = subprocess.DEVNULL
        if self._log_path:
            stderr = os.open(self._log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            self._proc = subprocess.Popen(self._argv, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                          stderr=stderr, env=self._env, start_new_session=True)
        finally:
            if self._log_path:
                os.close(stderr)
        self._proc.stdin.write((json.dumps(self._init) + '\n').encode())
        self._proc.stdin.close()
        self._sock = self._connect()
        threading.Thread(target=self._read, args=(self._sock,), name='anrufprozess', daemon=True).start()

    def _connect(self):
        deadline = time.monotonic() + self._timeout
        while True:
            code = self._proc.poll()
            if code is not None:
                raise WorkerError(f'Anrufprozess beendet (Code {code})')
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(self._sock_path)
                return sock
            except (FileNotFoundError, ConnectionRefusedError):
                sock.close()
            if time.monotonic() > deadline:
                self._kill()
                raise WorkerError('Anrufprozess antwortet nicht')
            time.sleep(0.1)

    def _read(self, sock):
        with sock.makefile('rb') as stream:
            try:
                for line in stream:
                    try:
                        self._on_event(decode(line))
                    except ProtocolError:
                        continue
            except OSError:
                pass
        if not self._stopping:
            self._on_event({'typ': '_lost'})

    def send(self, typ, **data):
        with self._lock:
            try:
                self._sock.sendall(encode(typ, **data))
            except (OSError, AttributeError):
                pass  # Verlust meldet der Lesethread

    def stop(self, timeout=3):
        self._stopping = True
        if self._proc is None:
            return
        self.send('quit')
        try:
            self._proc.wait(timeout)
        except subprocess.TimeoutExpired:
            self._kill()
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        self._proc = None

    def returncode(self):
        return None if self._proc is None else self._proc.poll()

    def _kill(self):
        self._proc.kill()
        self._proc.wait()
```

- [ ] **Step 4: Tests und ruff grün**

Run: `.venv/bin/pytest -q tests/test_workerclient.py && .venv/bin/ruff check .`
Expected: `6 passed`, ruff `All checks passed!`

- [ ] **Step 5: Stand festhalten** – kein Commit; volle Testsuite `.venv/bin/pytest -q` grün.

---

### Task 12: Anrufprozess auf dem Pi ohne Kodi testen

Erster echter Lauf des Anrufprozesses. `tools/wctl.py` bedient ihn von der Kommandozeile, wie `call.py` in Teilprojekt 1. Die Anmeldung landet schon im Datenordner des Add-ons, damit das Add-on sie später übernimmt. Der Nutzer muss für die Anmeldung (QR-Code scannen) und die Anrufe dabei sein.

**Files:**
- Create: `tools/wctl.py`

**Interfaces:**
- Consumes: `worker/main.py` (Task 10), `tgc.workerclient.WorkerClient` (Task 11), `/storage/tgcalls-test/config.ini` (nur gelesen, nie ausgegeben).
- Produces: angemeldete Session in `/storage/.kodi/userdata/addon_data/script.telegram.calls/telegram.session`; Erfahrungswerte für die Abnahme.

- [ ] **Step 1: `tools/wctl.py` schreiben**

`tools/wctl.py`:

```python
#!/usr/bin/env python3
"""Bedient den Anrufprozess ohne Kodi (Test auf dem Pi).

Aufruf auf dem Pi:
  python3 wctl.py --addon /storage/tgcalls-addon --config /storage/tgcalls-test/config.ini \
                  [--data DIR] [--direkt] [--echo webrtc|daempfen|aus]
Eingaben: kontakte | call <id> | accept | decline | hangup | mute | telefon | quit
Ton über Kodi muss hier von Hand gestartet werden; wctl meldet play_kodi mit dem SDP-Pfad.
api_id/api_hash werden aus der Konfiguration gelesen und nie ausgegeben.
"""
import argparse
import configparser
import getpass
import io
import os
import queue
import shutil
import sys
import threading

DEFAULT_DATA = '/storage/.kodi/userdata/addon_data/script.telegram.calls'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--addon', required=True, help='Ordner des Add-ons (mit worker/ und vendor/)')
    parser.add_argument('--config', required=True, help='ini-Datei mit [telegram] api_id, api_hash')
    parser.add_argument('--data', default=DEFAULT_DATA)
    parser.add_argument('--direkt', action='store_true', help='Ausgabe direkt per ALSA, wenn HDMI frei')
    parser.add_argument('--echo', default='webrtc', choices=['webrtc', 'daempfen', 'aus'])
    args = parser.parse_args()

    sys.path.insert(0, os.path.join(args.addon, 'resources', 'lib'))
    sys.path.insert(0, os.path.join(args.addon, 'vendor'))
    import qrcode

    from tgc.workerclient import WorkerClient, WorkerError

    config = configparser.ConfigParser()
    config.read(args.config)
    init = {'api_id': config.getint('telegram', 'api_id'), 'api_hash': config.get('telegram', 'api_hash'),
            'direkt': args.direkt, 'echo': args.echo, 'mikrofon': 'plughw:CARD=Webcam,DEV=0'}
    os.makedirs(args.data, mode=0o700, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([os.path.join(args.addon, 'vendor'),
                                                       os.path.join(args.addon, 'resources', 'lib')]))
    events = queue.Queue()
    worker = WorkerClient([shutil.which('python3') or '/usr/bin/python3',
                           os.path.join(args.addon, 'worker', 'main.py'), '--data', args.data],
                          init, os.path.join(args.data, 'worker.sock'), events.put, env=env,
                          log_path=os.path.join(args.data, 'worker.log'))
    try:
        worker.start()
    except WorkerError as e:
        sys.exit(f'Anrufprozess startet nicht: {e} (Log: {args.data}/worker.log)')

    def show_events():
        while True:
            message = events.get()
            typ = message['typ']
            if typ == 'qr':
                code = qrcode.QRCode(border=1)
                code.add_data(message['url'])
                text = io.StringIO()
                code.print_ascii(out=text, invert=True)
                print(text.getvalue() + 'In Telegram: Einstellungen → Geräte → Gerät verbinden', flush=True)
            elif typ == 'contacts':
                for entry in message['liste']:
                    print(f'{entry["id"]:>12}  {entry["name"]}{"  (Gruppe)" if entry["gruppe"] else ""}')
            elif typ == 'ready' and not message.get('angemeldet'):
                print('Nicht angemeldet: QR-Code folgt (oder "telefon" eingeben).', flush=True)
                worker.send('login_qr')
            elif typ == 'need_code':
                worker.send('login_code', code=input('Code: ').strip())
            elif typ == 'need_password':
                worker.send('login_password', passwort=getpass.getpass('Zwei-Faktor-Passwort: '))
            else:
                print('<', message, flush=True)
            if typ == '_lost':
                print('Anrufprozess beendet.')
                os._exit(1)

    threading.Thread(target=show_events, daemon=True).start()
    muted = False
    try:
        for line in sys.stdin:
            parts = line.split()
            if not parts:
                continue
            command = parts[0]
            if command == 'kontakte':
                worker.send('contacts')
            elif command == 'call' and len(parts) == 2:
                worker.send('call', id=int(parts[1]))
            elif command in ('accept', 'decline', 'hangup'):
                worker.send(command)
            elif command == 'mute':
                muted = not muted
                worker.send('mute', an=muted)
            elif command == 'telefon':
                worker.send('login_phone', nummer=input('Telefonnummer (+49…): ').strip())
            elif command == 'quit':
                break
            else:
                print('Eingaben: kontakte | call <id> | accept | decline | hangup | mute | telefon | quit')
    except KeyboardInterrupt:
        pass
    finally:
        worker.stop()


if __name__ == '__main__':
    main()
```

Run: `.venv/bin/ruff check tools/wctl.py && .venv/bin/python -m py_compile tools/wctl.py`
Expected: keine Befunde.

- [ ] **Step 2: Auf den Testort kopieren** (nicht in Kodis Add-on-Ordner)

Run:
```bash
ssh root@192.168.178.10 'cd /storage/tgcalls-test && python3 check.py --guard'
tools/deploy.sh /storage/tgcalls-addon
scp tools/wctl.py root@192.168.178.10:/storage/tgcalls-addon/
```

- [ ] **Step 3: Anmelden per QR-Code** (Nutzer scannt)

Dem Nutzer den Befehl geben (interaktiv, er tippt ihn mit `ssh -t` oder direkt am Pi):
```
python3 /storage/tgcalls-addon/wctl.py --addon /storage/tgcalls-addon --config /storage/tgcalls-test/config.ini
```
Expected: ASCII-QR-Code; nach dem Scannen `login_ok`. Danach `kontakte` eingeben: Liste mit IDs erscheint, Philipp darunter. `quit`.
Prüfen: `ssh root@192.168.178.10 'stat -c %a /storage/.kodi/userdata/addon_data/script.telegram.calls/telegram.session'` → `600`. Nicht den Inhalt ansehen.

- [ ] **Step 4: Ausgehender Anruf mit Ton über Kodi** (Nutzer und Philipp)

Kodi darf nichts abspielen. wctl starten wie in Step 3 ohne `--direkt`, `call <Philipps ID>`. Sobald `play_kodi` erscheint, startet wctl den Ton nicht selbst: in einem zweiten Terminal
`ssh root@192.168.178.10 "python3 -c \"import sys; sys.path.insert(0, '/storage/tgcalls-test'); from common import kodi_rpc; kodi_rpc('Player.Open', {'item': {'file': '/storage/.kodi/userdata/addon_data/script.telegram.calls/anruf.sdp'}})\""`
Prüfen mit Philipp: beide hören sich; Zählprobe; hört Philipp sich als Echo? Dann `mute` (Philipp hört nichts mehr), `mute`, `hangup`. Im Log `worker.log` darf keine Telefonnummer stehen: `ssh root@192.168.178.10 'grep -c "+49" /storage/.kodi/userdata/addon_data/script.telegram.calls/worker.log'` → `0`.

- [ ] **Step 5: Eingehender Anruf und direkte Ausgabe**

wctl mit `--direkt` starten (nur sinnvoll, wenn der Messtest die direkte Ausgabe empfohlen hat und `geraet.py` „closed“ zeigt). Philipp ruft an: `<` `incoming` erscheint, Klingelton aus den Boxen; `accept`. Gespräch, Zählprobe, Echo prüfen. Philipp legt auf → `ended` mit `beendet`. Nochmal anrufen lassen und `decline` → bei Philipp „abgelehnt“. Einmal 45 s klingeln lassen → `verpasst`.

- [ ] **Step 6: Echo-Verfahren vergleichen**

Je ein kurzes Gespräch mit `--echo webrtc` und `--echo daempfen`. Philipp beurteilt Echo und Abschneiden beim Dazwischenreden. CPU während des Gesprächs: `ssh root@192.168.178.10 'top -b -n 1 | grep main.py'`. Ergebnis in `docs/messtest-teilprojekt-2.md` unter „Gespräche mit dem Anrufprozess“ eintragen (Verzögerung je Weg, Echo je Verfahren, CPU). Falls `webrtc` schlechter ist als erwartet: Standard der Einstellung `echo` in Task 15 auf `daempfen`.

- [ ] **Step 7: Wächter nachher und Stand festhalten**

Run: `ssh root@192.168.178.10 'cd /storage/tgcalls-test && python3 check.py --guard'` → OK. Kein Commit.

---

### Task 13: Zustandslogik der Oberfläche

**Files:**
- Test: `tests/test_appstate.py`

**Interfaces:**
- Consumes: Ereignisse aus Task 3/10, eine Favoritenliste mit `ids`, `add`, `remove`, `move` (Task 4).
- Produces: `tgc.appstate.AppState(favorites)` mit `start()`, `on_event(message, now)`, `on_user(action, now, **data)`, `tick(now)` → Liste von Aktionen (siehe Docstring), dazu `screen`, `contacts`, `qr`, `banner`, `call`, `ringing`, `home_items()`, `is_favorite(id)`, `call_status(now)`, `contact(id)`, `find_contact(text) -> int | None` (Position in `contacts`). Benutzeraktionen: `call{id}`, `accept`, `decline`, `hangup`, `mute`, `back`, `exit`, `open_contacts`, `fav_add{id}`, `fav_remove{id}`, `fav_move{id, step}`, `login_phone_start`, `login_phone{nummer}`, `login_code{code}`, `login_password{passwort}`, `login_cancel`.

- [ ] **Step 1: Tests schreiben**

`tests/test_appstate.py`:

```python
from tgc.appstate import AppState


class Fav:
    def __init__(self, ids=()):
        self.ids = list(ids)

    def add(self, i):
        if i not in self.ids:
            self.ids.append(i)

    def remove(self, i):
        if i in self.ids:
            self.ids.remove(i)

    def move(self, i, step):
        self.moved = (i, step)


CONTACTS = [
    {'id': 1, 'name': 'Anna', 'bild': '/b/1.jpg', 'gruppe': False},
    {'id': 2, 'name': 'Philipp', 'bild': '', 'gruppe': False},
    {'id': 9, 'name': 'Verein', 'bild': '', 'gruppe': True},
]


def logged_in(favorites=(2, 1, 9, 77)):
    state = AppState(Fav(favorites))
    state.on_event({'typ': 'ready', 'angemeldet': True}, 0)
    state.on_event({'typ': 'contacts', 'liste': CONTACTS}, 0)
    return state


def kinds(actions):
    return [a[0] for a in actions]


def test_ohne_anmeldung_qr_bildschirm():
    state = AppState(Fav())
    assert state.on_event({'typ': 'ready', 'angemeldet': False}, 0) == [('show', 'login'),
                                                                      ('send', 'login_qr', {})]
    assert state.on_event({'typ': 'qr', 'url': 'u', 'bild': '/q.png'}, 0) == [('refresh',)]
    assert state.qr == '/q.png'
    assert state.on_event({'typ': 'login_ok'}, 0) == [('show', 'home'), ('send', 'contacts', {})]


def test_anmeldung_per_telefon():
    state = AppState(Fav())
    state.on_event({'typ': 'ready', 'angemeldet': False}, 0)
    assert state.on_user('login_phone_start', 0) == [('ask', 'nummer')]
    assert state.on_user('login_phone', 0, nummer='+49') == [('send', 'login_phone', {'nummer': '+49'})]
    assert state.on_event({'typ': 'need_code'}, 0) == [('ask', 'code')]
    assert state.on_event({'typ': 'login_error', 'grund': 'Code falsch', 'erneut': 'code'}, 0) == [
        ('notify', 'Code falsch'), ('ask', 'code')]
    assert state.on_event({'typ': 'login_error', 'grund': 'Code abgelaufen'}, 0)[-1] == ('send', 'login_qr', {})
    assert state.on_user('login_cancel', 0) == [('send', 'login_qr', {})]


def test_favoriten_in_reihenfolge_nur_bekannte_personen():
    state = logged_in()
    assert [c['name'] for c in state.home_items()] == ['Philipp', 'Anna']


def test_anrufen_und_gespraech():
    state = logged_in()
    actions = state.on_user('call', 10, id=2)
    assert actions == [('pause_kodi',), ('screensaver', False), ('send', 'call', {'id': 2}), ('show', 'call')]
    assert state.call_status(10) == 'Wählt …'
    state.on_event({'typ': 'outgoing_state', 'zustand': 'klingelt'}, 11)
    assert state.call_status(11) == 'Klingelt …'
    state.on_event({'typ': 'connected'}, 12)
    assert state.call_status(75) == 'Verbunden 01:03'
    assert state.tick(75) == [('refresh_call',)]


def test_ende_wird_drei_sekunden_gezeigt_dann_zurueck():
    state = logged_in()
    state.on_user('open_contacts', 0)
    state.on_user('call', 1, id=1)
    state.on_event({'typ': 'ended', 'grund': 'besetzt'}, 5)
    assert state.call_status(6) == 'Besetzt'
    assert state.tick(7) == []
    assert state.tick(8) == [('show', 'contacts')]
    assert state.call is None


def test_gruppe_und_fehlendes_mikrofon_verhindern_anruf():
    state = logged_in()
    assert kinds(state.on_user('call', 0, id=9)) == ['notify']
    state.on_event({'typ': 'status', 'telegram_verbunden': True, 'mikrofon_ok': False}, 0)
    assert 'Mikrofon' in state.banner
    assert kinds(state.on_user('call', 0, id=2)) == ['notify']
    assert state.call is None


def test_keine_verbindung_im_banner():
    state = logged_in()
    state.on_event({'typ': 'status', 'telegram_verbunden': False, 'mikrofon_ok': True}, 0)
    assert state.banner == 'Keine Verbindung zu Telegram'


def test_eingehend_annehmen():
    state = logged_in()
    actions = state.on_event({'typ': 'incoming', 'id': 1, 'name': 'Anna'}, 0)
    assert actions == [('pause_kodi',), ('screensaver', False), ('ring', True)]
    assert state.ringing['bild'] == '/b/1.jpg'
    assert state.on_user('accept', 1) == [('ring', False), ('send', 'accept', {}), ('show', 'call')]
    assert state.call['name'] == 'Anna' and state.ringing is None


def test_eingehend_ablehnen_und_verpasst():
    state = logged_in()
    state.on_event({'typ': 'incoming', 'id': 1, 'name': 'Anna'}, 0)
    assert state.on_user('decline', 1) == [('ring', False), ('send', 'decline', {}), ('screensaver', True)]
    state.on_event({'typ': 'incoming', 'id': 1, 'name': 'Anna'}, 2)
    actions = state.on_event({'typ': 'ended', 'grund': 'verpasst'}, 3)
    assert actions == [('ring', False), ('screensaver', True), ('notify', 'Verpasster Anruf: Anna')]


def test_incoming_waehrend_anruf_wird_ignoriert():
    state = logged_in()
    state.on_user('call', 0, id=2)
    assert state.on_event({'typ': 'incoming', 'id': 1, 'name': 'Anna'}, 1) == []
    assert state.ringing is None


def test_zurueck_im_anruf_legt_auf_sonst_schliessen_fragen():
    state = logged_in()
    assert state.on_user('back', 0) == [('confirm_exit',)]
    state.on_user('open_contacts', 0)
    assert state.on_user('back', 0) == [('show', 'home')]
    state.on_user('call', 0, id=2)
    assert state.on_user('back', 1) == [('send', 'hangup', {})]
    state.on_event({'typ': 'ended', 'grund': 'aufgelegt'}, 2)
    assert state.on_user('back', 2) == [('show', 'home')]
    assert state.on_user('hangup', 2) == []


def test_stumm_schaltet_um():
    state = logged_in()
    state.on_user('call', 0, id=2)
    assert state.on_user('mute', 1)[0] == ('send', 'mute', {'an': True})
    assert state.on_user('mute', 2)[0] == ('send', 'mute', {'an': False})


def test_verlust_beendet_anruf_und_startet_neu():
    state = logged_in()
    state.on_user('call', 0, id=2)
    actions = state.on_event({'typ': '_lost'}, 1)
    assert actions == [('show', 'home'), ('stop_kodi',), ('screensaver', True),
                       ('notify', 'Anrufteil neu gestartet'), ('restart_worker',)]
    assert state.call is None


def test_kodi_wiedergabe_und_favoriten():
    state = logged_in()
    assert state.on_event({'typ': 'play_kodi', 'sdp_pfad': '/a.sdp'}, 0) == [('play_kodi', '/a.sdp')]
    assert state.on_event({'typ': 'stop_kodi'}, 0) == [('stop_kodi',)]
    state.on_user('fav_remove', 0, id=2)
    assert not state.is_favorite(2)
    state.on_user('fav_add', 0, id=2)
    assert state.favorites.ids[-1] == 2
    state.on_user('fav_move', 0, id=2, step=-1)
    assert state.favorites.moved == (2, -1)


def test_unbekannte_ereignisse_und_aktionen_tun_nichts():
    state = logged_in()
    assert state.on_event({'typ': 'neu'}, 0) == []
    assert state.on_user('neu', 0) == []


def test_start_zeigt_startseite_bis_ready():
    state = AppState(Fav())
    assert state.start() == [('show', 'home')]
    assert state.banner == 'Verbinde mit Telegram …'
    assert state.on_event({'typ': 'ready', 'angemeldet': False}, 0)[0] == ('show', 'login')
    assert state.banner == ''


def test_kontaktsuche():
    state = logged_in()
    assert state.find_contact('phi') == 1
    assert state.find_contact('ANN') == 0
    assert state.find_contact('ver') == 2
    assert state.find_contact('lipp') == 1
    assert state.find_contact('xyz') is None
    assert state.find_contact('  ') is None
```

- [ ] **Step 2: Tests laufen lassen, sie müssen scheitern**

Run: `.venv/bin/pytest -q tests/test_appstate.py`
Expected: FAIL mit `ModuleNotFoundError: No module named 'tgc.appstate'`

- [ ] **Step 3: Implementierung schreiben**

`addon/script.telegram.calls/resources/lib/tgc/appstate.py`:

```python
"""Zustandslogik der Oberfläche, ohne Kodi testbar.

on_event (Ereignis vom Anrufprozess), on_user (Taste oder Klick) und tick
(Uhr) ändern den Zustand und geben eine Liste von Aktionen zurück, die
kodi_ui ausführt:

  ('send', typ, daten)     Befehl an den Anrufprozess
  ('show', bildschirm)     'login' | 'home' | 'contacts' | 'call'
  ('refresh',)             aktuellen Bildschirm neu zeichnen
  ('refresh_call',)        nur die Statuszeile im Anruf (Uhr)
  ('ring', an)             Klingeldialog zeigen oder schließen
  ('play_kodi', pfad) | ('stop_kodi',) | ('pause_kodi',)
  ('screensaver', erlaubt) False: Bildschirmschoner beenden und unterdrücken
  ('notify', text)
  ('ask', 'nummer' | 'code' | 'passwort')
  ('confirm_exit',) | ('exit',) | ('restart_worker',)
"""

GRUND = {
    'aufgelegt': 'Aufgelegt',
    'beendet': 'Gespräch beendet',
    'abgelehnt': 'Abgelehnt',
    'besetzt': 'Besetzt',
    'keine_antwort': 'Keine Antwort',
    'verpasst': 'Verpasst',
    'abgebrochen': 'Verbindung abgebrochen',
    'tonausgabe': 'Tonausgabe fehlgeschlagen',
    'fehler': 'Fehler beim Verbinden',
}
ENDED_SHOW_SECONDS = 3
NO_MIC = 'Kein Mikrofon: Webcam anschließen bzw. Mikrofon-Regler prüfen'


class AppState:
    def __init__(self, favorites):
        self.favorites = favorites
        self.screen = None
        self.previous = 'home'
        self.contacts = []
        self.qr = ''
        self.banner = ''
        self.mic_ok = True
        self.call = None     # id, name, bild, status, since, stumm, ended_at
        self.ringing = None  # id, name, bild

    # --- Abfragen für die Fenster ---------------------------------------

    def contact(self, user_id):
        for entry in self.contacts:
            if entry['id'] == user_id:
                return entry
        return {'id': user_id, 'name': str(user_id), 'bild': '', 'gruppe': False}

    def home_items(self):
        known = {c['id']: c for c in self.contacts if not c['gruppe']}
        return [known[i] for i in self.favorites.ids if i in known]

    def is_favorite(self, user_id):
        return user_id in self.favorites.ids

    def find_contact(self, text):
        """Position des ersten Kontakts, dessen Name mit text beginnt, sonst der ihn enthält; sonst None."""
        needle = text.strip().casefold()
        if not needle:
            return None
        names = [c['name'].casefold() for c in self.contacts]
        for test in (lambda n: n.startswith(needle), lambda n: needle in n):
            for index, name in enumerate(names):
                if test(name):
                    return index
        return None

    def call_status(self, now):
        call = self.call
        if call is None:
            return ''
        if call['ended_at'] is None and call['since'] is not None:
            seconds = int(now - call['since'])
            return f'Verbunden {seconds // 60:02d}:{seconds % 60:02d}'
        return call['status']

    # --- Eingänge -------------------------------------------------------

    def start(self):
        """Sofort beim Öffnen: Startseite zeigen, bis der Anrufprozess meldet, ob man angemeldet ist."""
        self.banner = 'Verbinde mit Telegram …'
        return self._show('home')

    def on_event(self, message, now):
        handler = getattr(self, '_ev_' + message['typ'], None)
        return handler(message, now) if handler else []

    def on_user(self, action, now, **data):
        handler = getattr(self, '_user_' + action, None)
        return handler(now, **data) if handler else []

    def tick(self, now):
        call = self.call
        if call is None:
            return []
        if call['ended_at'] is not None:
            if now - call['ended_at'] >= ENDED_SHOW_SECONDS:
                self.call = None
                return self._show(self.previous)
            return []
        if call['since'] is not None and self.screen == 'call':
            return [('refresh_call',)]
        return []

    # --- Ereignisse -----------------------------------------------------

    def _ev_ready(self, message, now):
        if self.banner == 'Verbinde mit Telegram …':
            self.banner = ''
        if message.get('angemeldet'):
            return self._show('home') + [('send', 'contacts', {})]
        return self._show('login') + [('send', 'login_qr', {})]

    def _ev_login_ok(self, message, now):
        return self._show('home') + [('send', 'contacts', {})]

    def _ev_qr(self, message, now):
        self.qr = message.get('bild', '')
        return [('refresh',)] if self.screen == 'login' else []

    def _ev_need_code(self, message, now):
        return [('ask', 'code')]

    def _ev_need_password(self, message, now):
        return [('ask', 'passwort')]

    def _ev_login_error(self, message, now):
        actions = [('notify', message.get('grund', 'Anmeldung fehlgeschlagen'))]
        again = message.get('erneut')
        if again in ('code', 'passwort'):
            return actions + [('ask', again)]
        return actions + [('send', 'login_qr', {})]

    def _ev_contacts(self, message, now):
        self.contacts = message.get('liste', [])
        return [('refresh',)]

    def _ev_incoming(self, message, now):
        if self.call is not None or self.ringing is not None:
            return []  # der Anrufprozess lehnt selbst als besetzt ab
        user_id = message['id']
        self.ringing = {'id': user_id, 'name': message.get('name') or str(user_id),
                        'bild': self.contact(user_id)['bild']}
        return [('pause_kodi',), ('screensaver', False), ('ring', True)]

    def _ev_outgoing_state(self, message, now):
        if self.call is None or self.call['ended_at'] is not None:
            return []
        self.call['status'] = 'Klingelt …' if message.get('zustand') == 'klingelt' else 'Wählt …'
        return [('refresh',)] if self.screen == 'call' else []

    def _ev_connected(self, message, now):
        if self.call is None:
            return []
        self.call['since'] = now
        return [('refresh',)]

    def _ev_ended(self, message, now):
        grund = message.get('grund', 'beendet')
        if self.ringing is not None:
            ringing, self.ringing = self.ringing, None
            actions = [('ring', False), ('screensaver', True)]
            if grund == 'verpasst':
                actions.append(('notify', f'Verpasster Anruf: {ringing["name"]}'))
            return actions
        if self.call is None or self.call['ended_at'] is not None:
            return []
        self.call['status'] = GRUND.get(grund, grund)
        self.call['ended_at'] = now
        return [('refresh',), ('screensaver', True)]

    def _ev_play_kodi(self, message, now):
        return [('play_kodi', message['sdp_pfad'])]

    def _ev_stop_kodi(self, message, now):
        return [('stop_kodi',)]

    def _ev_status(self, message, now):
        self.mic_ok = bool(message.get('mikrofon_ok', True))
        if not message.get('telegram_verbunden', True):
            self.banner = 'Keine Verbindung zu Telegram'
        elif not self.mic_ok:
            self.banner = NO_MIC
        else:
            self.banner = ''
        return [('refresh',)]

    def _ev_error(self, message, now):
        return [('notify', message.get('text', 'Fehler'))]

    def _ev__lost(self, message, now):
        actions = []
        if self.ringing is not None:
            self.ringing = None
            actions.append(('ring', False))
        if self.call is not None:
            self.call = None
            actions += self._show(self.previous)
        return actions + [('stop_kodi',), ('screensaver', True), ('notify', 'Anrufteil neu gestartet'),
                          ('restart_worker',)]

    # --- Bedienung ------------------------------------------------------

    def _user_call(self, now, id):
        if self.call is not None or self.ringing is not None:
            return []
        entry = self.contact(id)
        if entry['gruppe']:
            return [('notify', 'Gruppenanrufe folgen in einer späteren Version')]
        if not self.mic_ok:
            return [('notify', NO_MIC)]
        self.call = {'id': id, 'name': entry['name'], 'bild': entry['bild'], 'status': 'Wählt …',
                     'since': None, 'stumm': False, 'ended_at': None}
        return [('pause_kodi',), ('screensaver', False), ('send', 'call', {'id': id})] + self._show('call')

    def _user_accept(self, now):
        if self.ringing is None:
            return []
        if not self.mic_ok:
            return [('notify', NO_MIC)]
        ringing, self.ringing = self.ringing, None
        self.call = {'id': ringing['id'], 'name': ringing['name'], 'bild': ringing['bild'],
                     'status': 'Verbinde …', 'since': None, 'stumm': False, 'ended_at': None}
        return [('ring', False), ('send', 'accept', {})] + self._show('call')

    def _user_decline(self, now):
        if self.ringing is None:
            return []
        self.ringing = None
        return [('ring', False), ('send', 'decline', {}), ('screensaver', True)]

    def _user_hangup(self, now):
        if self.call is None or self.call['ended_at'] is not None:
            return []
        return [('send', 'hangup', {})]

    def _user_mute(self, now):
        if self.call is None or self.call['ended_at'] is not None:
            return []
        self.call['stumm'] = not self.call['stumm']
        return [('send', 'mute', {'an': self.call['stumm']}), ('refresh',)]

    def _user_back(self, now):
        if self.screen == 'call':
            if self.call is not None and self.call['ended_at'] is None:
                return [('send', 'hangup', {})]
            self.call = None
            return self._show(self.previous)
        if self.screen == 'contacts':
            return self._show('home')
        return [('confirm_exit',)]

    def _user_exit(self, now):
        return [('exit',)]

    def _user_open_contacts(self, now):
        return self._show('contacts')

    def _user_fav_add(self, now, id):
        self.favorites.add(id)
        return [('refresh',)]

    def _user_fav_remove(self, now, id):
        self.favorites.remove(id)
        return [('refresh',)]

    def _user_fav_move(self, now, id, step):
        self.favorites.move(id, step)
        return [('refresh',)]

    def _user_login_phone_start(self, now):
        return [('ask', 'nummer')]

    def _user_login_phone(self, now, nummer):
        return [('send', 'login_phone', {'nummer': nummer})]

    def _user_login_code(self, now, code):
        return [('send', 'login_code', {'code': code})]

    def _user_login_password(self, now, passwort):
        return [('send', 'login_password', {'passwort': passwort})]

    def _user_login_cancel(self, now):
        return [('send', 'login_qr', {})]

    # --- intern ---------------------------------------------------------

    def _show(self, screen):
        if screen == self.screen:
            return [('refresh',)]
        if self.screen in ('home', 'contacts'):
            self.previous = self.screen
        self.screen = screen
        return [('show', screen)]
```

- [ ] **Step 4: Tests und ruff grün**

Run: `.venv/bin/pytest -q tests/test_appstate.py && .venv/bin/ruff check .`
Expected: `17 passed`, ruff `All checks passed!`

- [ ] **Step 5: Stand festhalten** – kein Commit; volle Testsuite `.venv/bin/pytest -q` grün.

---

### Task 14: Fenster-Vorlagen, Grafiken und Schriftanpassung

Arctic Zephyr (der Skin auf dem Pi) hat keine Standardschriften wie `font13`; Text mit unbekannter Schrift wäre unsichtbar. Die Fenster-XML enthalten deshalb Platzhalter `$FONT_KLEIN$`, `$FONT_MITTEL$`, `$FONT_GROSS$`, `$FONT_RIESIG$`, die `tgc/skin.py` beim Start durch Schriften des aktiven Skins ersetzt.

**Files:**
- Create: `tools/make_media.py`
- Create: `addon/script.telegram.calls/resources/skins/Default/1080i/tgc-{home,contacts,login,call,ring}.xml`
- Create: `addon/script.telegram.calls/resources/skins/Default/media/tgc-{white,kreis,avatar,alle}.png (erzeugt)`
- Test: `tests/test_skin.py`

**Interfaces:**
- Produces: `tgc.skin.available_fonts(skin_path) -> set`, `tgc.skin.font_roles(names) -> dict`, `tgc.skin.prepare(addon_path, target, roles) -> str` (scriptPath für `WindowXML`). Control-IDs, auf die Task 15 zugreift: Startseite Panel `100`, Hinweisleiste `200`, Leer-Hinweis `201`; Kontakte Liste `100`, Hinweisleiste `200`; Anmeldung QR-Bild `100`, Knopf `200`; Anruf Bild `100`, Name `101`, Status `102`, Stumm `200`, Auflegen `201`; Klingeln Bild `100`, Name `101`, Annehmen `200`, Ablehnen `201`. ListItem-Eigenschaften: `kind` (`contact` | `group` | `all`), `id`; Art `thumb`; `Label2` für Hinweise.

- [ ] **Step 1: Tests schreiben**

`tests/test_skin.py`:

```python
from tgc import skin


def test_schriften_aus_font_xml(tmp_path):
    (tmp_path / '1080i').mkdir()
    (tmp_path / '1080i' / 'Font.xml').write_text(
        '<fonts><fontset id="Default"><font><name>Small</name></font><font><name> Large </name></font>'
        '</fontset></fonts>')
    assert skin.available_fonts(str(tmp_path)) == {'Small', 'Large'}
    assert skin.available_fonts(str(tmp_path / 'fehlt')) == set()


def test_rollen_fuer_estuary_und_arctic_zephyr():
    estuary = skin.font_roles({'font10', 'font12', 'font13', 'font30', 'font45', 'font52'})
    assert estuary == {'KLEIN': 'font12', 'MITTEL': 'font30', 'GROSS': 'font45', 'RIESIG': 'font52'}
    zephyr = skin.font_roles({'Small', 'Medium', 'Large', 'LargeX2', 'Mini'})
    assert zephyr == {'KLEIN': 'Small', 'MITTEL': 'Medium', 'GROSS': 'Large', 'RIESIG': 'LargeX2'}


def test_unbekannter_skin_nimmt_irgendeine_vorhandene_schrift():
    assert set(skin.font_roles({'Zeta', 'Alpha'}).values()) == {'Alpha'}


def test_prepare_ersetzt_platzhalter(tmp_path):
    addon = tmp_path / 'addon'
    xml_dir = addon / 'resources' / 'skins' / 'Default' / '1080i'
    xml_dir.mkdir(parents=True)
    (addon / 'resources' / 'skins' / 'Default' / 'media').mkdir()
    (xml_dir / 'tgc-home.xml').write_text('<font>$FONT_GROSS$</font><font>$FONT_KLEIN$</font>')
    target = skin.prepare(str(addon), str(tmp_path / 'ui'), {'GROSS': 'Large', 'KLEIN': 'Small'})
    out = tmp_path / 'ui' / 'resources' / 'skins' / 'Default' / '1080i' / 'tgc-home.xml'
    assert target == str(tmp_path / 'ui')
    assert out.read_text() == '<font>Large</font><font>Small</font>'
    skin.prepare(str(addon), str(tmp_path / 'ui'), {'GROSS': 'font45', 'KLEIN': 'font12'})
    assert out.read_text() == '<font>font45</font><font>font12</font>'
```

- [ ] **Step 2: Tests laufen lassen, sie müssen scheitern**

Run: `.venv/bin/pytest -q tests/test_skin.py`
Expected: FAIL mit `ImportError: cannot import name 'skin' from 'tgc'`

- [ ] **Step 3: Implementierung schreiben**

`addon/script.telegram.calls/resources/lib/tgc/skin.py`:

```python
"""Fenster-XML an die Schriften des aktiven Skins anpassen.

Skript-Fenster kennen nur die Schriftnamen des aktiven Skins. Ein unbekannter
Name fällt auf "font13" zurück; fehlt auch der (Arctic Zephyr), bleibt der
Text unsichtbar (GUIFontManager::GetFont). Deshalb stehen in den XML-Dateien
Platzhalter $FONT_KLEIN$ usw., die beim Start ersetzt werden.
"""
import os
import re
import shutil

ROLES = {
    'KLEIN': ('font12', 'font13', 'Small', 'font10'),
    'MITTEL': ('font30', 'font27', 'font25_title', 'Medium', 'font13'),
    'GROSS': ('font45', 'font37', 'font36', 'Large', 'font30'),
    'RIESIG': ('font52', 'font60', 'LargeX2', 'Large', 'font45'),
}


def available_fonts(skin_path):
    """Schriftnamen aus den Font.xml-Dateien des Skins (eine Ebene unter dem Skin-Ordner)."""
    names = set()
    try:
        folders = os.listdir(skin_path)
    except OSError:
        return names
    for folder in folders:
        path = os.path.join(skin_path, folder, 'Font.xml')
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                names.update(re.findall(r'<name>\s*([^<\s]+)\s*</name>', f.read()))
        except OSError:
            continue
    return names


def font_roles(names):
    lower = {n.lower(): n for n in names}
    fallback = sorted(names)[0] if names else 'font13'
    roles = {}
    for role, wanted in ROLES.items():
        roles[role] = next((lower[w.lower()] for w in wanted if w.lower() in lower), fallback)
    return roles


def prepare(addon_path, target, roles):
    """Kopiert resources/skins/Default nach target, ersetzt die Platzhalter, gibt target zurück.

    target dient als scriptPath für xbmcgui.WindowXML.
    """
    source = os.path.join(addon_path, 'resources', 'skins', 'Default')
    dest = os.path.join(target, 'resources', 'skins', 'Default')
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(source, dest)
    xml_dir = os.path.join(dest, '1080i')
    for name in os.listdir(xml_dir):
        path = os.path.join(xml_dir, name)
        with open(path, encoding='utf-8') as f:
            text = f.read()
        for role, font in roles.items():
            text = text.replace('$FONT_' + role + '$', font)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
    return target
```

- [ ] **Step 4: Tests und ruff grün**

Run: `.venv/bin/pytest -q tests/test_skin.py && .venv/bin/ruff check .`
Expected: `4 passed`, ruff `All checks passed!`

- [ ] **Step 5: Grafik-Erzeuger und Fenster-XML anlegen**

`tools/make_media.py`:

```python
#!/usr/bin/env python3
"""Erzeugt die PNG-Grafiken des Add-ons (ohne PIL). Aufruf: tools/make_media.py <media-ordner>"""
import math
import os
import struct
import sys
import zlib


def png(size, pixel):
    """pixel(x, y) -> (r, g, b, a); quadratisches Bild."""
    rows = []
    for y in range(size):
        row = bytearray(b'\0')
        for x in range(size):
            row += bytes(pixel(x, y))
        rows.append(bytes(row))

    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF))

    header = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(b''.join(rows)))
            + chunk(b'IEND', b''))


def circle(size, color, plus=None):
    r = size / 2

    def pixel(x, y):
        d = math.hypot(x + 0.5 - r, y + 0.5 - r)
        alpha = max(0.0, min(1.0, r - d))  # weicher Rand
        if plus and (abs(x + 0.5 - r) < size * 0.04 or abs(y + 0.5 - r) < size * 0.04) \
                and abs(x + 0.5 - r) < size * 0.22 and abs(y + 0.5 - r) < size * 0.22:
            return (*plus, int(255 * alpha))
        return (*color, int(255 * alpha))
    return png(size, pixel)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    files = {
        'tgc-white.png': png(8, lambda x, y: (255, 255, 255, 255)),
        'tgc-kreis.png': circle(256, (255, 255, 255)),
        'tgc-avatar.png': circle(256, (84, 110, 122)),
        'tgc-alle.png': circle(256, (38, 50, 56), plus=(255, 255, 255)),
    }
    for name, data in files.items():
        with open(os.path.join(out, name), 'wb') as f:
            f.write(data)
        print(name, len(data), 'Byte')


if __name__ == '__main__':
    main()
```

Run: `.venv/bin/python tools/make_media.py addon/script.telegram.calls/resources/skins/Default/media`
Expected: vier Zeilen `tgc-….png … Byte`.

`addon/script.telegram.calls/resources/skins/Default/1080i/tgc-home.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Startseite: Favoriten als Kacheln, letzte Kachel "Alle Kontakte". Schriften: siehe tgc/skin.py -->
<window>
    <defaultcontrol always="true">100</defaultcontrol>
    <controls>
        <control type="image">
            <left>0</left><top>0</top><width>1920</width><height>1080</height>
            <texture colordiffuse="FF101820">tgc-white.png</texture>
        </control>
        <control type="label">
            <left>90</left><top>50</top><width>1000</width><height>90</height>
            <font>$FONT_GROSS$</font><textcolor>FFFFFFFF</textcolor>
            <label>Telegram-Anrufe</label>
        </control>
        <control type="label" id="200">
            <left>1000</left><top>70</top><width>830</width><height>60</height>
            <align>right</align><font>$FONT_KLEIN$</font><textcolor>FFFFB300</textcolor>
        </control>
        <control type="label" id="201">
            <left>90</left><top>180</top><width>1740</width><height>70</height>
            <font>$FONT_MITTEL$</font><textcolor>FFB0BEC5</textcolor>
            <label>Noch keine Favoriten – unter „Alle Kontakte“ hinzufügen</label>
        </control>
        <control type="panel" id="100">
            <left>90</left><top>270</top><width>1740</width><height>780</height>
            <orientation>vertical</orientation>
            <scrolltime>200</scrolltime>
            <itemlayout width="348" height="390">
                <control type="image">
                    <left>49</left><top>20</top><width>250</width><height>250</height>
                    <aspectratio>scale</aspectratio>
                    <texture diffuse="tgc-kreis.png" fallback="tgc-avatar.png">$INFO[ListItem.Art(thumb)]</texture>
                </control>
                <control type="label">
                    <left>10</left><top>290</top><width>328</width><height>70</height>
                    <align>center</align><font>$FONT_MITTEL$</font><textcolor>FFB0BEC5</textcolor>
                    <label>$INFO[ListItem.Label]</label>
                </control>
            </itemlayout>
            <focusedlayout width="348" height="390">
                <control type="image">
                    <left>37</left><top>8</top><width>274</width><height>274</height>
                    <texture colordiffuse="FF2AABEE">tgc-kreis.png</texture>
                </control>
                <control type="image">
                    <left>49</left><top>20</top><width>250</width><height>250</height>
                    <aspectratio>scale</aspectratio>
                    <texture diffuse="tgc-kreis.png" fallback="tgc-avatar.png">$INFO[ListItem.Art(thumb)]</texture>
                </control>
                <control type="label">
                    <left>10</left><top>290</top><width>328</width><height>70</height>
                    <align>center</align><font>$FONT_MITTEL$</font><textcolor>FFFFFFFF</textcolor>
                    <label>$INFO[ListItem.Label]</label>
                </control>
            </focusedlayout>
        </control>
    </controls>
</window>
```

`addon/script.telegram.calls/resources/skins/Default/1080i/tgc-contacts.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Alle Kontakte: Personen, darunter Gruppen (ausgegraut). Schriften: siehe tgc/skin.py -->
<window>
    <defaultcontrol always="true">100</defaultcontrol>
    <controls>
        <control type="image">
            <left>0</left><top>0</top><width>1920</width><height>1080</height>
            <texture colordiffuse="FF101820">tgc-white.png</texture>
        </control>
        <control type="label">
            <left>90</left><top>50</top><width>1000</width><height>90</height>
            <font>$FONT_GROSS$</font><textcolor>FFFFFFFF</textcolor>
            <label>Alle Kontakte</label>
        </control>
        <control type="label" id="200">
            <left>1000</left><top>70</top><width>830</width><height>60</height>
            <align>right</align><font>$FONT_KLEIN$</font><textcolor>FFFFB300</textcolor>
        </control>
        <control type="list" id="100">
            <left>90</left><top>170</top><width>1740</width><height>880</height>
            <orientation>vertical</orientation>
            <scrolltime>150</scrolltime>
            <itemlayout height="110">
                <control type="image">
                    <left>10</left><top>10</top><width>90</width><height>90</height>
                    <aspectratio>scale</aspectratio>
                    <texture diffuse="tgc-kreis.png" fallback="tgc-avatar.png">$INFO[ListItem.Art(thumb)]</texture>
                </control>
                <control type="label">
                    <left>130</left><top>0</top><width>1000</width><height>110</height>
                    <aligny>center</aligny><font>$FONT_MITTEL$</font><textcolor>FFB0BEC5</textcolor>
                    <label>$INFO[ListItem.Label]</label>
                </control>
                <control type="label">
                    <left>1140</left><top>0</top><width>580</width><height>110</height>
                    <align>right</align><aligny>center</aligny><font>$FONT_KLEIN$</font><textcolor>FF78909C</textcolor>
                    <label>$INFO[ListItem.Label2]</label>
                </control>
            </itemlayout>
            <focusedlayout height="110">
                <control type="image">
                    <left>0</left><top>0</top><width>1740</width><height>110</height>
                    <texture colordiffuse="FF2AABEE">tgc-white.png</texture>
                </control>
                <control type="image">
                    <left>10</left><top>10</top><width>90</width><height>90</height>
                    <aspectratio>scale</aspectratio>
                    <texture diffuse="tgc-kreis.png" fallback="tgc-avatar.png">$INFO[ListItem.Art(thumb)]</texture>
                </control>
                <control type="label">
                    <left>130</left><top>0</top><width>1000</width><height>110</height>
                    <aligny>center</aligny><font>$FONT_MITTEL$</font><textcolor>FFFFFFFF</textcolor>
                    <label>$INFO[ListItem.Label]</label>
                </control>
                <control type="label">
                    <left>1140</left><top>0</top><width>580</width><height>110</height>
                    <align>right</align><aligny>center</aligny><font>$FONT_KLEIN$</font><textcolor>FFFFFFFF</textcolor>
                    <label>$INFO[ListItem.Label2]</label>
                </control>
            </focusedlayout>
        </control>
    </controls>
</window>
```

`addon/script.telegram.calls/resources/skins/Default/1080i/tgc-login.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Anmeldung: QR-Code, alternativ Telefonnummer. Schriften: siehe tgc/skin.py -->
<window>
    <defaultcontrol always="true">200</defaultcontrol>
    <controls>
        <control type="image">
            <left>0</left><top>0</top><width>1920</width><height>1080</height>
            <texture colordiffuse="FF101820">tgc-white.png</texture>
        </control>
        <control type="label">
            <left>90</left><top>50</top><width>1740</width><height>90</height>
            <font>$FONT_GROSS$</font><textcolor>FFFFFFFF</textcolor>
            <label>Bei Telegram anmelden</label>
        </control>
        <control type="image">
            <left>90</left><top>200</top><width>640</width><height>640</height>
            <texture colordiffuse="FFFFFFFF">tgc-white.png</texture>
        </control>
        <control type="image" id="100">
            <left>110</left><top>220</top><width>600</width><height>600</height>
            <aspectratio>keep</aspectratio>
        </control>
        <control type="label">
            <left>820</left><top>220</top><width>1010</width><height>500</height>
            <wrapmultiline>true</wrapmultiline><font>$FONT_MITTEL$</font><textcolor>FFECEFF1</textcolor>
            <label>Öffne Telegram auf dem Handy:[CR]Einstellungen → Geräte → Gerät verbinden[CR][CR]und scanne den Code. Er erneuert sich von selbst.</label>
        </control>
        <control type="button" id="200">
            <left>820</left><top>740</top><width>800</width><height>100</height>
            <font>$FONT_MITTEL$</font><align>center</align><aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor><focusedcolor>FFFFFFFF</focusedcolor>
            <texturefocus colordiffuse="FF2AABEE">tgc-white.png</texturefocus>
            <texturenofocus colordiffuse="FF263238">tgc-white.png</texturenofocus>
            <label>Mit Telefonnummer anmelden</label>
        </control>
    </controls>
</window>
```

`addon/script.telegram.calls/resources/skins/Default/1080i/tgc-call.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Anrufbildschirm: Bild, Name, Status, Stumm, Auflegen. Schriften: siehe tgc/skin.py -->
<window>
    <defaultcontrol always="true">201</defaultcontrol>
    <controls>
        <control type="image">
            <left>0</left><top>0</top><width>1920</width><height>1080</height>
            <texture colordiffuse="FF101820">tgc-white.png</texture>
        </control>
        <control type="image" id="100">
            <left>760</left><top>120</top><width>400</width><height>400</height>
            <aspectratio>scale</aspectratio>
            <texture diffuse="tgc-kreis.png">tgc-avatar.png</texture>
        </control>
        <control type="label" id="101">
            <left>160</left><top>560</top><width>1600</width><height>110</height>
            <align>center</align><font>$FONT_RIESIG$</font><textcolor>FFFFFFFF</textcolor>
        </control>
        <control type="label" id="102">
            <left>160</left><top>680</top><width>1600</width><height>80</height>
            <align>center</align><font>$FONT_MITTEL$</font><textcolor>FFB0BEC5</textcolor>
        </control>
        <control type="button" id="200">
            <left>560</left><top>840</top><width>380</width><height>110</height>
            <onright>201</onright>
            <font>$FONT_MITTEL$</font><align>center</align><aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor><focusedcolor>FFFFFFFF</focusedcolor>
            <texturefocus colordiffuse="FF2AABEE">tgc-white.png</texturefocus>
            <texturenofocus colordiffuse="FF263238">tgc-white.png</texturenofocus>
            <label>Stumm</label>
        </control>
        <control type="button" id="201">
            <left>980</left><top>840</top><width>380</width><height>110</height>
            <onleft>200</onleft>
            <font>$FONT_MITTEL$</font><align>center</align><aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor><focusedcolor>FFFFFFFF</focusedcolor>
            <texturefocus colordiffuse="FFE53935">tgc-white.png</texturefocus>
            <texturenofocus colordiffuse="FF5D2A2A">tgc-white.png</texturenofocus>
            <label>Auflegen</label>
        </control>
    </controls>
</window>
```

`addon/script.telegram.calls/resources/skins/Default/1080i/tgc-ring.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Klingeldialog über allen Fenstern des Add-ons. Schriften: siehe tgc/skin.py -->
<window>
    <defaultcontrol always="true">200</defaultcontrol>
    <controls>
        <control type="image">
            <left>0</left><top>0</top><width>1920</width><height>1080</height>
            <texture colordiffuse="E6101820">tgc-white.png</texture>
        </control>
        <control type="image" id="100">
            <left>760</left><top>140</top><width>400</width><height>400</height>
            <aspectratio>scale</aspectratio>
            <texture diffuse="tgc-kreis.png">tgc-avatar.png</texture>
        </control>
        <control type="label" id="101">
            <left>160</left><top>580</top><width>1600</width><height>110</height>
            <align>center</align><font>$FONT_RIESIG$</font><textcolor>FFFFFFFF</textcolor>
        </control>
        <control type="label">
            <left>160</left><top>700</top><width>1600</width><height>80</height>
            <align>center</align><font>$FONT_MITTEL$</font><textcolor>FFB0BEC5</textcolor>
            <label>ruft an</label>
        </control>
        <control type="button" id="200">
            <left>560</left><top>840</top><width>380</width><height>110</height>
            <onright>201</onright>
            <font>$FONT_MITTEL$</font><align>center</align><aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor><focusedcolor>FFFFFFFF</focusedcolor>
            <texturefocus colordiffuse="FF43A047">tgc-white.png</texturefocus>
            <texturenofocus colordiffuse="FF1E3A20">tgc-white.png</texturenofocus>
            <label>Annehmen</label>
        </control>
        <control type="button" id="201">
            <left>980</left><top>840</top><width>380</width><height>110</height>
            <onleft>200</onleft>
            <font>$FONT_MITTEL$</font><align>center</align><aligny>center</aligny>
            <textcolor>FFFFFFFF</textcolor><focusedcolor>FFFFFFFF</focusedcolor>
            <texturefocus colordiffuse="FFE53935">tgc-white.png</texturefocus>
            <texturenofocus colordiffuse="FF5D2A2A">tgc-white.png</texturenofocus>
            <label>Ablehnen</label>
        </control>
    </controls>
</window>
```

Run: `for f in addon/script.telegram.calls/resources/skins/Default/1080i/*.xml; do python3 -c "import sys, xml.etree.ElementTree as E; E.parse(sys.argv[1])" "$f" && echo "ok $f"; done`
Expected: fünfmal `ok`.

- [ ] **Step 6: Stand festhalten** – kein Commit; volle Testsuite `.venv/bin/pytest -q` grün.

---

### Task 15: Kodi-Oberfläche und Add-on-Rahmen

`kodi_ui.py` ist das einzige Modul mit `xbmc`-Import. Ein Rauchtest mit Kodi-Attrappen (`tests/kodistubs/`) prüft Import und Ausführung der Aktionen; das Verhalten in Kodi selbst prüft Task 16. Standardwerte der Einstellungen `direkte_ausgabe` und `echo` aus der Entscheidung in `docs/messtest-teilprojekt-2.md` übernehmen (unten: `false` und `webrtc`).

**Files:**
- Create: `addon/script.telegram.calls/{default.py,addon.xml}`
- Create: `addon/script.telegram.calls/resources/settings.xml`
- Create: `addon/script.telegram.calls/resources/language/resource.language.{de_de,en_gb}/strings.po`
- Test: `tests/kodistubs/xbmc.py`
- Test: `tests/kodistubs/xbmcaddon.py`
- Test: `tests/kodistubs/xbmcgui.py`
- Test: `tests/kodistubs/xbmcvfs.py`
- Test: `tests/test_kodi_ui.py`

**Interfaces:**
- Consumes: `AppState` (Task 13), `Favorites` (Task 4), `WorkerClient`/`WorkerError` (Task 11), `skin` (Task 14), Control-IDs aus Task 14, Exit-Code 3 aus Task 10.
- Produces: `tgc.kodi_ui.main()`, `tgc.kodi_ui.logout()`, `Controller`, `Ui`, `worker_command()`, `worker_env()`, `worker_init()`; Einstellungen `api_id`, `api_hash`, `abmelden`, `direkte_ausgabe`, `echo` (`webrtc|daempfen|aus`), `mikrofon`.

- [ ] **Step 1: Tests schreiben**

`tests/kodistubs/xbmc.py`:

```python
"""Minimale Attrappe von Kodis Modul xbmc, nur damit kodi_ui in Tests importierbar ist."""
LOGINFO, LOGERROR = 1, 3
builtins = []
rpc_results = {}


def log(message, level=LOGINFO):
    pass


def executebuiltin(command, wait=False):
    builtins.append(command)


def executeJSONRPC(request):
    import json
    method = json.loads(request)['method']
    return json.dumps({'result': rpc_results.get(method)})


class Player:
    def __init__(self):
        self.played = []

    def play(self, path, item):
        self.played.append(path)

    def isPlaying(self):
        return bool(self.played)

    def getPlayingFile(self):
        return self.played[-1]

    def stop(self):
        self.played.clear()


class Monitor:
    def abortRequested(self):
        return False
```

`tests/kodistubs/xbmcaddon.py`:

```python
class Addon:
    def getAddonInfo(self, key):
        return {'id': 'script.telegram.calls', 'path': '/addon', 'profile': '/profile/'}[key]

    def getSettingInt(self, key):
        return 0

    def getSettingString(self, key):
        return ''

    def getSettingBool(self, key):
        return False
```

`tests/kodistubs/xbmcgui.py`:

```python
INPUT_ALPHANUM, INPUT_NUMERIC, ALPHANUM_HIDE_INPUT, NOTIFICATION_INFO = 0, 1, 2, 'info'


class ListItem:
    def __init__(self, label='', label2='', path=''):
        self.label, self.label2, self.path, self.props, self.art = label, label2, path, {}, {}

    def setArt(self, art):
        self.art = art

    def setProperty(self, key, value):
        self.props[key] = value

    def getProperty(self, key):
        return self.props.get(key, '')

    def getMusicInfoTag(self):
        return type('Tag', (), {'setTitle': lambda self, t: None})()


class WindowXML:
    def __init__(self, *args, **kwargs):
        pass


class WindowXMLDialog(WindowXML):
    pass


class Dialog:
    pass
```

`tests/kodistubs/xbmcvfs.py`:

```python
def translatePath(path):
    return path
```

`tests/test_kodi_ui.py`:

```python
"""Rauchtest: kodi_ui lässt sich mit Kodi-Attrappen importieren, die Aktionen werden ausgeführt."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'kodistubs'))

import xbmc  # noqa: E402

from tgc import kodi_ui  # noqa: E402


class FakeWorker:
    def __init__(self):
        self.sent = []

    def send(self, typ, **data):
        self.sent.append((typ, data))


def controller():
    c = kodi_ui.Controller.__new__(kodi_ui.Controller)
    c.player = xbmc.Player()
    c.sdp_path = None
    c.worker = FakeWorker()
    c.running = True
    return c


def test_senden_und_beenden():
    c = controller()
    c.execute(('send', 'call', {'id': 3}))
    c.execute(('exit',))
    assert c.worker.sent == [('call', {'id': 3})] and c.running is False


def test_sdp_abspielen_und_nur_eigenen_stream_stoppen():
    c = controller()
    c.execute(('play_kodi', '/p/anruf.sdp'))
    assert c.player.played == ['/p/anruf.sdp']
    c.player.played.append('/film.mkv')
    c.execute(('stop_kodi',))
    assert c.player.played == ['/p/anruf.sdp', '/film.mkv']


def test_bildschirmschoner():
    c = controller()
    c.execute(('screensaver', False))
    c.execute(('screensaver', True))
    assert xbmc.builtins[-2:] == ['InhibitScreensaver(true)', 'InhibitScreensaver(false)']


def test_worker_umgebung_ohne_pythonhome(monkeypatch):
    monkeypatch.setenv('PYTHONHOME', '/kodi')
    env = kodi_ui.worker_env()
    assert 'PYTHONHOME' not in env
    assert env['PYTHONPATH'].split(os.pathsep) == ['/addon/vendor', '/addon/resources/lib']
    assert kodi_ui.worker_command()[1:] == ['/addon/worker/main.py', '--data', '/profile/']
```

- [ ] **Step 2: Tests laufen lassen, sie müssen scheitern**

Run: `.venv/bin/pytest -q tests/test_kodi_ui.py`
Expected: FAIL mit `ImportError: cannot import name 'kodi_ui' from 'tgc'`

- [ ] **Step 3: Implementierung schreiben**

`addon/script.telegram.calls/resources/lib/tgc/kodi_ui.py`:

```python
"""Kodi-Seite des Add-ons: Fenster, Ausführung der Aktionen aus AppState, Anrufprozess.

Alle Entscheidungen trifft AppState (ohne Kodi testbar). Dieses Modul zeigt
nur an, nimmt Tasten entgegen und führt Aktionen aus. Fenster-Callbacks und
der Lesethread des Anrufprozesses legen ihre Eingänge in eine Warteschlange;
abgearbeitet wird sie nur im Hauptthread (Controller.run).
"""
import json
import os
import queue
import shutil
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from tgc import skin
from tgc.appstate import AppState
from tgc.favorites import Favorites
from tgc.workerclient import WorkerClient, WorkerError

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_PATH = ADDON.getAddonInfo('path')
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
TITLE = 'Telegram-Anrufe'
EXIT_LOCKED = 3  # worker/main.py

ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
ACTION_STOP = 13
ACTION_CONTEXT_MENU = 117
RESTARTS_PER_MINUTE = 3


def log(message, level=xbmc.LOGINFO):
    xbmc.log(f'{ADDON_ID}: {message}', level)


def rpc(method, **params):
    request = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}
    return json.loads(xbmc.executeJSONRPC(json.dumps(request))).get('result')


def avatar(path):
    return path or 'tgc-avatar.png'


def contact_item(entry, kind, label2=''):
    item = xbmcgui.ListItem(entry['name'], label2)
    item.setArt({'thumb': avatar(entry['bild'])})
    item.setProperty('kind', kind)
    item.setProperty('id', str(entry['id']))
    return item


# --- Fenster ----------------------------------------------------------------

class _Screen(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        self.push = kwargs['push']
        self.state = kwargs['state']
        self.ready = False

    def onInit(self):
        self.ready = True
        self.render()

    def render(self):
        pass

    def user(self, action, **data):
        self.push(('user', action, data))

    def onAction(self, action):
        code = action.getId()
        if code in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.user('back')
        elif code == ACTION_STOP:
            self.user('hangup')
        elif code == ACTION_CONTEXT_MENU:
            self.context()

    def context(self):
        pass

    def selected(self):
        item = self.getControl(100).getSelectedItem()
        if item is None or item.getProperty('kind') == 'all':
            return item, None
        return item, int(item.getProperty('id'))

    def fill(self, items):
        control = self.getControl(100)
        position = control.getSelectedPosition()
        control.reset()
        control.addItems(items)
        if 0 <= position < len(items):
            control.selectItem(position)


class LoginScreen(_Screen):
    def render(self):
        if self.ready and self.state.qr:
            self.getControl(100).setImage(self.state.qr, False)

    def onClick(self, control_id):
        if control_id == 200:
            self.user('login_phone_start')


class HomeScreen(_Screen):
    def render(self):
        if not self.ready:
            return
        favorites = self.state.home_items()
        items = [contact_item(c, 'contact') for c in favorites]
        everyone = xbmcgui.ListItem('Alle Kontakte')
        everyone.setArt({'thumb': 'tgc-alle.png'})
        everyone.setProperty('kind', 'all')
        self.fill(items + [everyone])
        self.getControl(200).setLabel(self.state.banner)
        self.getControl(201).setVisible(not favorites)

    def onClick(self, control_id):
        if control_id != 100:
            return
        item, user_id = self.selected()
        if item is None:
            return
        if user_id is None:
            self.user('open_contacts')
        else:
            self.user('call', id=user_id)

    def context(self):
        item, user_id = self.selected()
        if user_id is None:
            return
        choice = xbmcgui.Dialog().contextmenu(['Aus Favoriten entfernen', 'Nach vorne', 'Nach hinten'])
        if choice == 0:
            self.user('fav_remove', id=user_id)
        elif choice in (1, 2):
            self.user('fav_move', id=user_id, step=-1 if choice == 1 else 1)


class ContactsScreen(_Screen):
    def render(self):
        if not self.ready:
            return
        items = []
        for entry in self.state.contacts:
            if entry['gruppe']:
                label2 = 'Gruppenanrufe folgen'
            elif self.state.is_favorite(entry['id']):
                label2 = 'Favorit'
            else:
                label2 = ''
            items.append(contact_item(entry, 'group' if entry['gruppe'] else 'contact', label2))
        self.fill(items)
        self.getControl(200).setLabel(self.state.banner)

    def onClick(self, control_id):
        if control_id == 100:
            item, user_id = self.selected()
            if user_id is not None:
                self.user('call', id=user_id)

    def context(self):
        item, user_id = self.selected()
        entries = ['Suchen …']
        favorite = None
        if user_id is not None and item.getProperty('kind') == 'contact':
            favorite = self.state.is_favorite(user_id)
            entries.append('Aus Favoriten entfernen' if favorite else 'Zu Favoriten hinzufügen')
        choice = xbmcgui.Dialog().contextmenu(entries)
        if choice == 0:
            self.search()
        elif choice == 1:
            self.user('fav_remove' if favorite else 'fav_add', id=user_id)

    def search(self):
        text = xbmcgui.Dialog().input('Kontakt suchen', type=xbmcgui.INPUT_ALPHANUM)
        index = self.state.find_contact(text) if text else None
        if index is None:
            if text:
                xbmcgui.Dialog().notification(TITLE, f'Kein Kontakt „{text}“', xbmcgui.NOTIFICATION_INFO, 3000)
            return
        self.getControl(100).selectItem(index)
        self.setFocusId(100)


class CallScreen(_Screen):
    def render(self):
        call = self.state.call
        if not self.ready or call is None:
            return
        self.getControl(100).setImage(avatar(call['bild']), False)
        self.getControl(101).setLabel(call['name'])
        self.getControl(200).setLabel('Ton an' if call['stumm'] else 'Stumm')
        self.render_status()

    def render_status(self):
        if self.ready:
            self.getControl(102).setLabel(self.state.call_status(time.monotonic()))

    def onClick(self, control_id):
        if control_id == 200:
            self.user('mute')
        elif control_id == 201:
            self.user('hangup')


class RingDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.push = kwargs['push']
        self.state = kwargs['state']

    def onInit(self):
        ringing = self.state.ringing
        if ringing is not None:
            self.getControl(100).setImage(avatar(ringing['bild']), False)
            self.getControl(101).setLabel(ringing['name'])

    def onClick(self, control_id):
        self.push(('user', 'accept' if control_id == 200 else 'decline', {}))

    def onAction(self, action):
        if action.getId() in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK, ACTION_STOP):
            self.push(('user', 'decline', {}))


class Ui:
    FILES = {'login': ('tgc-login.xml', LoginScreen), 'home': ('tgc-home.xml', HomeScreen),
             'contacts': ('tgc-contacts.xml', ContactsScreen), 'call': ('tgc-call.xml', CallScreen)}

    def __init__(self, push, state, root):
        self._push = push
        self._state = state
        self._root = root
        self._screens = {}
        self._current = None
        self._ring = None

    def _screen(self, name):
        if name not in self._screens:
            xml, cls = self.FILES[name]
            self._screens[name] = cls(xml, self._root, 'Default', '1080i', push=self._push, state=self._state)
        return self._screens[name]

    def show(self, name):
        screen = self._screen(name)
        if screen is self._current:
            screen.render()
            return
        old, self._current = self._current, screen
        screen.ready = False
        screen.show()  # erst das neue Fenster, dann das alte schließen: kein Aufblitzen von Kodi
        if old is not None:
            old.close()

    def refresh(self):
        if self._current is not None:
            self._current.render()

    def refresh_call(self):
        if isinstance(self._current, CallScreen):
            self._current.render_status()

    def ring(self, on):
        if on and self._ring is None:
            self._ring = RingDialog('tgc-ring.xml', self._root, 'Default', '1080i',
                                    push=self._push, state=self._state)
            self._ring.show()
        elif not on and self._ring is not None:
            self._ring.close()
            self._ring = None

    def close_all(self):
        self.ring(False)
        for screen in self._screens.values():
            screen.close()
        self._screens.clear()
        self._current = None


# --- Steuerung --------------------------------------------------------------

def worker_command():
    python = shutil.which('python3') or '/usr/bin/python3'
    return [python, os.path.join(ADDON_PATH, 'worker', 'main.py'), '--data', PROFILE]


def worker_env():
    env = dict(os.environ)
    env.pop('PYTHONHOME', None)  # Kodis eingebettetes Python darf den Prozess nicht beeinflussen
    env['PYTHONPATH'] = os.pathsep.join([os.path.join(ADDON_PATH, 'vendor'),
                                         os.path.join(ADDON_PATH, 'resources', 'lib')])
    env['PYTHONNOUSERSITE'] = '1'
    return env


def worker_init():
    return {
        'api_id': ADDON.getSettingInt('api_id'),
        'api_hash': ADDON.getSettingString('api_hash'),
        'direkt': ADDON.getSettingBool('direkte_ausgabe'),
        'echo': ADDON.getSettingString('echo') or 'webrtc',
        'mikrofon': ADDON.getSettingString('mikrofon'),
    }


def make_worker(on_event):
    return WorkerClient(worker_command(), worker_init(), os.path.join(PROFILE, 'worker.sock'), on_event,
                        env=worker_env(), log_path=os.path.join(PROFILE, 'worker.log'))


class Controller:
    def __init__(self):
        self.events = queue.Queue()
        self.state = AppState(Favorites(os.path.join(PROFILE, 'favoriten.json')))
        roles = skin.font_roles(skin.available_fonts(xbmcvfs.translatePath('special://skin/')))
        root = skin.prepare(ADDON_PATH, os.path.join(PROFILE, 'ui'), roles)
        self.ui = Ui(self.events.put, self.state, root)
        self.player = xbmc.Player()
        self.sdp_path = None
        self.worker = None
        self.restarts = []
        self.running = True

    def start_worker(self):
        self.worker = make_worker(lambda message: self.events.put(('event', message)))
        try:
            self.worker.start()
        except WorkerError as e:
            log(f'Anrufprozess startet nicht: {e}', xbmc.LOGERROR)
            xbmcgui.Dialog().ok(TITLE, f'Der Anrufteil startet nicht ({e}).[CR]Details: {PROFILE}worker.log')
            return False
        return True

    def run(self):
        monitor = xbmc.Monitor()
        for action in self.state.start():
            self.execute(action)
        while self.running and not monitor.abortRequested():
            try:
                item = self.events.get(timeout=0.2)
            except queue.Empty:
                item = None
            now = time.monotonic()
            if item is None:
                actions = self.state.tick(now)
            elif item[0] == 'event':
                actions = self.state.on_event(item[1], now)
            else:
                actions = self.state.on_user(item[1], now, **item[2])
            for action in actions:
                self.execute(action)

    def execute(self, action):
        kind, args = action[0], action[1:]
        if kind == 'send':
            self.worker.send(args[0], **args[1])
        elif kind == 'show':
            self.ui.show(args[0])
        elif kind == 'refresh':
            self.ui.refresh()
        elif kind == 'refresh_call':
            self.ui.refresh_call()
        elif kind == 'ring':
            self.ui.ring(args[0])
        elif kind == 'play_kodi':
            self.play_kodi(args[0])
        elif kind == 'stop_kodi':
            self.stop_kodi()
        elif kind == 'pause_kodi':
            self.pause_other_playback()
        elif kind == 'screensaver':
            self.screensaver(args[0])
        elif kind == 'notify':
            xbmcgui.Dialog().notification(TITLE, args[0], xbmcgui.NOTIFICATION_INFO, 4000)
        elif kind == 'ask':
            self.ask(args[0])
        elif kind == 'confirm_exit':
            if xbmcgui.Dialog().yesno(TITLE, 'Telegram-Anrufe schließen? Du bist dann nicht mehr erreichbar.'):
                self.running = False
        elif kind == 'exit':
            self.running = False
        elif kind == 'restart_worker':
            self.restart_worker()

    def play_kodi(self, path):
        self.sdp_path = path
        item = xbmcgui.ListItem(path=path)  # ohne inputstream: ffmpegs Whitelist lehnt sonst rtp ab
        item.getMusicInfoTag().setTitle('Telegram-Anruf')
        self.player.play(path, item)

    def stop_kodi(self):
        try:
            if self.sdp_path and self.player.isPlaying() and self.player.getPlayingFile() == self.sdp_path:
                self.player.stop()
        except RuntimeError:
            pass

    def pause_other_playback(self):
        for player in rpc('Player.GetActivePlayers') or []:
            item = (rpc('Player.GetItem', playerid=player['playerid'], properties=['file']) or {}).get('item', {})
            if item.get('file') != self.sdp_path:
                rpc('Player.PlayPause', playerid=player['playerid'], play=False)

    def screensaver(self, allowed):
        if allowed:
            xbmc.executebuiltin('InhibitScreensaver(false)')
        else:
            xbmc.executebuiltin('InhibitScreensaver(true)')
            rpc('Input.ExecuteAction', action='noop')  # weckt einen laufenden Bildschirmschoner

    def ask(self, what):
        dialog = xbmcgui.Dialog()
        if what == 'nummer':
            value = dialog.input('Telefonnummer mit Ländervorwahl, z. B. +4917…', type=xbmcgui.INPUT_ALPHANUM)
            action, key = 'login_phone', 'nummer'
        elif what == 'code':
            value = dialog.input('Code aus der Telegram-App', type=xbmcgui.INPUT_NUMERIC)
            action, key = 'login_code', 'code'
        else:
            value = dialog.input('Zwei-Faktor-Passwort', type=xbmcgui.INPUT_ALPHANUM,
                                 option=xbmcgui.ALPHANUM_HIDE_INPUT)
            action, key = 'login_password', 'passwort'
        if value:
            self.events.put(('user', action, {key: value}))
        else:
            self.events.put(('user', 'login_cancel', {}))

    def restart_worker(self):
        now = time.monotonic()
        self.restarts = [t for t in self.restarts if now - t < 60] + [now]
        self.worker.stop()
        if len(self.restarts) > RESTARTS_PER_MINUTE:
            xbmcgui.Dialog().ok(TITLE, f'Der Anrufteil stürzt wiederholt ab.[CR]Details: {PROFILE}worker.log')
            self.running = False
            return
        if not self.start_worker():
            self.running = False

    def shutdown(self):
        if self.worker is not None:
            self.worker.stop()  # der Anrufprozess legt einen laufenden Anruf vorher auf
        self.stop_kodi()
        self.screensaver(True)
        self.ui.close_all()


def credentials_missing():
    return not ADDON.getSettingInt('api_id') or not ADDON.getSettingString('api_hash')


def main():
    os.makedirs(PROFILE, mode=0o700, exist_ok=True)
    if credentials_missing():
        xbmcgui.Dialog().ok(TITLE, 'Bitte zuerst api_id und api_hash von my.telegram.org in den '
                                   'Einstellungen eintragen.')
        ADDON.openSettings()
        return
    controller = Controller()
    try:
        if controller.start_worker():
            controller.run()
    finally:
        controller.shutdown()


def logout():
    """Aus den Einstellungen: Session bei Telegram abmelden und löschen."""
    if credentials_missing():
        return
    if not xbmcgui.Dialog().yesno(TITLE, 'Dieses Gerät bei Telegram abmelden?'):
        return
    events = queue.Queue()
    worker = make_worker(events.put)
    try:
        worker.start()
    except WorkerError as e:
        if worker.returncode() == EXIT_LOCKED or f'Code {EXIT_LOCKED}' in str(e):
            xbmcgui.Dialog().ok(TITLE, 'Bitte zuerst Telegram-Anrufe schließen.')
        else:
            xbmcgui.Dialog().ok(TITLE, f'Abmelden fehlgeschlagen ({e}).')
        return
    try:
        deadline = time.monotonic() + 20
        sent = False
        while time.monotonic() < deadline:
            try:
                message = events.get(timeout=0.5)
            except queue.Empty:
                continue
            if message['typ'] == 'ready' and message.get('angemeldet') and not sent:
                worker.send('logout')
                sent = True
            elif message['typ'] == 'ready' and not message.get('angemeldet'):
                xbmcgui.Dialog().notification(TITLE, 'Abgemeldet', xbmcgui.NOTIFICATION_INFO, 4000)
                return
    finally:
        worker.stop()
```

- [ ] **Step 4: Tests und ruff grün**

Run: `.venv/bin/pytest -q tests/test_kodi_ui.py && .venv/bin/ruff check .`
Expected: `4 passed`, ruff `All checks passed!`

- [ ] **Step 5: Einstieg und Add-on-Rahmen anlegen**

`addon/script.telegram.calls/default.py`:

```python
"""Einstieg des Add-ons: Oberfläche, oder mit Argument "logout" Abmelden (aus den Einstellungen)."""
import os
import sys

import xbmcaddon

sys.path.insert(0, os.path.join(xbmcaddon.Addon().getAddonInfo('path'), 'resources', 'lib'))

from tgc import kodi_ui  # noqa: E402

if len(sys.argv) > 1 and sys.argv[1] == 'logout':
    kodi_ui.logout()
else:
    kodi_ui.main()
```

`addon/script.telegram.calls/addon.xml`:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="script.telegram.calls" name="Telegram-Anrufe" version="0.1.0" provider-name="willheisenberg">
    <requires>
        <import addon="xbmc.python" version="3.0.1"/>
    </requires>
    <extension point="xbmc.python.script" library="default.py">
        <provides>executable</provides>
    </extension>
    <extension point="xbmc.addon.metadata">
        <summary lang="de_DE">Telegram-Sprachanrufe am Fernseher</summary>
        <summary lang="en_GB">Telegram voice calls on the TV</summary>
        <description lang="de_DE">Anrufen und angerufen werden mit dem eigenen Telegram-Account, solange das Add-on geöffnet ist. Bedienung mit der Fernbedienung.</description>
        <description lang="en_GB">Make and receive Telegram calls with your own account while the add-on is open. Operated with the remote.</description>
        <platform>linux</platform>
    </extension>
</addon>
```

`addon/script.telegram.calls/resources/settings.xml`:

```xml
<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<settings version="1">
    <section id="script.telegram.calls">
        <category id="telegram" label="30000">
            <group id="1">
                <setting id="api_id" type="integer" label="30001">
                    <level>0</level>
                    <default>0</default>
                    <control type="edit" format="integer">
                        <heading>30001</heading>
                    </control>
                </setting>
                <setting id="api_hash" type="string" label="30002">
                    <level>0</level>
                    <default/>
                    <constraints>
                        <allowempty>true</allowempty>
                    </constraints>
                    <control type="edit" format="string">
                        <heading>30002</heading>
                        <hidden>true</hidden>
                    </control>
                </setting>
                <setting id="abmelden" type="action" label="30003">
                    <level>0</level>
                    <data>RunScript(script.telegram.calls,logout)</data>
                    <constraints>
                        <allowempty>true</allowempty>
                    </constraints>
                    <control type="button" format="action">
                        <close>true</close>
                    </control>
                </setting>
            </group>
        </category>
        <category id="ton" label="30010">
            <group id="1">
                <setting id="direkte_ausgabe" type="boolean" label="30011" help="30017">
                    <level>0</level>
                    <default>false</default>
                    <control type="toggle"/>
                </setting>
                <setting id="echo" type="string" label="30012">
                    <level>0</level>
                    <default>webrtc</default>
                    <constraints>
                        <options>
                            <option label="30013">webrtc</option>
                            <option label="30014">daempfen</option>
                            <option label="30015">aus</option>
                        </options>
                    </constraints>
                    <control type="spinner" format="string"/>
                </setting>
                <setting id="mikrofon" type="string" label="30016">
                    <level>2</level>
                    <default>plughw:CARD=Webcam,DEV=0</default>
                    <control type="edit" format="string">
                        <heading>30016</heading>
                    </control>
                </setting>
            </group>
        </category>
    </section>
</settings>
```

`addon/script.telegram.calls/resources/language/resource.language.de_de/strings.po`:

```po
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\n"
"Language: de_DE\n"

msgctxt "#30000"
msgid "Telegram"
msgstr "Telegram"

msgctxt "#30001"
msgid "api_id (my.telegram.org)"
msgstr "api_id (my.telegram.org)"

msgctxt "#30002"
msgid "api_hash (my.telegram.org)"
msgstr "api_hash (my.telegram.org)"

msgctxt "#30003"
msgid "Log out this device"
msgstr "Dieses Gerät abmelden"

msgctxt "#30010"
msgid "Audio"
msgstr "Ton"

msgctxt "#30011"
msgid "Direct output when HDMI is free"
msgstr "Direkte Ausgabe, wenn HDMI frei ist"

msgctxt "#30012"
msgid "Echo handling"
msgstr "Echo-Verfahren"

msgctxt "#30013"
msgid "WebRTC echo cancellation"
msgstr "WebRTC-Echounterdrückung"

msgctxt "#30014"
msgid "Duck microphone"
msgstr "Mikrofon dämpfen"

msgctxt "#30015"
msgid "Off"
msgstr "Aus"

msgctxt "#30016"
msgid "Microphone (ALSA device)"
msgstr "Mikrofon (ALSA-Gerät)"

msgctxt "#30017"
msgid "Shorter delay. Kodi's own volume control does not apply then."
msgstr "Kürzere Verzögerung. Kodis Lautstärkeregler wirkt dann nicht."
```

`addon/script.telegram.calls/resources/language/resource.language.en_gb/strings.po`:

```po
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\n"
"Language: en_GB\n"

msgctxt "#30000"
msgid "Telegram"
msgstr ""

msgctxt "#30001"
msgid "api_id (my.telegram.org)"
msgstr ""

msgctxt "#30002"
msgid "api_hash (my.telegram.org)"
msgstr ""

msgctxt "#30003"
msgid "Log out this device"
msgstr ""

msgctxt "#30010"
msgid "Audio"
msgstr ""

msgctxt "#30011"
msgid "Direct output when HDMI is free"
msgstr ""

msgctxt "#30012"
msgid "Echo handling"
msgstr ""

msgctxt "#30013"
msgid "WebRTC echo cancellation"
msgstr ""

msgctxt "#30014"
msgid "Duck microphone"
msgstr ""

msgctxt "#30015"
msgid "Off"
msgstr ""

msgctxt "#30016"
msgid "Microphone (ALSA device)"
msgstr ""

msgctxt "#30017"
msgid "Shorter delay. Kodi's own volume control does not apply then."
msgstr ""
```

Run: `for f in addon/script.telegram.calls/addon.xml addon/script.telegram.calls/resources/settings.xml; do python3 -c "import sys, xml.etree.ElementTree as E; E.parse(sys.argv[1])" "$f" && echo "ok $f"; done && .venv/bin/ruff check .`
Expected: zweimal `ok`, ruff ohne Befunde.

- [ ] **Step 6: Stand festhalten** – kein Commit; volle Testsuite `.venv/bin/pytest -q` grün.

---

### Task 16: Installation in Kodi und Abnahme

**Files:**
- Modify: `CLAUDE.md` (Projekt), `docs/ergebnisse-teilprojekt-1.md` bleibt; Create: `docs/ergebnisse-teilprojekt-2.md`

**Interfaces:**
- Consumes: alles aus Task 1–15.

- [ ] **Step 1: Volle Testsuite und Bündel**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check . && ls addon/script.telegram.calls/vendor/PYTHON_VERSION`
Expected: alle Tests grün (118), ruff ohne Befunde.

- [ ] **Step 2: In Kodi installieren**

Run:
```bash
ssh root@192.168.178.10 'cd /storage/tgcalls-test && python3 check.py --guard'
tools/deploy.sh
```
Expected: Ausgabe von `Addons.SetAddonEnabled` mit `"result":"OK"` und `Kopiert nach …`. Danach in Kodi: **Add-ons → Programm-Add-ons → Telegram-Anrufe** ist sichtbar. Kodi nicht neu starten.

- [ ] **Step 3: Einstellungen** (Nutzer)

Der Nutzer trägt `api_id` und `api_hash` in den Add-on-Einstellungen ein (die Werte aus seiner `config.ini`; nicht von Claude kopieren). Standardwerte von `direkte_ausgabe` und `echo` prüfen.

- [ ] **Step 4: Abnahme mit dem Nutzer und Philipp** – die Erfolgskriterien der Spec, jeweils Ergebnis notieren:

1. Add-on öffnen: Session aus Task 12 wird übernommen (keine Anmeldung). Schriften lesbar? (Arctic Zephyr). In „Alle Kontakte“ per Kontextmenü „Suchen …“ Philipp finden und zu den Favoriten hinzufügen, zurück, Favorit mit OK anrufen. Beim Öffnen erscheint sofort die Startseite mit „Verbinde mit Telegram …“.
2. Während das Add-on offen ist, ruft Philipp an: Klingeldialog über jedem Fenster (auch in „Alle Kontakte“), OK nimmt an. Weckt das Klingeln einen laufenden Bildschirmschoner? (Bildschirmschoner-Zeit vorher nicht verstellen; ggf. nur beobachten.)
3. Zurück und Stopp legen auf; Statuszeile zeigt 3 s den Grund, dann zurück zum vorigen Bildschirm.
4. Echo und gleichzeitiges Reden mit dem gewählten Verfahren.
5. Absturz: während eines Gesprächs `ssh root@192.168.178.10 'pkill -f script.telegram.calls/worker/main.py'` → Kodi läuft weiter, Hinweis „Anrufteil neu gestartet“, Startseite, danach wieder anrufbar.
6. Zählprobe; Vergleich mit Teilprojekt 1 (1–2 s).
7. Läuft Spotify (Soloist) beim Anrufen: Es pausiert. Danach geht es nicht von selbst weiter.
8. Über Kodi-Ausgabe: Wechselt Kodi beim Start des SDP-Streams in die Musik-Visualisierung und verdeckt das Add-on? Falls ja: notieren; Abhilfe als Folgearbeit (Fenster nach `play_kodi` erneut zeigen).
9. Add-on mit Zurück auf der Startseite schließen (Rückfrage bestätigen) → Philipp erreicht das Gerät nicht mehr (Telegram zeigt nicht „klingelt“ bzw. der Anruf geht ins Leere).
10. Einstellungen → „Dieses Gerät abmelden“ bei geschlossenem Add-on → Meldung „Abgemeldet“; in der Telegram-App verschwindet das Gerät. Danach erneut per QR anmelden.

Danach: `ssh root@192.168.178.10 'cd /storage/tgcalls-test && python3 check.py --guard'` → OK.

- [ ] **Step 5: Ergebnisse dokumentieren**

`docs/ergebnisse-teilprojekt-2.md` mit Tabelle der zehn Punkte, Messwerten aus `docs/messtest-teilprojekt-2.md` und offenen Punkten für Teilprojekt 3. In der Projekt-`CLAUDE.md` den Abschnitt „Erkenntnisse“ um das Add-on ergänzen: Pfade (`addon/script.telegram.calls`, Testziel `/storage/tgcalls-addon`, Daten in `addon_data`), `tools/deploy.sh`, Skin-Schriften-Platzhalter, Sperrdatei, Messwerte.

- [ ] **Step 6: Stand berichten** – kein Commit, kein Push. Dem Nutzer Ergebnis und offene Punkte nennen.
