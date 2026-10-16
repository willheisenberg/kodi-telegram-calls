"""Webcam-Mikrofon per ALSA: 10-ms-Blöcke (s16le, 48 kHz, Mono) in einem eigenen Thread.

Läuft nur während eines Gesprächs. Der Thread liest ohne Pause, deshalb staut
sich in ALSA nichts; was vor dem Verbinden ankommt, verwirft CallManager.
"""
import logging
import re
import subprocess
import threading

log = logging.getLogger('worker.mic')

RATE = 48000
FRAME_BYTES = RATE // 100 * 2
DEVICE = 'plughw:CARD=Webcam,DEV=0'


class MicCapture:
    def __init__(self, on_frame, device=DEVICE, command=None):
        self._on_frame = on_frame
        self._command = command or ['aplay', '-C', '-q', '-D', device, '-f', 'S16_LE', '-r', str(RATE),
                                    '-c', '1', '-t', 'raw', '--buffer-time=40000']
        self._proc = None
        self._thread = None

    def start(self):
        self._proc = subprocess.Popen(self._command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._thread = threading.Thread(target=self._read, name='mikrofon', daemon=True)
        self._thread.start()

    def _read(self):
        stream = self._proc.stdout
        while True:
            chunk = stream.read(FRAME_BYTES)
            if len(chunk) < FRAME_BYTES:
                return
            try:
                self._on_frame(chunk)
            except Exception:
                log.exception('Mikrofonblock nicht verarbeitet')

    def stop(self):
        if self._proc is None:
            return
        self._proc.terminate()
        try:
            self._proc.wait(2)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
        if self._thread is not None:
            self._thread.join(2)
        self._proc = None


def card_of(device):
    """'plughw:CARD=Webcam,DEV=0' -> 'Webcam'."""
    match = re.search(r'CARD=([^,]+)', device)
    return match.group(1) if match else device


def mic_volume(card, run=subprocess.run):
    """Wert des Reglers 'Mic Capture Volume' oder None, wenn er sich nicht lesen lässt."""
    try:
        result = run(['amixer', '-c', card, 'cget', 'name=Mic Capture Volume'],
                     capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r': values=(\d+)', result.stdout)
    return int(match.group(1)) if match else None


def mic_ok(card, cards_path='/proc/asound/cards', run=subprocess.run):
    """Karte vorhanden und Regler nicht auf 0 (ein fehlender Regler zählt als in Ordnung)."""
    try:
        with open(cards_path) as f:
            cards = f.read()
    except OSError:
        return False
    if f'[{card}' not in cards:
        return False
    return mic_volume(card, run) != 0
