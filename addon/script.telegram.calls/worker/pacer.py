"""Gibt den Ton im festen 10-ms-Takt an die Ausgabe, mit Stille, wenn nichts da ist.

Kodi spielt die SDP-Datei als Datei, nicht als Live-Strom (live sind für Kodi nur
udp:// und rtp://). Ist seine Paketwarteschlange ~0,1 s leer, meldet es "stream
stalled", füllt danach seinen Puffer ganz und hängt das ganze Gespräch ~7 s
hinterher (Messung 2026-10-28). Telegram liefert aber in Schüben, und py-tgcalls
blockiert beim Annehmen den Anrufprozess ~1 s.

Deshalb schreibt ein eigener Thread alle 10 ms genau 10 ms: aus der Warteschlange,
die write() füllt, sonst Stille. Die Warteschlange fasst höchstens MAX_QUEUE_S;
was darüber hinausgeht, verwirft sie vorne, damit die Verzögerung nicht wächst.
pcm ist s16le, 48 kHz, Stereo.
"""
import logging
import threading
import time

from sinks import SinkError

log = logging.getLogger('worker.pacer')

BYTES_PER_S = 48000 * 4
CHUNK_BYTES = BYTES_PER_S // 100  # 10 ms
MAX_QUEUE_S = 0.3
MAX_QUEUE_BYTES = int(MAX_QUEUE_S * BYTES_PER_S) // 4 * 4
MAX_CATCH_UP = 50  # nach einer langen Thread-Pause höchstens 0,5 s nachliefern


class Pacer:
    def __init__(self, sink, clock=time.monotonic, on_audio=None, on_error=None):
        """on_audio sieht jeden Block, der rausgeht (Referenz der Echounterdrückung); on_error einen SinkError."""
        self._sink = sink
        self._clock = clock
        self._on_audio = on_audio
        self._on_error = on_error
        self._lock = threading.Lock()
        self._queue = bytearray()
        self._start = clock()
        self._sent = 0  # Blöcke seit dem Start
        self._dropping = False
        self._stop = threading.Event()
        self._thread = None

    def write(self, pcm):
        with self._lock:
            self._queue += pcm
            excess = len(self._queue) - MAX_QUEUE_BYTES
            if excess > 0:
                del self._queue[:(excess + 3) // 4 * 4]
                if not self._dropping:
                    log.info('Ton der Gegenseite staut sich, verwerfe das Älteste')
                    self._dropping = True
            else:
                self._dropping = False

    def queued_s(self):
        with self._lock:
            return len(self._queue) / BYTES_PER_S

    def pump(self):
        """Schreibt alle Blöcke, die bis jetzt fällig sind."""
        due = int((self._clock() - self._start) * 100 + 1e-6) - self._sent
        if due > MAX_CATCH_UP:
            self._sent += due - MAX_CATCH_UP
            due = MAX_CATCH_UP
        for _ in range(due):
            with self._lock:
                chunk = bytes(self._queue[:CHUNK_BYTES])
                del self._queue[:CHUNK_BYTES]
            if len(chunk) < CHUNK_BYTES:
                chunk += bytes(CHUNK_BYTES - len(chunk))
            self._sink.write(chunk)
            self._sent += 1
            if self._on_audio is not None:
                self._on_audio(chunk)

    def start(self):
        self._thread = threading.Thread(target=self._run, name='taktgeber', daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                self.pump()
            except SinkError as e:
                if self._on_error is not None:
                    self._on_error(e)
                return
            except Exception:
                log.exception('Taktgeber')
                return
            next_at = self._start + (self._sent + 1) / 100
            self._stop.wait(max(0.001, next_at - self._clock()))

    def stop(self):
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(1)
