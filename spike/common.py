"""Gemeinsame Hilfen für die Testskripte: Suchpfad, Konfiguration, Client."""
import configparser
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(HERE, 'vendor')
CONFIG = os.path.join(HERE, 'config.ini')
SESSION = os.path.join(HERE, 'tgcalls')

sys.path.insert(0, VENDOR)


def die(message, code=1):
    print(f'FEHLER: {message}', file=sys.stderr)
    sys.exit(code)


def load_config():
    if not os.path.exists(CONFIG):
        die(f'{CONFIG} fehlt. config.example.ini kopieren und ausfüllen.')
    parser = configparser.ConfigParser()
    parser.read(CONFIG)
    try:
        return parser.getint('telegram', 'api_id'), parser.get('telegram', 'api_hash')
    except (configparser.Error, ValueError) as e:
        die(f'config.ini unvollständig: {e}')


def make_client():
    from telethon import TelegramClient

    api_id, api_hash = load_config()
    return TelegramClient(SESSION, api_id, api_hash)


def kodi_rpc(method, params=None):
    """Ein JSON-RPC-Aufruf an das lokale Kodi (TCP-Port 9090)."""
    import json
    import socket

    with socket.create_connection(('127.0.0.1', 9090), timeout=5) as sock:
        sock.sendall(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}).encode())
        buf = b''
        while True:
            buf += sock.recv(65536)
            try:
                message = json.loads(buf)
            except ValueError:
                continue
            buf = b''
            if message.get('id') == 1:
                if 'error' in message:
                    raise RuntimeError(f'Kodi {method}: {message["error"]}')
                return message['result']
