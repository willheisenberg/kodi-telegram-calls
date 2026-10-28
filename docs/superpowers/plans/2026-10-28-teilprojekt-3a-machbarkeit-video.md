# Teilprojekt 3a: Machbarkeitsmessung Video (Phase 0) – Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Klären, ob und wie der Videoweg der Spec trägt: Encoder im Bündel, Verzögerung von Kodi im Live-Modus (`udp://` + MPEG-TS), CPU-Last auf dem Pi 5, Kamera der C922 über ntgcalls an die Gegenseite, Videokennung eingehender Anrufe. Ergebnis ist ein Messprotokoll mit Entscheidungen; die Umsetzung folgt in Plan 3b.

**Architecture:** Drei Messwerkzeuge unter `tools/messtest/`, die auf dem Pi in einem eigenen Probeordner `/storage/tgcalls-probe` laufen (Bündel mit PyAV, getrennt vom installierten Add-on). Kodi wird nur per JSON-RPC bedient, PulseAudio nicht angefasst. Der Anruftest nutzt die Session des Add-ons an Ort und Stelle, während das Add-on beendet ist.

**Tech Stack:** Python 3.11 (LibreELEC 12), PyAV (FFmpeg in Python, aarch64-Wheel), numpy, Telethon 1.45.0, py-tgcalls 3.0.0 / ntgcalls 3.0.3, Kodi 21 JSON-RPC (Port 9090).

**Spec:** `docs/superpowers/specs/2026-10-28-teilprojekt-3-videoanrufe-design.md` (Abschnitt „Phase 0“ und „Entscheidungsregeln“).

## Global Constraints

- Code muss mit Python 3.11 laufen (LibreELEC 12); Bündel nur aarch64-Wheels (`manylinux_2_28_aarch64` / `manylinux_2_17_aarch64`).
- PulseAudio nicht verändern; vor und nach jedem Pi-Test `python3 /storage/tgcalls-test/check.py --guard`.
- Kodi-Einstellungen nicht ändern; Kodi nicht ohne Rückfrage stoppen. Laufende Wiedergabe nur nach Rückfrage unterbrechen.
- Session-Datei und API-Zugangsdaten nie kopieren oder ausgeben; Werkzeuge lesen sie an Ort und Stelle.
- Telefonnummern und Codes nicht protokollieren.
- Committen und Pushen nur auf ausdrückliche Anweisung des Nutzers (auch nicht in den Commit-Schritten dieses Plans ohne Freigabe).
- Entscheidungsregeln aus der Spec: Kodi-Anteil im Live-Modus deutlich über 1 s oder kein bündelbarer Encoder → anhalten, neu entscheiden, Nachtrag in der Spec; 720p zu teuer (Anrufprozess über 150 % von 400 % CPU) → 540p oder 360p; Codec ohne B-Frames, kurze GOP.

## Review Focus

1. **PyAV-Wheel ohne die nötigen Teile** (kein `mpegts`-Muxer, kein billiger Videoencoder, kein `v4l2`-Eingang): `av_probe.py` muss jede Fähigkeit einzeln als OK/FEHLT melden statt abzubrechen. Test: Task 1 Step 4 prüft die Ausgabe auf alle Zeilen.
2. **Kodi kann `udp://` nicht öffnen oder wartet lange auf die Formaterkennung:** `videolag.py` muss nach 15 s ohne aktiven Player mit klarer Meldung abbrechen und den Player stoppen. Test: Task 2 Step 3 (falscher Port).
3. **Lücke im Strom** (Encoder hängt, Netz): Verzögerung nach einer 1,5-s-Lücke messen, wie in Teilprojekt 2. Test: Task 2 Step 5.
4. **Kamera belegt oder abgesteckt:** `videocall_probe.py` muss ohne Kamera mit Testbild weiterlaufen und das melden. Test: Task 3 Step 3 (Gerät `/dev/video9`).
5. **Gegenseite schaltet ihre Kamera aus:** Probe protokolliert Pausen im eingehenden Video (> 1 s ohne Bild) mit Zeitpunkt. Test: Task 3 Step 6 (Nutzer bittet den Freund, die Kamera kurz auszuschalten).

---

## Dateistruktur

