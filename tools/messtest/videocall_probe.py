#!/usr/bin/env python3
"""Teilprojekt 3a: Videoanruf mit der C922, Empfangsstatistik und Videokennung.

  ausgehend:  python3 videocall_probe.py call <user_id>|--name <Favorit> [--size 1280x720] [--seconds 60] [--device /dev/video0]
  eingehend:  python3 videocall_probe.py wait [--seconds 60]

Das Add-on muss beendet sein (gleiche Session). Sendet das Kamerabild (oder ein Testbild, wenn die
Kamera fehlt) und Stille; zählt eingehende Videobilder (Größe, fps, Pausen > 1 s). Gibt keine
Nummern und keine Zugangsdaten aus.
"""
import argparse
import asyncio
import json
import os
import subprocess
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
        self._proc = None
        self._stop = threading.Event()
        threading.Thread(target=self._run, args=(device,), daemon=True).start()

    def _run(self, device):
        # PyAV auf dem Pi hat keinen v4l2-Eingang (av_probe): MJPEG per v4l2-ctl lesen, mit PyAV dekodieren.
        try:
            if not os.path.exists(device):
                raise FileNotFoundError(device)
            proc = subprocess.Popen(
                ['v4l2-ctl', '-d', device,
                 f'--set-fmt-video=width={self.width},height={self.height},pixelformat=MJPG',
                 f'--set-parm={FPS}', '--stream-mmap', '--stream-to=-', '--stream-count=0'],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self._proc = proc
            container = av.open(proc.stdout, format='mjpeg')
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
        if self._proc is not None:
            self._proc.terminate()


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


async def favourite_by_name(client, name):
    """Sucht unter den Favoriten des Add-ons den ersten, dessen Name `name` enthält; gibt keine ID aus."""
    with open(os.path.join(DATA, 'favoriten.json')) as f:
        ids = json.load(f)
    for user_id in ids:
        user = await client.get_entity(user_id)
        full = ' '.join(filter(None, [user.first_name, user.last_name]))
        if name.lower() in full.lower():
            print(f'Favorit gefunden: {full}', flush=True)
            return user_id
    sys.exit(f'kein Favorit mit "{name}"')


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
        peer['id'] = args.user_id or await favourite_by_name(client, args.name)
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
    parser.add_argument('--name', help='call: Favorit, dessen Name dies enthält')
    args = parser.parse_args()
    if args.mode == 'call' and args.user_id is None:
        if not args.name:
            parser.error('call braucht eine user_id oder --name')
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
