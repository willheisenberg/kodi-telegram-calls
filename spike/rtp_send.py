#!/usr/bin/env python3
"""Liest PCM (s16le, 48 kHz, Stereo) von stdin und sendet es als RTP an Kodi.

Gesendet wird L16 mit 48 kHz und dem dynamischen Payload-Typ 96; Kodi
erfährt das Format aus einer SDP-Datei (siehe sdp()). 48 kHz statt der
statischen 44,1 kHz (Payload-Typ 10), weil 44,1 kHz über HDMI zum Denon
nach dessen Einschalten piepsig klingt und knistert.
Aufruf: rtp_send.py <port> [rohdaten-datei]
"""
import array
import random
import socket
import struct
import sys
import time

RATE = 48000
CHANNELS = 2
PAYLOAD_TYPE = 96
SAMPLES_PER_PACKET = 240  # 5 ms, 960 Byte Nutzlast, bleibt unter Soloists MTU von 1280
BYTES_PER_PACKET = SAMPLES_PER_PACKET * CHANNELS * 2
STATS_INTERVAL = 10


def sdp(port):
    """SDP-Beschreibung des Streams, die Kodi (ffmpeg) zum Abspielen braucht."""
    return (
        'v=0\r\n'
        'o=- 0 0 IN IP4 127.0.0.1\r\n'
        's=Telegram-Anruf\r\n'
        'c=IN IP4 127.0.0.1\r\n'
        't=0 0\r\n'
        f'm=audio {port} RTP/AVP {PAYLOAD_TYPE}\r\n'
        f'a=rtpmap:{PAYLOAD_TYPE} L16/{RATE}/{CHANNELS}\r\n'
    )


def main():
    port = int(sys.argv[1])
    # Diagnose: Rohdaten von ntgcalls mitschreiben (rtp_send.py <port> <datei>)
    dump = open(sys.argv[2], 'wb') if len(sys.argv) > 2 else None
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ssrc = random.getrandbits(32)
    sequence = random.getrandbits(16)
    timestamp = random.getrandbits(32)
    stdin = sys.stdin.buffer
    stats_start, stats_bytes = time.monotonic(), 0
    while True:
        chunk = stdin.read(BYTES_PER_PACKET)
        if len(chunk) < BYTES_PER_PACKET:
            return
        if dump:
            dump.write(chunk)
        stats_bytes += len(chunk)
        elapsed = time.monotonic() - stats_start
        if elapsed >= STATS_INTERVAL:
            # 100 % = ntgcalls liefert genau Echtzeit
            rate = stats_bytes / elapsed / (RATE * CHANNELS * 2)
            print(f'rtp_send: Eingang {100 * rate:.1f} % Echtzeit', file=sys.stderr, flush=True)
            stats_start, stats_bytes = time.monotonic(), 0
        samples = array.array('h', chunk)
        samples.byteswap()  # RTP verlangt L16 in Netzwerk-Byte-Reihenfolge
        header = struct.pack('!BBHII', 0x80, PAYLOAD_TYPE, sequence, timestamp, ssrc)
        sock.sendto(header + samples.tobytes(), ('127.0.0.1', port))
        sequence = (sequence + 1) & 0xFFFF
        timestamp = (timestamp + SAMPLES_PER_PACKET) & 0xFFFFFFFF


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        pass  # Strg+C erreicht auch diesen Kindprozess
