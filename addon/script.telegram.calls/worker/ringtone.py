"""Klingelton für eingehende Anrufe: Doppelton 0,8 s, Pause 2,2 s; s16le, 48 kHz, Stereo."""
import asyncio
import time

import numpy as np

RATE = 48000
TONE_S = 0.8
CYCLE_S = 3.0
CHUNK_S = 0.1
CHUNK_BYTES = int(RATE * CHUNK_S) * 4


def ring_cycle():
    n_tone = int(RATE * TONE_S)
    t = np.arange(n_tone) / RATE
    wave = 0.25 * (np.sin(2 * np.pi * 523.25 * t) + np.sin(2 * np.pi * 659.25 * t)) / 2
    fade = np.minimum(1.0, np.minimum(t, TONE_S - t) / 0.02)  # 20 ms ein- und ausblenden gegen Knacken
    mono = np.zeros(int(RATE * CYCLE_S))
    mono[:n_tone] = wave * fade
    return np.repeat((mono * 32767).astype(np.int16), 2).tobytes()


class RingTone:
    def __init__(self):
        self._cycle = ring_cycle()

    async def run(self, sink):
        """Schreibt den Ton in Echtzeit in die Ausgabe, bis die Aufgabe abgebrochen wird."""
        start, pos, n = time.monotonic(), 0, 0
        while True:
            sink.write(self._cycle[pos:pos + CHUNK_BYTES])
            pos = (pos + CHUNK_BYTES) % len(self._cycle)
            n += 1
            await asyncio.sleep(max(0.0, start + n * CHUNK_S - time.monotonic()))
