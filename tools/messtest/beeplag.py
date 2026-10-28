#!/usr/bin/env python3
"""Teilprojekt 3a: echte Verzögerung bis zum Ton im Raum, gemessen mit dem Webcam-Mikrofon.

Sendet alle --every s einen kurzen 1-kHz-Piepton an Kodi und nimmt den Raum mit der C922
(ALSA direkt per aplay -C, nicht PulseAudio) auf. Verzögerung = Zeitpunkt, an dem der Ton im Mikrofon
ankommt, minus Zeitpunkt, zu dem er gesendet wurde. Enthält Kodi, HDMI, Denon und Schallweg.
Kodis Zeitangabe wird nicht gebraucht (die hat bei MPEG-TS einen unbekannten Versatz).

Wege:
  --via udp  MPEG-TS (Bild + mp2) über udp://, Kodi im Live-Modus (Videoanruf-Kandidat)
  --via l16  RTP L16 + SDP-Datei wie der Tonweg aus Teilprojekt 2 (Vergleich)
  --via rtp  H.264 und L16 als zwei RTP-Ströme + SDP-Datei (Dateimodus wie Teilprojekt 2)

Unterbricht laufende Wiedergabe und piept hörbar: nur nach Rückfrage beim Nutzer starten.
Aufruf auf dem Pi:
  python3 /storage/tgcalls-probe/beeplag.py --via udp --codec libx264
"""
import argparse
import subprocess
import sys
import threading
import time

sys.path.insert(0, '/storage/tgcalls-probe/vendor')
sys.path.insert(0, '/storage/tgcalls-probe')
sys.path.insert(0, '/storage/.kodi/addons/script.telegram.calls/worker')
import numpy as np  # noqa: E402
from videolag import rpc, stop_ours  # noqa: E402

RATE = 48000
FPS = 25
PORT = 23540
L16_PORT = 23560
SDP_PATH = '/storage/tgcalls-probe/tonprobe.sdp'  # manche neuen Namen lehnt Kodis Player.Open ab
BEEP_HZ = 1000
BEEP_S = 0.2
BLOCK = 240  # 5 ms Mikrofon-Blöcke
KODI_OPEN_STEP = 52  # rtp: Kodi öffnet nach 0,52 s (10-ms-Schritte)


class Recorder:
    """Liest das Webcam-Mikrofon; merkt sich zu jedem 5-ms-Block die Ankunftszeit und die 1-kHz-Stärke."""

    def __init__(self, device):
        self._proc = subprocess.Popen(
            ['aplay', '-C', '-q', '-D', device, '-f', 'S16_LE', '-r', str(RATE), '-c', '1', '-t', 'raw',
             '--buffer-time=40000', '--period-time=5000'],
            stdout=subprocess.PIPE)
        n = np.arange(BLOCK)
        self._wave = np.exp(-2j * np.pi * BEEP_HZ * n / RATE)
        self.blocks = []  # (Zeit am Blockende, Stärke)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            data = self._proc.stdout.read(BLOCK * 2)
            if len(data) < BLOCK * 2:
                return
            x = np.frombuffer(data, np.int16).astype(np.float32)
            self.blocks.append((time.monotonic(), abs(np.dot(x, self._wave)) / BLOCK))

    def stop(self):
        self._proc.terminate()
        self._proc.wait()


def open_kodi(path):
    if rpc('Player.Open', item={'file': path}) != 'OK':
        raise SystemExit(f'ABBRUCH: Kodi lehnt {path} ab')


def beep_pcm(t_start, count, every):
    """Ton (mono float) für die Proben ab Sekunde t_start: Piep in den ersten BEEP_S jeder Periode."""
    t = t_start + np.arange(count) / RATE
    phase = np.mod(t, every)
    on = (phase < BEEP_S) & (t >= every)
    return np.where(on, 0.9 * np.sin(2 * np.pi * BEEP_HZ * t), 0.0)