```
tools/messtest/
  av_probe.py         Task 1: Fähigkeiten und Kodiergeschwindigkeit von PyAV auf dem Pi
  videolag.py         Task 2: Verzögerung von Kodi im Live-Modus (udp:// + MPEG-TS)
  videocall_probe.py  Task 3: Videoanruf mit Kamera, Empfangsstatistik, Videokennung
tools/build-probe.sh  Task 1: Probebündel (PyAV + numpy) für /storage/tgcalls-probe
docs/messtest-teilprojekt-3.md   Task 4: Messprotokoll und Entscheidungen
```

`tools/messtest/tonweg.py` (Teilprojekt 2) verweist auf die am 2026-10-28
gelöschten Ordner `/storage/tgcalls-addon` und Skripte in `/storage/tgcalls-test`;
es läuft so nicht mehr und wird in diesem Plan nicht gebraucht.

---

### Task 1: PyAV-Probebündel und Fähigkeiten

**Files:**
- Create: `tools/build-probe.sh`
- Create: `tools/messtest/av_probe.py`

**Interfaces:**
- Consumes: nichts.
- Produces: Probeordner `/storage/tgcalls-probe/vendor` (PyAV + numpy, aarch64, Python 3.11); Messwerte „Encoder vorhanden“, „Kodier-fps und CPU“ für das Messprotokoll (Task 4).

- [ ] **Step 1: Bündelskript schreiben**

```bash
#!/usr/bin/env bash
# Probebündel für Teilprojekt 3a: PyAV + numpy (aarch64, LibreELECs Python) nach /storage/tgcalls-probe.
# Aufruf: tools/build-probe.sh [host]
set -euo pipefail
HOST="${1:-root@192.168.178.10}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT
python3 -m pip install --target "$OUT/vendor" --only-binary=:all: --implementation cp \
    --python-version 3.11 --platform manylinux_2_28_aarch64 --platform manylinux_2_17_aarch64 \
    --platform manylinux2014_aarch64 --no-compile av numpy
cp "$ROOT"/tools/messtest/av_probe.py "$ROOT"/tools/messtest/videolag.py \
   "$ROOT"/tools/messtest/videocall_probe.py "$OUT"/ 2>/dev/null || true
du -sh "$OUT/vendor"
ssh "$HOST" "rm -rf /storage/tgcalls-probe && mkdir -p /storage/tgcalls-probe"
tar -C "$OUT" -czf - . | ssh "$HOST" "tar -C /storage/tgcalls-probe -xzf -"
echo "Probebündel nach $HOST:/storage/tgcalls-probe"
```

- [ ] **Step 2: Fähigkeiten-Probe schreiben**

```python
#!/usr/bin/env python3
"""Teilprojekt 3a: Was kann PyAV auf dem Pi? Encoder, Muxer, V4L2-Eingang, Kodiergeschwindigkeit.

Aufruf auf dem Pi: python3 /storage/tgcalls-probe/av_probe.py
Jede Fähigkeit wird einzeln als OK/FEHLT gemeldet; ein Fehlen bricht nicht ab.
"""
import os
import sys
import time

sys.path.insert(0, '/storage/tgcalls-probe/vendor')
import av  # noqa: E402
import numpy as np  # noqa: E402

VIDEO = ['mpeg2video', 'libx264', 'libopenh264', 'h264_v4l2m2m', 'mjpeg']
AUDIO = ['mp2', 'aac', 'libopus', 's302m']
SIZES = [(1280, 720), (960, 540), (640, 360)]
FPS = 25


def has_codec(name):
    try:
        av.codec.Codec(name, 'w')
        return True
    except Exception:
        return False


def report(name, ok, detail=''):
    print(f'[{"OK" if ok else "FEHLT"}] {name}' + (f': {detail}' if detail else ''), flush=True)


def cpu_seconds():
    t = os.times()
    return t.user + t.system


def bench(codec, width, height, seconds=4):
    """Kodiert Testbilder in Echtzeitmenge; liefert (erreichte fps, CPU-Anteil in % eines Kerns)."""
    out = av.open(os.devnull, mode='w', format='mpegts')
    stream = out.add_stream(codec, rate=FPS)
    stream.width, stream.height, stream.pix_fmt = width, height, 'yuv420p'
    stream.options = {'g': str(FPS), 'bf': '0'}
    if codec == 'libx264':
        stream.options.update({'preset': 'ultrafast', 'tune': 'zerolatency'})
    frames = FPS * seconds
    rgb = np.zeros((height, width, 3), np.uint8)
    t0, c0 = time.monotonic(), cpu_seconds()
    for i in range(frames):
        rgb[:, :, 0] = i % 255
        frame = av.VideoFrame.from_ndarray(rgb, format='rgb24').reformat(format='yuv420p')
        frame.pts = i
        for packet in stream.encode(frame):
            out.mux(packet)
    for packet in stream.encode(None):
        out.mux(packet)
    out.close()
    wall, cpu = time.monotonic() - t0, cpu_seconds() - c0
    return frames / wall, 100 * cpu / (frames / FPS)


def main():
    report('PyAV', True, f'{av.__version__}, FFmpeg {av.library_versions.get("libavcodec")}')
    report('Muxer mpegts', 'mpegts' in av.formats_available)
    report('Eingang v4l2', 'v4l2' in av.formats_available)
    for name in VIDEO + AUDIO:
        report(f'Encoder {name}', has_codec(name))
    for codec in [c for c in VIDEO if has_codec(c) and c != 'h264_v4l2m2m']:
        for width, height in SIZES:
            try:
                fps, cpu = bench(codec, width, height)
                report(f'Kodieren {codec} {width}x{height}', fps >= FPS,
                       f'{fps:.0f} fps möglich, CPU {cpu:.0f} % eines Kerns bei {FPS} fps')
            except Exception as e:
                report(f'Kodieren {codec} {width}x{height}', False, f'{type(e).__name__}: {e}')


if __name__ == '__main__':
    main()
```

