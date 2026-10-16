"""Baut für CallManager Ausgabe, Echounterdrückung, Mikrofon und Klingelton nach den Einstellungen."""
import os

import echo
import mic
import ringtone
import sinks


class AudioFactory:
    def __init__(self, init, data_dir, emit):
        self._direct = bool(init.get('direkt', False))
        self._echo_mode = init.get('echo', 'webrtc')
        self._mic_device = init.get('mikrofon') or mic.DEVICE
        self._sdp_path = os.path.join(data_dir, 'anruf.sdp')
        self._emit = emit

    def open_sink(self):
        return sinks.open_sink(self._direct, self._sdp_path, self._emit)

    def make_echo(self, delay_ms):
        return echo.make_echo(self._echo_mode, delay_ms)

    def make_mic(self, on_frame):
        return mic.MicCapture(on_frame, self._mic_device)

    def ringtone(self):
        return ringtone.RingTone()