def send_udp(args, stop_at):
    import av
    out = av.open(f'udp://127.0.0.1:{PORT}?pkt_size=1316', mode='w', format='mpegts',
                  options={'max_delay': '0', 'flush_packets': '1'})
    video = None if args.codec == 'none' else out.add_stream(args.codec, rate=FPS)
    if video is not None:
        video.width, video.height, video.pix_fmt = 1280, 720, 'yuv420p'
        video.options = {'g': str(FPS), 'bf': '0'}
    if args.codec == 'libx264':
        video.options.update({'preset': 'ultrafast', 'tune': 'zerolatency'})
    audio = out.add_stream('mp2', rate=RATE, layout='stereo')
    url = f'udp://127.0.0.1:{PORT}'
    rgb = np.zeros((720, 1280, 3), np.uint8)
    per = RATE // FPS
    t0 = time.monotonic()
    n = 0
    try:
        while n / FPS < stop_at:
            rgb[:, :, 1] = (n * 7) % 255
            vf = av.VideoFrame.from_ndarray(rgb, format='rgb24').reformat(format='yuv420p')
            vf.pts = n
            for packet in (video.encode(vf) if video is not None else ()):
                out.mux(packet)
            mono = (beep_pcm(n / FPS, per, args.every) * 32767).astype(np.int16)
            af = av.AudioFrame.from_ndarray(np.repeat(mono, 2).reshape(1, -1), format='s16', layout='stereo')
            af.sample_rate, af.pts = RATE, n * per
            for packet in audio.encode(af):
                out.mux(packet)
            n += 1
            if n == 1:
                open_kodi(url)
            time.sleep(max(0.0, t0 + n / FPS - time.monotonic()))
    finally:
        stop_ours(url)
        out.close()
    return t0


def send_rtp(args, stop_at):
    """H.264 und L16 als zwei RTP-Ströme (mit RTCP für den Gleichlauf), Kodi spielt die SDP-Datei."""
    import av
    vport, aport = 23580, 23582
    with open(SDP_PATH, 'w') as f:
        f.write('v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=beeplag\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\n'
                f'm=video {vport} RTP/AVP 96\r\na=rtpmap:96 H264/90000\r\na=fmtp:96 packetization-mode=1\r\n'
                f'm=audio {aport} RTP/AVP 97\r\na=rtpmap:97 L16/{RATE}/2\r\n')
    vout = av.open(f'rtp://127.0.0.1:{vport}?pkt_size=1200', mode='w', format='rtp',
                   options={'payload_type': '96'})
    video = vout.add_stream('libx264', rate=300)  # Zeitbasis 1/300 s: 10-ms-Schritte und 25/30 fps exakt
    video.width, video.height, video.pix_fmt = 1280, 720, 'yuv420p'
    video.options = {'g': str(args.gop), 'bf': '0', 'preset': 'ultrafast', 'tune': 'zerolatency'}
    aout = av.open(f'rtp://127.0.0.1:{aport}?pkt_size=1200', mode='w', format='rtp',
                   options={'payload_type': '97'})
    audio = aout.add_stream('pcm_s16be', rate=RATE, layout='stereo')
    rgb = np.zeros((720, 1280, 3), np.uint8)
    per = RATE // 100
    t0 = time.monotonic()
    n = 0  # 10-ms-Schritte
    frames = 0
    next_frame = 0.0  # Sendezeit des nächsten normalen Bildes in s
    try:
        while n / 100 < stop_at:
            # die ersten --burst Bilder im 10-ms-Takt, damit ffmpegs Bildraten-Schätzung schnell fertig ist
            in_burst = KODI_OPEN_STEP <= n < KODI_OPEN_STEP + args.burst
            due = n / 100 + 1e-9 >= next_frame
            if due:
                next_frame += 1 / args.fps
            if in_burst or due:
                pts = n * 3 if in_burst else round((next_frame - 1 / args.fps) * 300)
                t_img = pts / 300
                # Prüfbild: weiß, solange der Piep läuft (Lippensynchronität), sonst wandernder Balken
                if t_img % args.every < BEEP_S and t_img >= args.every:
                    rgb[:] = 255
                else:
                    rgb[:] = 40
                    x = int(t_img % 2 * 620)  # 1240 px in 2 s
                    rgb[260:460, x:x + 40] = (255, 200, 0)
                vf = av.VideoFrame.from_ndarray(rgb, format='rgb24').reformat(format='yuv420p')
                vf.pts = pts
                if n == KODI_OPEN_STEP:
                    vf.pict_type = av.video.frame.PictureType.I
                frames += 1
                for packet in video.encode(vf):
                    vout.mux(packet)
            mono = (beep_pcm(n / 100, per, args.every) * 32767).astype(np.int16)
            af = av.AudioFrame.from_ndarray(np.repeat(mono, 2).reshape(1, -1), format='s16', layout='stereo')
            af.sample_rate, af.pts = RATE, n * per
            for packet in audio.encode(af):
                aout.mux(packet)
            n += 1
            if n == KODI_OPEN_STEP:
                open_kodi(SDP_PATH)
            time.sleep(max(0.0, t0 + n / 100 - time.monotonic()))
    finally:
        stop_ours(SDP_PATH)
        vout.close()
        aout.close()
    return t0


