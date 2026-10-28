"""Hält den Ton zur Ausgabe lückenlos: Kodi puffert nach jedem Leerlauf Sekunden nach.

Kommt vom Anruf länger als GAP_S kein Ton, füllt tick() die Lücke bis jetzt mit
Stille ("stream stalled" bei Kodi, danach die ganze Gesprächsdauer Sekunden
Verzögerung). Läuft der Ton danach mehr als MAX_AHEAD_S der Uhr voraus, verwirft
write() Blöcke, statt die Verzögerung zu erhöhen. pcm ist s16le, 48 kHz, Stereo.
"""
import logging
import time

log = logging.getLogger('worker.gapfill')

BYTES_PER_S = 48000 * 4
GAP_S = 0.12
MAX_AHEAD_S = 0.3


class GapFiller:
    def __init__(self, sink, clock=time.monotonic, on_silence=None):
        self._sink = sink
        self._clock = clock
        self._on_silence = on_silence
        self._start = clock()
        self._written = 0  # Byte seit dem Start
        self._dropping = False
        self._in_gap = False

    def _lag_bytes(self):
        """Wie weit der geschriebene Strom hinter der Uhr liegt (negativ: voraus)."""
        return (self._clock() - self._start) * BYTES_PER_S - self._written

    def write(self, pcm):
        """Schreibt einen Block der Gegenseite; False, wenn er verworfen wurde."""
        if -(self._lag_bytes() - len(pcm)) > MAX_AHEAD_S * BYTES_PER_S:
            if not self._dropping:
                log.info('Ton läuft voraus, verwerfe Blöcke')
                self._dropping = True
            return False
        self._dropping = self._in_gap = False
        self._sink.write(pcm)
        self._written += len(pcm)
        return True

    def tick(self):
        lag = self._lag_bytes()
        if lag <= GAP_S * BYTES_PER_S:
            return
        silence = bytes(int(round(lag / 4)) * 4)
        if not self._in_gap:
            log.info('Lücke im Ton der Gegenseite, fülle mit Stille')
            self._in_gap = True
        self._sink.write(silence)
        self._written += len(silence)
        if self._on_silence is not None:
            self._on_silence(silence)
