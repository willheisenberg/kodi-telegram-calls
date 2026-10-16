#!/usr/bin/env python3
"""Erzeugt die PNG-Grafiken des Add-ons (ohne PIL). Aufruf: tools/make_media.py <media-ordner>"""
import math
import os
import struct
import sys
import zlib


def png(size, pixel):
    """pixel(x, y) -> (r, g, b, a); quadratisches Bild."""
    rows = []
    for y in range(size):
        row = bytearray(b'\0')
        for x in range(size):
            row += bytes(pixel(x, y))
        rows.append(bytes(row))

    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF))

    header = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(b''.join(rows)))
            + chunk(b'IEND', b''))


def circle(size, color, plus=None):
    r = size / 2

    def pixel(x, y):
        d = math.hypot(x + 0.5 - r, y + 0.5 - r)
        alpha = max(0.0, min(1.0, r - d))  # weicher Rand
        if plus and (abs(x + 0.5 - r) < size * 0.04 or abs(y + 0.5 - r) < size * 0.04) \
                and abs(x + 0.5 - r) < size * 0.22 and abs(y + 0.5 - r) < size * 0.22:
            return (*plus, int(255 * alpha))
        return (*color, int(255 * alpha))
    return png(size, pixel)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    files = {
        'tgc-white.png': png(8, lambda x, y: (255, 255, 255, 255)),
        'tgc-kreis.png': circle(256, (255, 255, 255)),
        'tgc-avatar.png': circle(256, (84, 110, 122)),
        'tgc-alle.png': circle(256, (38, 50, 56), plus=(255, 255, 255)),
    }
    for name, data in files.items():
        with open(os.path.join(out, name), 'wb') as f:
            f.write(data)
        print(name, len(data), 'Byte')


if __name__ == '__main__':
    main()