def send_l16(args, stop_at):
    import rtp
    with open(SDP_PATH, 'w') as f:
        f.write(rtp.sdp(L16_PORT))
    sender = rtp.RtpSender(L16_PORT)
    per = RATE // 100
    t0 = time.monotonic()
    n = 0
    try:
        while n / 100 < stop_at:
            mono = (beep_pcm(n / 100, per, args.every) * 32767).astype(np.int16)
            sender.send(np.repeat(mono, 2).tobytes())
            n += 1
            if n == 20:
                open_kodi(SDP_PATH)
            time.sleep(max(0.0, t0 + n / 100 - time.monotonic()))
    finally:
        stop_ours(SDP_PATH)
        sender.close()
    return t0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--via', choices=['udp', 'l16', 'rtp'], default='udp')
    parser.add_argument('--codec', default='libx264')
    parser.add_argument('--seconds', type=float, default=40)
    parser.add_argument('--every', type=float, default=4.0)
    parser.add_argument('--gop', type=int, default=10)
    parser.add_argument('--fps', type=int, default=FPS, help='rtp: Bilder pro Sekunde')
    parser.add_argument('--burst', type=int, default=0, help='rtp: so viele Bilder zu Beginn im 10-ms-Takt')
    parser.add_argument('--mic', default='plughw:CARD=Webcam')
    args = parser.parse_args()

    rec = Recorder(args.mic)
    time.sleep(1.0)
    t0 = {'udp': send_udp, 'l16': send_l16, 'rtp': send_rtp}[args.via](args, args.seconds)
    time.sleep(3.0)
    rec.stop()

    blocks = rec.blocks
    quiet = sorted(level for t, level in blocks if t < t0)
    floor = quiet[len(quiet) // 2] if quiet else 1.0
    threshold = max(floor * 15, 30.0)
    print(f'Mikrofon: {len(blocks)} Blöcke, Grundrauschen {floor:.1f}, Schwelle {threshold:.1f}')
    lags = []
    k = 1
    while k * args.every < args.seconds:
        sent = t0 + k * args.every
        window = [(t, level) for t, level in blocks if sent < t < sent + args.every - 0.2]
        heard = next((t for t, level in window if level > threshold), None)
        peak_t, peak = max(window, key=lambda b: b[1], default=(sent, 0))
        if heard is None:
            print(f'Piep {k:2d}: nicht gehört (Spitze {peak:.0f} nach {peak_t - sent:.2f} s)')
        else:
            lag = heard - sent
            lags.append(lag)
            print(f'Piep {k:2d}: {lag:.2f} s (Spitze {peak:.0f} nach {peak_t - sent:.2f} s)')
        k += 1
    if lags:
        lags.sort()
        print(f'Ergebnis {args.via}: Median {lags[len(lags) // 2]:.2f} s, '
              f'min {lags[0]:.2f} s, max {lags[-1]:.2f} s, {len(lags)} gehört')


if __name__ == '__main__':
    main()
