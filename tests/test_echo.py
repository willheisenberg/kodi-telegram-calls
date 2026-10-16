import numpy as np
import pytest

import echo

RATE = 48000


def speechlike(seconds, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(RATE * seconds) / RATE
    burst = np.sin(2 * np.pi * 0.7 * t) > 0
    signal = np.sin(2 * np.pi * 300 * t) * np.sin(2 * np.pi * 3 * t) + 0.5 * rng.standard_normal(t.size) * burst
    return (signal * 6000).astype(np.int16)


def damping_db(canceller, far, mic):
    """Schickt far als Referenz und mic durch process(); Dämpfung der letzten 3 s in dB."""
    out = []
    for i in range(0, far.size, echo.FRAME):
        canceller.add_reference(far[i:i + echo.FRAME].tobytes())
        out.append(np.frombuffer(canceller.process(mic[i:i + echo.FRAME].tobytes()), np.int16))
    result = np.concatenate(out).astype(np.float64)[-3 * RATE:]
    source = mic.astype(np.float64)[-3 * RATE:]
    return 10 * np.log10((np.mean(source ** 2) + 1e-9) / (np.mean(result ** 2) + 1e-9))


def echo_of(far, delay_ms, gain=0.5):
    delay = delay_ms * RATE // 1000
    mic = np.zeros_like(far)
    mic[delay:] = (far[:-delay] * gain).astype(np.int16)
    return mic


def test_webrtc_entfernt_echo_bei_bekannter_verzoegerung():
    far = speechlike(10)
    assert damping_db(echo.EchoCanceller(300), far, echo_of(far, 300)) > 30


def test_webrtc_vertraegt_zu_kurz_geschaetzte_verzoegerung():
    far = speechlike(10)
    assert damping_db(echo.EchoCanceller(150), far, echo_of(far, 300)) > 30


def test_ohne_referenz_bleibt_das_echo():
    far = speechlike(10)
    silent = np.zeros_like(far)
    canceller = echo.EchoCanceller(300)
    out = []
    mic = echo_of(far, 300)
    for i in range(0, far.size, echo.FRAME):
        canceller.add_reference(silent[i:i + echo.FRAME].tobytes())
        out.append(np.frombuffer(canceller.process(mic[i:i + echo.FRAME].tobytes()), np.int16))
    result = np.concatenate(out).astype(np.float64)[-3 * RATE:]
    source = mic.astype(np.float64)[-3 * RATE:]
    assert 10 * np.log10(np.mean(source ** 2) / np.mean(result ** 2)) < 15


def test_falsche_blocklaenge_wird_abgewiesen():
    with pytest.raises(ValueError):
        echo.PassThrough().process(bytes(100))


def test_stereo_zu_mono_mittelt():
    stereo = np.array([100, 300, -50, 50], dtype=np.int16).tobytes()
    assert np.frombuffer(echo.stereo_to_mono(stereo), np.int16).tolist() == [200, 0]


def test_ducker_daempft_waehrend_und_nach_der_gegenseite():
    ducker = echo.Ducker(delay_ms=100, threshold=500, gain=0.1, tail_ms=0)
    loud = (np.ones(echo.FRAME) * 3000).astype(np.int16).tobytes()
    quiet = bytes(echo.FRAME_BYTES)
    mic = (np.ones(echo.FRAME) * 1000).astype(np.int16).tobytes()
    assert ducker.process(mic) == mic
    ducker.add_reference(loud)
    for _ in range(10):  # 100 ms Nachlauf
        assert np.frombuffer(ducker.process(mic), np.int16)[0] == 100
    ducker.add_reference(quiet)
    assert ducker.process(mic) == mic


def test_make_echo_waehlt_verfahren():
    assert isinstance(echo.make_echo('webrtc', 300), echo.EchoCanceller)
    assert isinstance(echo.make_echo('daempfen', 300), echo.Ducker)
    assert isinstance(echo.make_echo('aus', 300), echo.PassThrough)
