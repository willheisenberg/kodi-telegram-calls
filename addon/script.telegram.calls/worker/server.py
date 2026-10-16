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
