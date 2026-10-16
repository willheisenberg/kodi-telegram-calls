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
import time

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

    # Nur der Hauptthread liest die Tastatur. Fragt der Anrufprozess nach Code oder Passwort,
    # merkt sich der Ereignis-Thread das, und die nächste Zeile geht dorthin.
    pending = []  # 'code' | 'passwort'
    phone_login = threading.Event()

    def show_events():
        while True:
            message = events.get()
            typ = message['typ']
            if typ == 'qr':
                if phone_login.is_set():
                    continue
                code = qrcode.QRCode(border=1)
                code.add_data(message['url'])
                text = io.StringIO()
                code.print_ascii(out=text, invert=True)
                # Bildschirm leeren: nur der neueste Code gilt, ältere dürfen nicht stehen bleiben.
                print('\033[2J\033[H' + text.getvalue()
                      + f'{time.strftime("%H:%M:%S")} In Telegram: Einstellungen → Geräte → Gerät verbinden.'
                      + ' Gilt etwa 30 s, danach erscheint von selbst ein neuer Code.'
                      + ' Oder "telefon" eingeben.', flush=True)
            elif typ == 'contacts':
                for entry in message['liste']:
                    print(f'{entry["id"]:>12}  {entry["name"]}{"  (Gruppe)" if entry["gruppe"] else ""}')
            elif typ == 'ready' and not message.get('angemeldet'):
                print('Nicht angemeldet: QR-Code folgt (oder "telefon" eingeben).', flush=True)
                worker.send('login_qr')
            elif typ == 'need_code':
                pending.append('code')
                print('Code aus der Telegram-App eingeben und Enter:', flush=True)
            elif typ == 'need_password':
                pending.append('passwort')
                print('Zwei-Faktor-Passwort eingeben und Enter (wird nicht angezeigt):', flush=True)
            elif typ == 'login_error':
                print('Anmeldung:', message.get('grund'), flush=True)
                if message.get('erneut') in ('code', 'passwort'):
                    pending.append(message['erneut'])
                    print('Bitte erneut eingeben und Enter:', flush=True)
            else:
                print('<', message, flush=True)
            if typ == '_lost':
                print('Anrufprozess beendet.')
                os._exit(1)

    threading.Thread(target=show_events, daemon=True).start()
    muted = False
    try:
        while True:
            if pending and pending[0] == 'passwort':
                worker.send('login_password', passwort=getpass.getpass(''))
                pending.pop(0)
                continue
            line = sys.stdin.readline()
            if not line:
                break
            parts = line.split()
            if pending and pending[0] in ('code', 'passwort'):
                kind = pending.pop(0)
                if kind == 'code':
                    worker.send('login_code', code=line.strip())
                    time.sleep(2)  # fragt Telegram nach dem Passwort, soll getpass es verdeckt abfragen
                else:
                    worker.send('login_password', passwort=line.rstrip('\n'))
                continue
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
                phone_login.set()
                print('Telefonnummer mit +49 eingeben und Enter:', flush=True)
                worker.send('login_phone', nummer=sys.stdin.readline().strip())
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
