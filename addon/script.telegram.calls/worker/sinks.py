"""Ausgabe des Anruftons: direkt per ALSA auf HDMI oder über Kodi (RTP + SDP).

Beide Ausgaben haben dieselbe Schnittstelle: start(), write(pcm), stop() und
delay_ms (Verzögerung bis zum Schall am Mikrofon, gemessen in Task 2,
docs/messtest-teilprojekt-2.md). pcm ist s16le, 48 kHz, Stereo.
"""
import logging
import subprocess
import time

from rtp import RtpSender, sdp

log = logging.getLogger('worker.sinks')

HDMI_DEVICE = 'hdmi:CARD=vc4hdmi0,DEV=0'
HDMI_STATUS = '/proc/asound/vc4hdmi0/pcm0p/sub0/status'
RTP_PORT = 23533  # Soloist nutzt 23433
ALSA_DELAY_MS = 90
KODI_DELAY_MS = 450
STARTUP_CHECK_S = 0.2


class SinkError(RuntimeError):
    pass


def hdmi_busy(status_path=HDMI_STATUS):
    """True, wenn jemand (meist Kodi) den HDMI-Ausgang offen hält oder der Zustand unklar ist."""
    try:
        with open(status_path) as f:
            return f.read().strip() != 'closed'
    except OSError:
        return True


class AlsaSink:
    delay_ms = ALSA_DELAY_MS

    def __init__(self, device=HDMI_DEVICE, command=None):
        self._command = command or ['aplay', '-q', '-D', device, '-f', 'S16_LE', '-r', '48000', '-c', '2',
                                    '-t', 'raw', '--buffer-time=60000']
        self._proc = None

    def start(self):
        self._proc = subprocess.Popen(self._command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(STARTUP_CHECK_S)
        if self._proc.poll() is not None:
            raise SinkError(f'aplay endete sofort: {self._proc.stderr.read().decode(errors="replace").strip()}')

    def write(self, pcm):
        try:
            self._proc.stdin.write(pcm)
            self._proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            raise SinkError('aplay ist beendet') from None

    def stop(self):
        if self._proc is None:
            return
        try:
            self._proc.stdin.close()
        except OSError:
            pass
        self._proc.terminate()
        try:
            self._proc.wait(2)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
        self._proc = None


class KodiSink:
    """Sendet per RTP; das Add-on spielt die SDP-Datei mit xbmc.Player ab (Ereignis play_kodi)."""

    delay_ms = KODI_DELAY_MS

    def __init__(self, sdp_path, emit, port=RTP_PORT):
        self._sdp_path = sdp_path
        self._emit = emit
        self._port = port
        self._rtp = None

    def start(self):
        with open(self._sdp_path, 'w') as f:
            f.write(sdp(self._port))
        self._rtp = RtpSender(self._port)
        self._emit('play_kodi', sdp_pfad=self._sdp_path)

    def write(self, pcm):
        self._rtp.send(pcm)

    def stop(self):
        if self._rtp is None:
            return
        self._emit('stop_kodi')
        self._rtp.close()
        self._rtp = None


def open_sink(prefer_direct, sdp_path, emit, busy=hdmi_busy, alsa_command=None):
    """Startet die direkte Ausgabe, wenn gewünscht und möglich, sonst die über Kodi."""
    if prefer_direct and not busy():
        sink = AlsaSink(command=alsa_command)
        try:
            sink.start()
            log.info('Ausgabe direkt per ALSA')
            return sink
        except (OSError, SinkError) as e:
            log.warning('Direkte Ausgabe nicht möglich, nehme Kodi: %s', e)
            sink.stop()
    sink = KodiSink(sdp_path, emit)
    sink.start()
    log.info('Ausgabe über Kodi')
    return sink
