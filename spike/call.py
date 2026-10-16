#!/usr/bin/env python3
"""Ausgehender Sprachanruf: Webcam-Mikrofon per ALSA rein, Gegenseite per RTP an Kodi raus.

PulseAudio wird nicht benutzt (gehört Soloist, siehe CLAUDE.md). Strg+C legt auf.
"""
import argparse
import asyncio
import logging
import os
import signal
import subprocess
import sys
import time

import rtp_send
from common import HERE, die, kodi_rpc, make_client

RING_TIMEOUT = 45
CPU_INTERVAL = 10
RTP_PORT = 23533  # Soloist nutzt 23433
# Kodi öffnet den 48-kHz-RTP-Stream über eine SDP-Beschreibung (siehe rtp_send.py).
SDP_PATH = os.path.join(HERE, 'anruf.sdp')
MIC_RATE = 48000  # muss zu mic_capture.py passen
SPEAKER_RATE = 48000  # muss zu rtp_send.py passen


def guard(label):
    """Soloist-Wächter aus check.py; meldet, ob PulseAudio unverändert ist."""
    result = subprocess.run([sys.executable, os.path.join(HERE, 'check.py'), '--guard'],
                            capture_output=True, text=True)
    status = 'OK' if result.returncode == 0 else 'FEHLER'
    print(f'Wächter {label}: {status}', flush=True)
    if result.returncode != 0:
        print(result.stdout, end='')
    return result.returncode == 0


def kodi_busy():
    return kodi_rpc('Player.GetActivePlayers')


async def report_cpu():
    """Gibt alle CPU_INTERVAL Sekunden die CPU-Last aus (100 % = ein Kern), inkl. Kindprozesse."""
    def total():
        t = os.times()
        return t.user + t.system + t.children_user + t.children_system

    last_cpu, last_wall = total(), time.monotonic()
    while True:
        await asyncio.sleep(CPU_INTERVAL)
        cpu, wall = total(), time.monotonic()
        print(f'CPU: {100 * (cpu - last_cpu) / (wall - last_wall):.0f} %', flush=True)
        last_cpu, last_wall = cpu, wall


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contact', help='Benutzername (@name) oder Telefonnummer (+49...)')
    parser.add_argument('--mic', default='plughw:CARD=Webcam,DEV=0', help='ALSA-Aufnahmegerät')
    parser.add_argument('--debug', action='store_true',
                        help='Rohe Anrufmeldungen von Telegram und Bibliotheks-Log ausgeben')
    parser.add_argument('--dump', metavar='DATEI',
                        help='Diagnose: Ton der Gegenseite roh (s16le, 48 kHz, Stereo) in DATEI mitschreiben')
    args = parser.parse_args()
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s.%(msecs)03d %(name)s %(levelname)s: %(message)s',
            datefmt='%H:%M:%S',
        )
        logging.getLogger('telethon').setLevel(logging.INFO)

    if kodi_busy():
        die('Kodi spielt gerade etwas ab. Erst beenden, der Anruf würde es unterbrechen.')
    if not guard('vorher'):
        die('PulseAudio ist nicht im erwarteten Zustand, Test abgebrochen.')

    from ntgcalls import MediaSource
    from pytgcalls import PyTgCalls, exceptions
    from pytgcalls import filters as fl
    from pytgcalls.types import CallConfig, ChatUpdate
    from pytgcalls.types.raw import AudioParameters, AudioStream, Stream

    client = make_client()
    await client.connect()
    if not await client.is_user_authorized():
        die('Nicht angemeldet. Zuerst login.py ausführen.')
    try:
        peer = await client.get_entity(args.contact)
    except Exception as e:
        die(f'Kontakt {args.contact!r} nicht gefunden: {e}')

    if args.debug:
        from telethon import events
        from telethon.tl.types import UpdatePhoneCall

        @client.on(events.Raw(UpdatePhoneCall))
        async def on_raw_call(update):
            call = update.phone_call
            fields = {k: getattr(call, k, None) for k in ('reason', 'duration', 'video')}
            protocol = getattr(call, 'protocol', None)
            if protocol is not None:
                fields['library_versions'] = protocol.library_versions
            print(f'{time.strftime("%H:%M:%S")} TELEGRAM {type(call).__name__} {fields}', flush=True)

    calls = PyTgCalls(client)
    ended = asyncio.Event()

    @calls.on_update(fl.chat_update(ChatUpdate.Status.LEFT_CALL))
    async def on_left(_, update):
        print(f'Anruf beendet: {update.status}')
        ended.set()

    microphone = Stream(microphone=AudioStream(
        MediaSource.SHELL,
        f'python3 {os.path.join(HERE, "mic_capture.py")} {args.mic}',  # 48 kHz Stereo, begrenzter Rückstau
        AudioParameters(MIC_RATE, 2),
    ))
    # Bei record() steht der Ton der Gegenseite im Feld "microphone".
    # ntgcalls sucht das Programm immer über PATH, ein absoluter Pfad wird nicht gefunden.
    speaker = Stream(microphone=AudioStream(
        MediaSource.SHELL,
        f'python3 {os.path.join(HERE, "rtp_send.py")} {RTP_PORT}' + (f' {args.dump}' if args.dump else ''),
        AudioParameters(SPEAKER_RATE, 2),
    ))

    await calls.start()
    print(f'Rufe {getattr(peer, "first_name", args.contact)} an (Mikrofon: {args.mic}) ...')
    try:
        await calls.play(peer.id, microphone, config=CallConfig(timeout=RING_TIMEOUT))
        try:
            await calls.record(peer.id, speaker)
        except Exception:
            await calls.leave_call(peer.id)  # sauber auflegen statt die Verbindung abreißen zu lassen
            raise
    except exceptions.TimedOutAnswer:
        die(f'Nach {RING_TIMEOUT} s nicht angenommen.', 2)
    except exceptions.CallDeclined:
        die('Anruf abgelehnt.', 3)
    except exceptions.CallBusy:
        die('Besetzt.', 4)
    except exceptions.CallDiscarded:
        die('Anruf verworfen.', 5)

    started = time.monotonic()
    with open(SDP_PATH, 'w') as f:
        f.write(rtp_send.sdp(RTP_PORT))
    kodi_rpc('Player.Open', {'item': {'file': SDP_PATH}})
    print('Verbunden, Ton läuft über Kodi. Strg+C legt auf.')
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, ended.set)
    cpu_task = asyncio.create_task(report_cpu())
    await ended.wait()
    cpu_task.cancel()

    try:
        await calls.leave_call(peer.id)
    except exceptions.NotInCallError:
        pass
    for player in kodi_busy():
        item = kodi_rpc('Player.GetItem', {'playerid': player['playerid'], 'properties': ['file']})
        if item['item'].get('file', '') == SDP_PATH:
            kodi_rpc('Player.Stop', {'playerid': player['playerid']})
    print(f'Gesprächsdauer: {time.monotonic() - started:.0f} s')
    await client.disconnect()
    guard('nachher')


asyncio.run(main())