- [ ] **Step 3: Probebündel bauen und auf den Pi kopieren**

Run: `tools/build-probe.sh`
Expected: `du` zeigt eine Größe (PyAV etwa 30–60 MB), letzte Zeile `Probebündel nach root@192.168.178.10:/storage/tgcalls-probe`. Schlägt pip mit „No matching distribution“ fehl: es gibt kein aarch64-Wheel für Python 3.11 → Entscheidungsregel „kein bündelbarer Encoder“, Ergebnis notieren, Task 4 vorziehen.

- [ ] **Step 4: Fähigkeiten messen**

Run: `ssh root@192.168.178.10 'python3 /storage/tgcalls-test/check.py --guard; python3 /storage/tgcalls-probe/av_probe.py; python3 /storage/tgcalls-test/check.py --guard'`
Expected: Zeilen für PyAV, Muxer mpegts, Eingang v4l2, je Encoder aus `VIDEO` und `AUDIO`, dann `Kodieren …`-Zeilen je vorhandenem Videoencoder und Größe. Wächter vorher und nachher `[OK]`. Ausgabe vollständig ins Messprotokoll übernehmen (Task 4).

- [ ] **Step 5: Commit (nur nach Freigabe des Nutzers)**

```bash
git add tools/build-probe.sh tools/messtest/av_probe.py
git commit -m "tools: PyAV probe bundle and capability probe for video (part 3a)"
```

---

### Task 2: Verzögerung von Kodi im Live-Modus

**Files:**
- Create: `tools/messtest/videolag.py`

**Interfaces:**
- Consumes: Probebündel aus Task 1; ein Videoencoder, den Task 1 als „OK“ gemeldet hat (Name per `--codec`).
- Produces: Messwerte „Kodi-Verzögerung Video live, vor/nach Lücke“, „Startzeit bis erstes Bild“ für Task 4.

- [ ] **Step 1: Messwerkzeug schreiben**

