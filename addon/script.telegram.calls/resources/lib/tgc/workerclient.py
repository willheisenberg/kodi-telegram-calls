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
