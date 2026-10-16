#!/usr/bin/env python3
"""Messtest: spielt 30 s einen leisen Ton direkt per ALSA und zeigt danach neue Audio-Zeilen im Kodi-Log.

Während der 30 s in Kodi mit der Fernbedienung navigieren (Bediengeräusche auslösen).
Aufruf: kollision.py [alsa-gerät]
"""
import math
import os
import subprocess
import sys

LOG = '/storage/.kodi/temp/kodi.log'
device = sys.argv[1] if len(sys.argv) > 1 else 'hdmi:CARD=vc4hdmi0,DEV=0'
rate = 48000
frame = bytearray()
for i in range(rate):
    v = int(1500 * math.sin(2 * math.pi * 440 * i / rate))
    frame += v.to_bytes(2, 'little', signed=True) * 2
start = os.path.getsize(LOG)
print('Ton läuft 30 s. Jetzt in Kodi navigieren.', flush=True)
p = subprocess.run(['aplay', '-q', '-D', device, '-f', 'S16_LE', '-r', str(rate), '-c', '2', '-t', 'raw'],
                   input=bytes(frame) * 30, capture_output=True)
print('aplay:', 'OK' if p.returncode == 0 else p.stderr.decode().strip())
with open(LOG, errors='replace') as f:
    f.seek(start)
    lines = [line.rstrip() for line in f if any(k in line for k in ('ALSA', 'ActiveAE', 'CAESink', 'AESink'))]
print(f'{len(lines)} neue Audio-Zeilen im Kodi-Log:')
print('\n'.join(lines[-40:]))
