"""Echounterdrückung: Das Webcam-Mikrofon hört die Boxen, die Gegenseite soll sich nicht selbst hören.

Alle Verfahren haben dieselbe Schnittstelle: add_reference(mono) bekommt den
Ton der Gegenseite, process(mic) einen 10-ms-Block vom Mikrofon und gibt den
bereinigten Block zurück. Ton: s16le, 48 kHz, Mono.

WebRTC (LiveKit) verkraftet eine zu früh kommende Referenz (ausprobiert:
300 ms), aber keine zu späte (100 ms zu spät: nur noch 12 dB Dämpfung). Die
Referenz wird deshalb um die Verzögerung der Ausgabe abzüglich MARGIN_MS
verzögert.
"""
import threading

import numpy as np

RATE = 48000
FRAME = RATE // 100
FRAME_BYTES = FRAME * 2
MARGIN_MS = 150
MAX_EXTRA_MS = 200  # so viel darf sich die Referenz über die Vorgabe hinaus stauen


def stereo_to_mono(pcm):
    samples = np.frombuffer(pcm, dtype=np.int16).reshape(-1, 2).astype(np.int32)
    return ((samples[:, 0] + samples[:, 1]) // 2).astype(np.int16).tobytes()


class _ReferenceDelay:
    """Verzögert die Referenz; wird vom Netz-Thread gefüllt und vom Mikrofon-Thread geleert."""

    def __init__(self, delay_ms):
        self._lock = threading.Lock()
        self._buf = bytearray(max(0, delay_ms) * RATE // 1000 * 2)
        self._max = len(self._buf) + MAX_EXTRA_MS * RATE // 1000 * 2

    def push(self, mono):
        with self._lock:
            self._buf += mono
            if len(self._buf) > self._max:
                del self._buf[:len(self._buf) - self._max]

    def pop(self):
        with self._lock:
            out = bytes(self._buf[:FRAME_BYTES])
            del self._buf[:FRAME_BYTES]
        return out.ljust(FRAME_BYTES, b'\0')


def _check(mic):
    if len(mic) != FRAME_BYTES:
        raise ValueError(f'Mikrofonblock muss {FRAME_BYTES} Byte haben, nicht {len(mic)}')


class EchoCanceller:
    def __init__(self, delay_ms, margin_ms=MARGIN_MS, apm=None):
        from livekit.rtc import AudioFrame, AudioProcessingModule

        self._frame = AudioFrame
        self._apm = apm or AudioProcessingModule(echo_cancellation=True, noise_suppression=True,
                                                 high_pass_filter=True)
        self._apm.set_stream_delay_ms(margin_ms)
        self._ref = _ReferenceDelay(delay_ms - margin_ms)

    def add_reference(self, mono):
        self._ref.push(mono)

    def process(self, mic):
        _check(mic)
        self._apm.process_reverse_stream(self._frame(self._ref.pop(), RATE, 1, FRAME))
        frame = self._frame(mic, RATE, 1, FRAME)
        self._apm.process_stream(frame)
        return bytes(frame.data)


class Ducker:
    """Rückfallebene: dämpft das Mikrofon, solange die Gegenseite spricht, samt Nachlauf."""

    def __init__(self, delay_ms, threshold=500, gain=0.1, tail_ms=300):
        self._threshold = threshold
        self._gain = gain
        self._hold_frames = (delay_ms + tail_ms) // 10
        self._lock = threading.Lock()
        self._hold = 0

    def add_reference(self, mono):
        samples = np.frombuffer(mono, dtype=np.int16).astype(np.float64)
        if samples.size and np.sqrt(np.mean(samples ** 2)) > self._threshold:
            with self._lock:
                self._hold = self._hold_frames

    def process(self, mic):
        _check(mic)
        with self._lock:
            active = self._hold > 0
            self._hold = max(0, self._hold - 1)
        if not active:
            return mic
        return (np.frombuffer(mic, dtype=np.int16) * self._gain).astype(np.int16).tobytes()


class PassThrough:
    def __init__(self, delay_ms=0):
        pass

    def add_reference(self, mono):
        pass

    def process(self, mic):
        _check(mic)
        return mic


def make_echo(mode, delay_ms):
    """mode: 'webrtc' | 'daempfen' | 'aus' (Einstellung echo des Add-ons)."""
    if mode == 'webrtc':
        return EchoCanceller(delay_ms)
    if mode == 'daempfen':
        return Ducker(delay_ms)
    return PassThrough()
