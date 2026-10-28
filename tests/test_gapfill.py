from gapfill import BYTES_PER_S, GapFiller

FRAME = b'\x01' * 1920  # 10 ms


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class Sink:
    def __init__(self):
        self.chunks = []

    def write(self, pcm):
        self.chunks.append(pcm)


def setup():
    clock, sink, silence = Clock(), Sink(), []
    filler = GapFiller(sink, clock=clock, on_silence=silence.append)
    return clock, sink, silence, filler


def test_ton_im_takt_braucht_keine_stille():
    clock, sink, silence, filler = setup()
    for _ in range(50):
        assert filler.write(FRAME)
        clock.now += 0.01
        filler.tick()
    assert sink.chunks == [FRAME] * 50 and silence == []


def test_kleine_schwankung_wird_nicht_gefuellt():
    clock, sink, silence, filler = setup()
    filler.write(FRAME)
    clock.now += 0.1
    filler.tick()
    assert silence == []


def test_luecke_wird_bis_jetzt_mit_stille_gefuellt():
    clock, sink, silence, filler = setup()
    filler.write(FRAME)
    clock.now += 0.51
    filler.tick()
    assert len(silence) == 1 and silence[0] == bytes(len(silence[0]))
    assert len(silence[0]) == 0.5 * BYTES_PER_S
    assert sink.chunks[-1] == silence[0]


def test_vor_dem_ersten_ton_wird_ebenfalls_gefuellt():
    clock, sink, silence, filler = setup()
    clock.now += 0.3
    filler.tick()
    assert sum(map(len, silence)) == 0.3 * BYTES_PER_S


def test_zu_weit_voraus_wird_verworfen_statt_die_verzoegerung_zu_erhoehen():
    clock, sink, silence, filler = setup()
    clock.now += 0.5
    filler.tick()                      # 0,5 s Stille, Strom steht bei "jetzt"
    written = [filler.write(FRAME) for _ in range(60)]  # verspäteter Schwall von 0,6 s
    assert written[:30] == [True] * 30
    assert written[-1] is False
    ahead = sum(map(len, sink.chunks)) / BYTES_PER_S - 0.5
    assert ahead <= 0.3 + 1e-9


def test_stille_ist_ganze_stereo_samples():
    clock, sink, silence, filler = setup()
    clock.now += 0.1234567
    filler.tick()
    assert len(silence[0]) % 4 == 0
