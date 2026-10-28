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
SDP_PATH = '/storage/tgcalls-probe/videolag.sdp'


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


def drain(sent):
    """Sender steht: misst, wie weit Kodi noch spielt. Das ist sein Polster, ohne den Zeitversatz."""
    start = kodi_time()
    if start is None:
        return
    last, last_change, t_stop = start, time.monotonic(), time.monotonic()
    while time.monotonic() - last_change < 1.0 and time.monotonic() - t_stop < 10:
        time.sleep(0.05)
        kt = kodi_time()
        if kt is None:
            break
        if kt != last:
            last, last_change = kt, time.monotonic()
    print(f'Nachlauf: Kodi spielte nach dem Senderstopp noch {last - start:.2f} s '
          f'(bis {last_change - t_stop:.2f} s nach Stopp), Versatz {sent - last:.2f} s', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--codec', default='mpeg2video')
    parser.add_argument('--audio', default='mp2')
    parser.add_argument('--size', default='1280x720')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--gap-at', type=float, default=25)
    parser.add_argument('--gap', type=float, default=1.5)
    parser.add_argument('--port', type=int, default=PORT)
    parser.add_argument('--gop', type=int, default=FPS, help='Abstand der Schlüsselbilder in Bildern')
    parser.add_argument('--via', choices=['udp', 'sdp'], default='udp',
                        help='sdp: MPEG-TS in RTP, Kodi öffnet eine SDP-Datei (kein Live-Modus)')
    args = parser.parse_args()
    width, height = map(int, args.size.split('x'))
    if args.via == 'sdp':
        url = SDP_PATH
        with open(SDP_PATH, 'w') as f:
            f.write('v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=videolag\r\nc=IN IP4 127.0.0.1\r\n'
                    f't=0 0\r\nm=video {args.port} RTP/AVP 33\r\na=rtpmap:33 MP2T/90000\r\n')
        out = av.open(f'rtp://127.0.0.1:{args.port}?pkt_size=1328', mode='w', format='rtp_mpegts',
                      options={'max_delay': '0', 'flush_packets': '1'})
    else:
        url = f'udp://127.0.0.1:{args.port}'
        out = av.open(f'udp://127.0.0.1:{args.port}?pkt_size=1316', mode='w', format='mpegts',
                      options={'max_delay': '0', 'flush_packets': '1'})
    video = None if args.codec == 'none' else out.add_stream(args.codec, rate=FPS)
    if video is not None:
        video.width, video.height, video.pix_fmt = width, height, 'yuv420p'
        video.options = {'g': str(args.gop), 'bf': '0'}
    if args.codec == 'libx264':
        video.options.update({'preset': 'ultrafast', 'tune': 'zerolatency'})
    audio = out.add_stream(args.audio, rate=RATE, layout='stereo')

    # MP2T in RTP: ffmpeg braucht beim Öffnen der SDP schon Pakete, sonst bricht Kodi ab
    open_at = 0 if args.via == 'udp' else FPS
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
            for packet in (video.encode(vf) if video is not None else ()):
                out.mux(packet)
            af = av.AudioFrame.from_ndarray(silence.reshape(1, -1), format='s16', layout='stereo')
            af.sample_rate, af.pts = RATE, n * (RATE // FPS)
            for packet in audio.encode(af):
                out.mux(packet)
            n += 1
            if n == open_at + 1:
                rpc('Player.Open', item={'file': url})
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
        drain(sent)
    finally:
        stop_ours(url)
        out.close()


if __name__ == '__main__':
    main()