```python
#!/usr/bin/env python3
"""Teilprojekt 3a: Verzögerung von Kodi bei einem Live-Videostrom (MPEG-TS über udp://).

Sendet Testbild + Stille im Echtzeittakt an udp://127.0.0.1:PORT, lässt Kodi die Adresse
abspielen und vergleicht laufend die gesendete Dauer mit Kodis Wiedergabezeit (JSON-RPC).
Nach --gap-at s pausiert der Sender --gap s lang (Lücke wie beim Annehmen eines Anrufs).
Unterbricht die laufende Kodi-Wiedergabe: nur nach Rückfrage beim Nutzer starten.

Aufruf auf dem Pi:
  python3 /storage/tgcalls-probe/videolag.py --codec mpeg2video --size 1280x720
"""
import argparse
import json
import socket
import sys
import time

sys.path.insert(0, '/storage/tgcalls-probe/vendor')
import av  # noqa: E402
import numpy as np  # noqa: E402

PORT = 23540
RATE = 48000
FPS = 25


def rpc(method, **params):
    with socket.create_connection(('127.0.0.1', 9090), timeout=5) as s:
        s.sendall(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode())
        buf = b''
        while True:
            buf += s.recv(65536)
            try:
                msg = json.loads(buf)
            except ValueError:
                continue
            if msg.get('id') == 1:
                return msg.get('result')
            buf = b''


def kodi_time():
    players = rpc('Player.GetActivePlayers') or []
    if not players:
        return None
    t = rpc('Player.GetProperties', playerid=players[0]['playerid'], properties=['time'])['time']
    return t['hours'] * 3600 + t['minutes'] * 60 + t['seconds'] + t['milliseconds'] / 1000


def stop_ours(url):
    for p in rpc('Player.GetActivePlayers') or []:
        item = rpc('Player.GetItem', playerid=p['playerid'], properties=['file'])['item']
        if item.get('file') == url:
            rpc('Player.Stop', playerid=p['playerid'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--codec', default='mpeg2video')
    parser.add_argument('--audio', default='mp2')
    parser.add_argument('--size', default='1280x720')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--gap-at', type=float, default=25)
    parser.add_argument('--gap', type=float, default=1.5)
    parser.add_argument('--port', type=int, default=PORT)
    args = parser.parse_args()
    width, height = map(int, args.size.split('x'))
    url = f'udp://127.0.0.1:{args.port}'

    out = av.open(f'udp://127.0.0.1:{args.port}?pkt_size=1316', mode='w', format='mpegts',
                  options={'muxdelay': '0', 'muxpreload': '0', 'flush_packets': '1'})
    video = out.add_stream(args.codec, rate=FPS)
    video.width, video.height, video.pix_fmt = width, height, 'yuv420p'
    video.options = {'g': str(FPS), 'bf': '0'}
    if args.codec == 'libx264':
        video.options.update({'preset': 'ultrafast', 'tune': 'zerolatency'})
    audio = out.add_stream(args.audio, rate=RATE, layout='stereo')

    rpc('Player.Open', item={'file': url})
    t0 = time.monotonic()
    first_seen = None
    rgb = np.zeros((height, width, 3), np.uint8)
    silence = np.zeros((2, RATE // FPS), np.int16)
    n, gap_done, next_report = 0, False, t0 + 1
    try:
        while True:
            now = time.monotonic()
            sent = n / FPS
            if sent >= args.seconds:
                break
            if not gap_done and sent >= args.gap_at:
                print(f'{sent:6.1f} s  LÜCKE {args.gap} s', flush=True)
                time.sleep(args.gap)
                t0 += args.gap
                gap_done = True
                continue
            rgb[:, :, 1] = (n * 7) % 255
            vf = av.VideoFrame.from_ndarray(rgb, format='rgb24').reformat(format='yuv420p')
            vf.pts = n
            for packet in video.encode(vf):
                out.mux(packet)
            af = av.AudioFrame.from_ndarray(silence.reshape(1, -1), format='s16', layout='stereo')
            af.sample_rate, af.pts = RATE, n * (RATE // FPS)
            for packet in audio.encode(af):
                out.mux(packet)
            n += 1
            if now >= next_report:
                kt = kodi_time()
                if kt is not None and first_seen is None:
                    first_seen = now - t0
                    print(f'erstes Bild in Kodi nach {first_seen:.2f} s', flush=True)
                if kt is None and now - t0 > 15:
                    print('ABBRUCH: Kodi spielt nach 15 s nichts ab (udp:// nicht geöffnet?)', flush=True)
                    break
                lag = None if kt is None else round(sent - kt, 2)
                print(f'{sent:6.1f} s  Kodi {kt}  Verzögerung {lag}', flush=True)
                next_report += 2
            time.sleep(max(0.0, t0 + n / FPS - time.monotonic()))
    finally:
        stop_ours(url)
        out.close()


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Rückfrage beim Nutzer**

Die Messung unterbricht laufende Wiedergabe für etwa 1–2 Minuten pro Lauf und zeigt ein farbiges Testbild. Erst nach Zustimmung weitermachen. Vorher prüfen, dass kein Anruf läuft (`tail -n1 …/worker.log`) und nichts abspielt (`Player.GetActivePlayers` leer).

- [ ] **Step 3: Fehlerfall prüfen (Kodi findet nichts)**

Kodi eine `udp://`-Adresse ohne Sender öffnen lassen und nach 20 s nachsehen:
`ssh root@192.168.178.10 'python3 -c "import json,socket;s=socket.create_connection((\"127.0.0.1\",9090));s.sendall(json.dumps({\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"Player.Open\",\"params\":{\"item\":{\"file\":\"udp://127.0.0.1:23599\"}}}).encode());print(s.recv(4096))"; sleep 20; python3 -c "import json,socket;s=socket.create_connection((\"127.0.0.1\",9090));s.sendall(json.dumps({\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"Player.GetActivePlayers\"}).encode());print(s.recv(4096))"'`
Expected: Notieren, ob Kodi bei einem stummen `udp://` hängt (aktiver Player ohne Daten) oder aufgibt, und nach wie vielen Sekunden. Hängt er: per `Player.Stop` beenden. Das bestimmt später, wie die Videoausgabe einen Startfehler erkennt.

