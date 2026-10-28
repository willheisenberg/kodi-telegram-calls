import subprocess
import sys
import threading

import mic

AMIXER_OUTPUT = """numid=3,iface=MIXER,name='Mic Capture Volume'
  ; type=INTEGER,access=rw---R--,values=1,min=0,max=15,step=0
  : values=%d
"""


def fake_amixer(value):
    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout=AMIXER_OUTPUT % value, stderr='')
    return run


def test_liefert_bloecke_zu_10_ms():
    frames = []
    done = threading.Event()

    def on_frame(chunk):
        frames.append(chunk)
        if len(frames) == 4:
            done.set()

    command = [sys.executable, '-c', 'import sys; sys.stdout.buffer.write(bytes(960 * 4 + 100))']
    capture = mic.MicCapture(on_frame, command=command)
    capture.start()
    assert done.wait(5)
    capture.stop()
    assert [len(f) for f in frames] == [960] * 4


def test_fehler_im_verarbeiter_beendet_das_lesen_nicht():
    frames = []

    def on_frame(chunk):
        frames.append(chunk)
        raise RuntimeError('kaputt')

    command = [sys.executable, '-c', 'import sys; sys.stdout.buffer.write(bytes(960 * 3))']
    capture = mic.MicCapture(on_frame, command=command)
    capture.start()
    capture._thread.join(5)
    capture.stop()
    assert len(frames) == 3


def test_karte_aus_geraetename():
    assert mic.card_of('plughw:CARD=Webcam,DEV=0') == 'Webcam'
    assert mic.card_of('default') == 'default'


def test_reglerwert():
    assert mic.mic_volume('Webcam', run=fake_amixer(10)) == 10


def test_mic_ok(tmp_path):
    cards = tmp_path / 'cards'
    cards.write_text(' 0 [vc4hdmi0       ]: vc4-hdmi\n 2 [Webcam         ]: USB-Audio - C922\n')
    assert mic.mic_ok('Webcam', str(cards), run=fake_amixer(10)) is True
    assert mic.mic_ok('Webcam', str(cards), run=fake_amixer(0)) is False
    cards.write_text(' 0 [vc4hdmi0       ]: vc4-hdmi\n')
    assert mic.mic_ok('Webcam', str(cards), run=fake_amixer(10)) is False


class StatefulAmixer:
    """Merkt sich den Reglerwert; cset verstellt ihn, wenn es klappen soll."""

    def __init__(self, value, settable=True):
        self.value, self.settable, self.sets = value, settable, []

    def __call__(self, args, **kwargs):
        if 'cset' in args:
            self.sets.append(args[-1])
            if self.settable:
                self.value = int(args[-1])
        return subprocess.CompletedProcess(args, 0, stdout=AMIXER_OUTPUT % self.value, stderr='')


def test_regler_auf_null_wird_auf_zehn_gestellt(tmp_path):
    # Die C922 setzt den Regler beim Wieder-Anstecken auf 0; dann hört die Gegenseite nichts.
    cards = tmp_path / 'cards'
    cards.write_text(' 2 [Webcam         ]: USB-Audio - C922\n')
    amixer = StatefulAmixer(0)
    assert mic.mic_ok('Webcam', str(cards), run=amixer) is True
    assert amixer.sets == ['10'] and amixer.value == 10


def test_eingestellter_regler_bleibt_unberuehrt(tmp_path):
    cards = tmp_path / 'cards'
    cards.write_text(' 2 [Webcam         ]: USB-Audio - C922\n')
    amixer = StatefulAmixer(4)
    assert mic.mic_ok('Webcam', str(cards), run=amixer) is True
    assert amixer.sets == []


def test_regler_laesst_sich_nicht_stellen(tmp_path):
    cards = tmp_path / 'cards'
    cards.write_text(' 2 [Webcam         ]: USB-Audio - C922\n')
    assert mic.mic_ok('Webcam', str(cards), run=StatefulAmixer(0, settable=False)) is False
