#!/usr/bin/env python3
"""Messtest: Verzögerung vom Abspielen bis zum Schall am Webcam-Mikrofon.

Aufruf auf dem Pi:
  python3 tonweg.py alsa [--device hdmi:CARD=vc4hdmi0,DEV=0]
  python3 tonweg.py kodi
Spielt dreimal 1 s Rauschen und sucht es per Kreuzkorrelation in der Aufnahme.
Nutzt rtp_send.py und common.py aus Teilprojekt 1 (/storage/tgcalls-test).
"""
import argparse
import subprocess
import sys
import threading
import time

sys.path.insert(0, '/storage/tgcalls-test')
sys.path.insert(0, '/storage/tgcalls-addon/vendor')
import numpy as np  # noqa: E402
import rtp_send  # noqa: E402
from common import kodi_rpc  # noqa: E402

RATE = 48000
MIC = 'plughw:CARD=Webcam,DEV=0'
PORT = 23533
SDP = '/storage/tgcalls-addon/messtest.sdp'


def burst(seed):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(RATE) * 6000).clip(-32000, 32000).astype(np.int16)


def stereo(mono):
    return np.repeat(mono, 2).tobytes()


def record(seconds, out):
    proc = subprocess.run(['aplay', '-C', '-q', '-D', MIC, '-f', 'S16_LE', '-r', str(RATE), '-c', '1',
                           '-t', 'raw', '-d', str(seconds)], capture_output=True)
    out.append(np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float64))


def find(recording, signal):
    size = 1 << (len(recording) + len(signal)).bit_length()
    corr = np.fft.irfft(np.fft.rfft(recording, size) * np.conj(np.fft.rfft(signal, size)), size)
    corr = corr[:len(recording)]
    lag = int(np.argmax(corr))
    return lag, corr[lag] / (np.std(corr) + 1e-9)


def run_alsa(device, seed):
    sig = burst(seed)
    pcm = stereo(np.concatenate([np.zeros(RATE // 2, np.int16), sig, np.zeros(2 * RATE, np.int16)]))
    rec = []
    t_rec = time.monotonic()
    th = threading.Thread(target=record, args=(5, rec))
    th.start()
    time.sleep(0.5)
    t_play = time.monotonic()
    p = subprocess.run(['aplay', '-q', '-D', device, '-f', 'S16_LE', '-r', str(RATE), '-c', '2', '-t', 'raw',
                        '--buffer-time=60000'], input=pcm, capture_output=True)
    th.join()
    if p.returncode != 0:
        sys.exit(f'aplay auf {device} scheiterte: {p.stderr.decode().strip()}')
    return sig, rec[0], t_rec, t_play + 0.5


def run_kodi(seed):
    if kodi_rpc('Player.GetActivePlayers'):
        sys.exit('Kodi spielt gerade etwas, bitte erst beenden.')
    sig = burst(seed)
    with open(SDP, 'w') as f:
        f.write(rtp_send.sdp(PORT))
    sender = subprocess.Popen(['python3', '/storage/tgcalls-test/rtp_send.py', str(PORT)], stdin=subprocess.PIPE)
    state = {'stop': False}
    queue = []

    def pump():
        start, n = time.monotonic(), 0
        while not state['stop']:
            chunk = queue.pop(0) if queue else bytes(1920)  # 10 ms Stereo, sonst Stille
            sender.stdin.write(chunk)
            sender.stdin.flush()
            n += 1
            time.sleep(max(0, start + n * 0.01 - time.monotonic()))

    th = threading.Thread(target=pump)
    th.start()
    time.sleep(0.5)
    kodi_rpc('Player.Open', {'item': {'file': SDP}})
    time.sleep(4)  # Kodi puffert an
    rec = []
    t_rec = time.monotonic()
    rt = threading.Thread(target=record, args=(6, rec))
    rt.start()
    time.sleep(0.5)
    pcm = stereo(sig)
    t_burst = time.monotonic()  # die Warteschlange ist leer, der nächste 10-ms-Takt sendet den Anfang
    queue.extend(pcm[i:i + 1920] for i in range(0, len(pcm), 1920))
    rt.join()
    state['stop'] = True
    th.join()
    for player in kodi_rpc('Player.GetActivePlayers'):
        kodi_rpc('Player.Stop', {'playerid': player['playerid']})
    sender.stdin.close()
    sender.wait()
    return sig, rec[0], t_rec, t_burst


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('weg', choices=['alsa', 'kodi'])
    parser.add_argument('--device', default='hdmi:CARD=vc4hdmi0,DEV=0')
    args = parser.parse_args()
    delays = []
    for seed in range(3):
        sig, rec, t_rec, t_play = run_alsa(args.device, seed) if args.weg == 'alsa' else run_kodi(seed)
        lag, quality = find(rec, sig.astype(np.float64))
        delay = (t_rec + lag / RATE - t_play) * 1000
        print(f'Lauf {seed + 1}: {delay:.0f} ms (Güte {quality:.1f}, unter 8 unsicher)')
        delays.append(delay)
        time.sleep(1)
    print(f'{args.weg}: Median {sorted(delays)[1]:.0f} ms')


if __name__ == '__main__':
    main()
