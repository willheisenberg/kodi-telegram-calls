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
        self.quit = asyncio.Event()
        self.server = Server(os.path.join(data_dir, 'worker.sock'), self.on_command, on_orphaned=self.quit.set)
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
