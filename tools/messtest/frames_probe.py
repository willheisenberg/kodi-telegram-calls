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
