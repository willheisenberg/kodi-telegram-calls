"""RTP-Versand des Anruftons an Kodi: L16, 48 kHz, Stereo, beschrieben durch eine SDP-Datei.

Ohne SDP spielt Kodi RTP nur mit 44,1 kHz; das klingt über HDMI zum Denon nach
dessen Einschalten zu hoch und knistert (docs/ergebnisse-teilprojekt-1.md).
"""
import array
import random
import socket
import struct
import sys

RATE = 48000
CHANNELS = 2
PAYLOAD_TYPE = 96
SAMPLES_PER_PACKET = 240  # 5 ms, 960 Byte Nutzlast
BYTES_PER_PACKET = SAMPLES_PER_PACKET * CHANNELS * 2


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


class RtpSender:
    def __init__(self, port, address='127.0.0.1'):
        self._target = (address, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._ssrc = random.getrandbits(32)
        self._sequence = random.getrandbits(16)
        self._timestamp = random.getrandbits(32)
        self._pending = bytearray()

    def send(self, pcm):
        """pcm: s16le, 48 kHz, Stereo, beliebige Länge; ein Rest wartet auf den nächsten Aufruf."""
        self._pending += pcm
        while len(self._pending) >= BYTES_PER_PACKET:
            samples = array.array('h', bytes(self._pending[:BYTES_PER_PACKET]))
            del self._pending[:BYTES_PER_PACKET]
            if sys.byteorder == 'little':
                samples.byteswap()  # RTP verlangt L16 in Netzwerk-Byte-Reihenfolge
            header = struct.pack('!BBHII', 0x80, PAYLOAD_TYPE, self._sequence, self._timestamp, self._ssrc)
            self._sock.sendto(header + samples.tobytes(), self._target)
            self._sequence = (self._sequence + 1) & 0xFFFF
            self._timestamp = (self._timestamp + SAMPLES_PER_PACKET) & 0xFFFFFFFF

    def close(self):
        self._sock.close()