- [ ] **Step 4: Messläufe**

Run (je Lauf, Wächter vorher/nachher):
`ssh root@192.168.178.10 'python3 /storage/tgcalls-test/check.py --guard; python3 /storage/tgcalls-probe/videolag.py --codec <codec aus Task 1> --size 1280x720; python3 /storage/tgcalls-test/check.py --guard'`
Läufe: bester Codec aus Task 1 in 1280x720; falls dieser über 150 % CPU braucht oder Kodi ruckelt, zusätzlich 960x540 und 640x360.
Expected: Zeile „erstes Bild in Kodi nach … s“, dann alle 2 s eine Verzögerungszeile. Ziel laut Spec: Verzögerung vor der Lücke unter 1 s. Zusätzlich während des Laufs `top -b -n 2 -d 5 | grep -E "kodi|python3"` in einer zweiten SSH-Sitzung für die CPU-Last von Kodi (Dekodieren) und Sender.

- [ ] **Step 5: Lücke auswerten**

Expected: Nach `LÜCKE 1.5 s` bleibt die Verzögerung im Live-Modus annähernd gleich (Kodi gleicht an), statt wie in Teilprojekt 2 auf ~7 s zu springen. `grep "stream stalled" /storage/.kodi/temp/kodi.log | tail -3` zeitlich zuordnen. Ergebnis für Task 4 notieren.

- [ ] **Step 6: Commit (nur nach Freigabe des Nutzers)**

```bash
git add tools/messtest/videolag.py
git commit -m "tools: measure Kodi delay for a live MPEG-TS stream over udp (part 3a)"
```

---

### Task 3: Videoanruf mit Kamera über ntgcalls

**Files:**
- Create: `tools/messtest/videocall_probe.py`

**Interfaces:**
- Consumes: Probebündel aus Task 1 (PyAV für die Kamera), Bündel des installierten Add-ons (`/storage/.kodi/addons/script.telegram.calls/vendor`: Telethon, py-tgcalls, ntgcalls), Session `addon_data/script.telegram.calls/telegram.session` und `api_id`/`api_hash` aus `addon_data/script.telegram.calls/settings.xml` (an Ort und Stelle gelesen, nie ausgegeben).
- Produces: Messwerte „Kamera an Gegenseite: Bild sichtbar ja/nein, Auflösung/fps gesendet“, „eingehendes Video: Auflösung, fps, Pausen“, „Videokennung bei eingehendem Anruf“ für Task 4.

- [ ] **Step 1: Probe schreiben**

