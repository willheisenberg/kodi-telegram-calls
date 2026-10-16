#!/usr/bin/env python3
"""Messtest: zeigt jede Sekunde, ob Kodi den HDMI-Ausgang belegt. Aufruf: geraet.py [sekunden]"""
import sys
import time

STATUS = '/proc/asound/vc4hdmi0/pcm0p/sub0/status'
seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 90
for _ in range(seconds):
    try:
        first = open(STATUS).readline().strip()
    except OSError as e:
        first = f'nicht lesbar: {e}'
    print(f'{time.strftime("%H:%M:%S")} {first}', flush=True)
    time.sleep(1)
