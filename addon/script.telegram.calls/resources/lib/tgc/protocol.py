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