```python
#!/usr/bin/env python3
"""Teilprojekt 3a: Videoanruf mit der C922, Empfangsstatistik und Videokennung.

  ausgehend:  python3 videocall_probe.py call <user_id> [--size 1280x720] [--seconds 60] [--device /dev/video0]
  eingehend:  python3 videocall_probe.py wait [--seconds 60]

Das Add-on muss beendet sein (gleiche Session). Sendet das Kamerabild (oder ein Testbild, wenn die
Kamera fehlt) und Stille; zählt eingehende Videobilder (Größe, fps, Pausen > 1 s). Gibt keine
Nummern und keine Zugangsdaten aus.
"""
import argparse
import asyncio
import os
import sys
import threading
import time
import xml.etree.ElementTree as ET

sys.path.insert(0, '/storage/.kodi/addons/script.telegram.calls/vendor')
sys.path.append('/storage/tgcalls-probe/vendor')
import av  # noqa: E402
import numpy as np  # noqa: E402
from ntgcalls import MediaSource  # noqa: E402
from pytgcalls import PyTgCalls  # noqa: E402
from pytgcalls import filters as fl  # noqa: E402
from pytgcalls.types import CallConfig, ChatUpdate, Device, Direction  # noqa: E402
from pytgcalls.types.raw import AudioParameters, AudioStream, Stream, VideoParameters, VideoStream  # noqa: E402
from pytgcalls.types.stream.frame import Frame  # noqa: E402
from telethon import TelegramClient, events  # noqa: E402
from telethon.tl.types import UpdatePhoneCall  # noqa: E402

DATA = '/storage/.kodi/userdata/addon_data/script.telegram.calls'
FPS = 25


def credentials():
    root = ET.parse(os.path.join(DATA, 'settings.xml')).getroot()
    values = {s.get('id'): (s.text or '') for s in root.iter('setting')}
    return int(values['api_id']), values['api_hash']


class Camera:
    """Liest die Kamera in einem Thread; letztes Bild als I420-Bytes. Ohne Kamera ein Testbild."""

    def __init__(self, device, width, height):
        self.width, self.height = width, height
        self.latest, self.ok, self.frames = None, False, 0
        self._stop = threading.Event()
        threading.Thread(target=self._run, args=(device,), daemon=True).start()

    def _run(self, device):
        try:
            container = av.open(device, format='v4l2', options={
                'video_size': f'{self.width}x{self.height}', 'input_format': 'mjpeg', 'framerate': str(FPS)})
            self.ok = True
            for frame in container.decode(video=0):
                if self._stop.is_set():
                    break
                self.latest = frame.reformat(width=self.width, height=self.height,
                                             format='yuv420p').to_ndarray().tobytes()
                self.frames += 1
        except Exception as e:
            print(f'Kamera nicht verfügbar ({type(e).__name__}: {e}), sende Testbild', flush=True)
            self.ok = False
            test = np.full((self.height * 3 // 2, self.width), 128, np.uint8)
            test[: self.height, :] = 60
            while not self._stop.is_set():
                self.latest = test.tobytes()
                self.frames += 1
                time.sleep(1 / FPS)

    def stop(self):
        self._stop.set()


class Stats:
    def __init__(self):
        self.count, self.sizes, self.last, self.pauses = 0, set(), None, []
        self.t0 = time.monotonic()

    def frame(self, info):
        now = time.monotonic()
        if self.last is not None and now - self.last > 1:
            self.pauses.append((round(self.last - self.t0, 1), round(now - self.last, 1)))
        self.last = now
        self.count += 1
        self.sizes.add((info.width, info.height))


async def run(args):
    api_id, api_hash = credentials()
    client = TelegramClient(os.path.join(DATA, 'telegram'), api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        sys.exit('Session nicht angemeldet')
    calls = PyTgCalls(client)
    width, height = map(int, args.size.split('x'))
    stats = Stats()
    ended = asyncio.Event()
    peer = {'id': None}

    @client.on(events.Raw(UpdatePhoneCall))
    async def raw(update):
        call = update.phone_call
        print(f'{time.strftime("%H:%M:%S")} Telegram {type(call).__name__} '
              f'video={getattr(call, "video", None)}', flush=True)

    @calls.on_update(fl.stream_frame(Direction.INCOMING, Device.CAMERA))
    async def frames(_, update):
        for f in update.frames:
            stats.frame(f.info)

    @calls.on_update(fl.chat_update(ChatUpdate.Status.LEFT_CALL))
    async def left(_, update):
        ended.set()

    send = Stream(microphone=AudioStream(MediaSource.EXTERNAL, '', AudioParameters(48000, 1)),
                  camera=VideoStream(MediaSource.EXTERNAL, '', VideoParameters(width, height, FPS)))
    receive = Stream(microphone=AudioStream(MediaSource.EXTERNAL, '', AudioParameters(48000, 2)),
                     camera=VideoStream(MediaSource.EXTERNAL, '', VideoParameters(width, height, FPS)))

    if args.mode == 'wait':
        incoming = asyncio.get_running_loop().create_future()

        @calls.on_update(fl.chat_update(ChatUpdate.Status.INCOMING_CALL))
        async def ring(_, update):
            if not incoming.done():
                incoming.set_result(update.chat_id)

    await calls.start()
    if args.mode == 'call':
        peer['id'] = args.user_id
        print('rufe an …', flush=True)
        await calls.play(peer['id'], send, config=CallConfig(timeout=45))
    else:
        print('warte auf eingehenden Anruf …', flush=True)
        peer['id'] = await asyncio.wait_for(incoming, 120)
        await calls.play(peer['id'], send)
    await calls.record(peer['id'], receive)
    print('verbunden', flush=True)
    stats.t0 = time.monotonic()

    camera = Camera(args.device, width, height)
    silence = bytes(960)
    start = time.monotonic()
    n = 0
    try:
        while time.monotonic() - start < args.seconds and not ended.is_set():
            if camera.latest is not None:
                await calls.send_frame(peer['id'], Device.CAMERA, camera.latest,
                                       Frame.Info(width=width, height=height))
            for _ in range(4):
                await calls.send_frame(peer['id'], Device.MICROPHONE, silence)
            n += 1
            await asyncio.sleep(max(0.0, start + n / FPS - time.monotonic()))
    finally:
        camera.stop()
        try:
            await calls.leave_call(peer['id'])
        except Exception:
            pass
    dur = max(0.1, (stats.last or stats.t0) - stats.t0)
    print(f'Kamera: {"C922" if camera.ok else "Testbild"}, {camera.frames} Bilder gelesen')
    print(f'Eingehend: {stats.count} Bilder, Größen {sorted(stats.sizes)}, '
          f'{stats.count / dur:.1f} fps, Pausen >1 s (ab s, Dauer s): {stats.pauses}')
    await client.disconnect()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['call', 'wait'])
    parser.add_argument('user_id', type=int, nargs='?')
    parser.add_argument('--size', default='1280x720')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--device', default='/dev/video0')
    args = parser.parse_args()
    if args.mode == 'call' and args.user_id is None:
        parser.error('call braucht eine user_id')
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Rückfrage und Vorbereitung**

Mit dem Nutzer einen Termin mit einem Freund vereinbaren. Dann: Wächter prüfen; Add-on beenden (`kodi-send -a "StopScript(script.telegram.calls)"`), prüfen, dass kein `worker/main.py` mehr läuft (sonst hält er Session und Sperre). Die `user_id` des Freundes aus `favoriten.json` lesen, nicht ausgeben lassen, sondern direkt als Argument verwenden.

- [ ] **Step 3: Fehlerfall Kamera prüfen (ohne Anruf)**

Run: `ssh root@192.168.178.10 'cd /storage/tgcalls-probe && timeout 5 python3 -c "import sys; sys.argv=[\"x\",\"wait\"]; import videocall_probe as v, time; c=v.Camera(\"/dev/video9\",640,360); time.sleep(2); print(c.ok, c.frames)"'`
Expected: Meldung „Kamera nicht verfügbar (…), sende Testbild“, dann `False` und eine Bildzahl > 0. Danach dasselbe mit `/dev/video0`: `True` und Bildzahl > 0 (C922 liefert MJPEG). Fehlt der `v4l2`-Eingang in PyAV (Task 1), stattdessen notieren und für Plan 3b `v4l2-ctl --stream-mmap --stream-to=-` als Kameraquelle vorsehen.

- [ ] **Step 4: Ausgehender Videoanruf**

Run: `ssh root@192.168.178.10 'cd /storage/tgcalls-probe && python3 videocall_probe.py call <id> --size 1280x720 --seconds 60'`
Expected: `verbunden`, nach 60 s Statistikzeilen. Der Freund bestätigt, dass er das Kamerabild sieht, und beschreibt Schärfe und Flüssigkeit; er lässt seine Kamera an. Eingehend: Bildgrößen und fps notieren. CPU dabei mit `top -b -n 2 -d 5 | grep python3` messen.

- [ ] **Step 5: Eingehender Videoanruf**

Run: `ssh root@192.168.178.10 'cd /storage/tgcalls-probe && python3 videocall_probe.py wait --seconds 45'`, dann ruft der Freund per Video an.
Expected: Zeile `Telegram PhoneCallRequested video=True` (Videokennung); Gespräch verbunden; Statistik. Danach ruft der Freund einmal als reinen Sprachanruf an (`video=False` erwartet; Probe beendet sich nach 45 s).

- [ ] **Step 6: Kamera der Gegenseite aus**

Während eines weiteren Laufs von Step 4 schaltet der Freund nach etwa 20 s seine Kamera für 10 s aus.
Expected: In „Pausen >1 s“ steht ein Eintrag um 20 s mit etwa 10 s Dauer. Notieren, ob Telegram dabei zusätzlich ein Ereignis schickt (Ausgaben der `Telegram …`-Zeilen).

- [ ] **Step 7: Add-on wieder starten**

Run: `ssh root@192.168.178.10 'kodi-send -a "RunAddon(script.telegram.calls)"; sleep 12; tail -n2 /storage/.kodi/userdata/addon_data/script.telegram.calls/worker.log; python3 /storage/tgcalls-test/check.py --guard'`
Expected: Anrufprozess läuft wieder (`Befehl {'typ': 'contacts'}`), Wächter `[OK]`.

- [ ] **Step 8: Commit (nur nach Freigabe des Nutzers)**

```bash
git add tools/messtest/videocall_probe.py
git commit -m "tools: video call probe with camera, receive stats and video flag (part 3a)"
```

---

### Task 4: Messprotokoll und Entscheidungen

**Files:**
- Create: `docs/messtest-teilprojekt-3.md`
- Modify (nur wenn eine Entscheidungsregel greift): `docs/superpowers/specs/2026-10-28-teilprojekt-3-videoanrufe-design.md` (Nachtrag am Ende)

**Interfaces:**
- Consumes: Ausgaben von Task 1–3.
- Produces: Entscheidungen, auf denen Plan 3b aufbaut: Videoencoder, Toncodec, Auflösung und Bildrate (Senden und Kodi), Kameraquelle (PyAV-v4l2 oder v4l2-ctl), Videokennung eingehender Anrufe (Feld und Wert), Verhalten bei ausgeschalteter Kamera der Gegenseite, Kodi-Verzögerung im Live-Modus (Wert für die Echounterdrückung), Startfehler-Erkennung bei `udp://`.

