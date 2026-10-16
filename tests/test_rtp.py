import socket
import struct

import rtp


def test_sdp_beschreibt_48khz_stereo():
    text = rtp.sdp(23533)
    assert 'm=audio 23533 RTP/AVP 96' in text
    assert 'a=rtpmap:96 L16/48000/2' in text


def test_pakete_mit_fortlaufendem_kopf_und_netzwerk_byte_reihenfolge():
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(('127.0.0.1', 0))
    receiver.settimeout(2)
    sender = rtp.RtpSender(receiver.getsockname()[1])
    pcm = struct.pack('<h', 0x0102) + bytes(4 * rtp.BYTES_PER_PACKET)  # 4 Pakete + 2 Byte Rest
    sender.send(pcm)
    packets = [receiver.recv(2048) for _ in range(4)]
    heads = [struct.unpack('!BBHII', p[:12]) for p in packets]
    assert all(h[0] == 0x80 and h[1] == 96 for h in heads)
    assert [(h[2] - heads[0][2]) & 0xFFFF for h in heads] == [0, 1, 2, 3]
    assert [(h[3] - heads[0][3]) & 0xFFFFFFFF for h in heads] == [0, 240, 480, 720]
    assert all(len(p) == 12 + rtp.BYTES_PER_PACKET for p in packets)
    assert packets[0][12:14] == b'\x01\x02'
    sender.send(bytes(rtp.BYTES_PER_PACKET - 2))  # füllt den Rest zu einem fünften Paket auf
    assert len(receiver.recv(2048)) == 12 + rtp.BYTES_PER_PACKET
    sender.close()
    receiver.close()