- [ ] **Step 1: Protokoll schreiben**

Gliederung von `docs/messtest-teilprojekt-3.md`:

```markdown
# Messtest Teilprojekt 3: Video (Phase 0)

Stand: <Datum>. Gerät: Raspberry Pi 5, LibreELEC 12.2.1, Kodi 21.3, C922.

## Ergebnis
| Frage | Ergebnis | Entscheidung |
|---|---|---|
| Encoder im Bündel | … | … |
| Kodi live über udp:// | Verzögerung … s, nach 1,5-s-Lücke … s | … |
| CPU 720p/25 | Sender … %, Kodi … % | Auflösung … |
| Kamera an Gegenseite | … | Kameraquelle … |
| Eingehendes Video | Größen …, … fps | … |
| Videokennung | PhoneCallRequested.video = … | … |
| Kamera der Gegenseite aus | Pause … s, Ereignis … | … |
| Startfehler udp:// | … | … |

## Rohdaten
(vollständige Ausgaben von av_probe.py, videolag.py, videocall_probe.py)
```

- [ ] **Step 2: Entscheidungsregeln anwenden**

Für jede Zeile die Spec-Regeln anwenden (siehe Global Constraints). Greift „anhalten“ (Kodi-Anteil deutlich über 1 s oder kein Encoder), einen Nachtrag „## Nachtrag <Datum>: Ergebnis Phase 0“ an die Spec anhängen und den Nutzer vor Plan 3b fragen, wie es weitergeht.

- [ ] **Step 3: Probeordner auf dem Pi entfernen**

Run: `ssh root@192.168.178.10 'rm -rf /storage/tgcalls-probe; python3 /storage/tgcalls-test/check.py --guard'`
Expected: Wächter `[OK]`. (Der Ordner wird für Plan 3b nicht gebraucht; das Bündel des Add-ons bekommt PyAV dort über `tools/build-bundle.sh`.)

- [ ] **Step 4: Commit (nur nach Freigabe des Nutzers)**

```bash
git add docs/messtest-teilprojekt-3.md docs/superpowers/specs/2026-10-28-teilprojekt-3-videoanrufe-design.md
git commit -m "docs: video feasibility results (part 3a)"
```

---

## Danach: Plan 3b

Plan 3b (Umsetzung) wird nach Task 4 mit den gemessenen Werten geschrieben:
Kamera, Bildmischer, Medien-Taktgeber, Videoausgabe, CallManager/Backend,
Protokoll, Oberfläche, Abnahme – wie in der Spec beschrieben.
