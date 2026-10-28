import time

from pacer import BYTES_PER_S, CHUNK_BYTES, MAX_QUEUE_S, Pacer

FRAME = b'\x01' * CHUNK_BYTES  # 10 ms


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


class Sink:
    def __init__(self):
        self.chunks, self.times = [], []

    def write(self, pcm):
        self.chunks.append(pcm)
        self.times.append(time.monotonic())


def setup():
    clock, sink, audio = Clock(), Sink(), []
    return clock, sink, audio, Pacer(sink, clock=clock, on_audio=audio.append)


def test_ohne_ton_kommt_stille_im_takt():
    clock, sink, audio, pacer = setup()
    clock.now += 0.05
    pacer.pump()
    assert sink.chunks == [bytes(CHUNK_BYTES)] * 5


def test_ton_der_gegenseite_geht_in_reihenfolge_raus():
    clock, sink, audio, pacer = setup()
    pacer.write(FRAME)
    pacer.write(b'\x02' * CHUNK_BYTES)
    clock.now += 0.03
    pacer.pump()
    assert sink.chunks == [FRAME, b'\x02' * CHUNK_BYTES, bytes(CHUNK_BYTES)]


def test_teilblock_wird_mit_stille_aufgefuellt():
    clock, sink, audio, pacer = setup()
    pacer.write(b'\x01' * 100)
    clock.now += 0.01
    pacer.pump()
    assert sink.chunks == [b'\x01' * 100 + bytes(CHUNK_BYTES - 100)]


def test_grosse_bloecke_werden_ueber_mehrere_takte_verteilt():
    # Der Klingelton schreibt 100-ms-Blöcke; Kodi soll trotzdem alle 10 ms Daten bekommen.
    clock, sink, audio, pacer = setup()
    pacer.write(b'\x01' * (10 * CHUNK_BYTES))
    clock.now += 0.01
    pacer.pump()
    assert sink.chunks == [FRAME]


def test_volle_warteschlange_verwirft_das_aelteste():
    clock, sink, audio, pacer = setup()
    n = int(MAX_QUEUE_S * 100) + 10
    for i in range(n):
        pacer.write(bytes([i % 250 + 1]) * CHUNK_BYTES)
    clock.now += 0.01
    pacer.pump()
    assert sink.chunks[0][0] == 10 % 250 + 1
    assert pacer.queued_s() <= MAX_QUEUE_S


def test_on_audio_sieht_alles_was_rausgeht():
    clock, sink, audio, pacer = setup()
    pacer.write(FRAME)
    clock.now += 0.02
    pacer.pump()
    assert audio == sink.chunks


def test_eigener_thread_haelt_den_takt_wenn_der_aufrufer_blockiert():
    # Kodi meldet "stream stalled", sobald seine Paketwarteschlange ~0,1 s leer ist, und puffert danach
    # ~7 s nach (Messung 2026-10-28). py-tgcalls blockiert beim Annehmen den Anrufprozess ~1 s.
    sink = Sink()
    pacer = Pacer(sink)
    pacer.start()
    time.sleep(0.5)  # blockierter Aufrufer
    pacer.stop()
    count = len(sink.chunks)
    time.sleep(0.1)
    assert count >= 40
    assert max(b - a for a, b in zip(sink.times, sink.times[1:], strict=False)) < 0.05
    assert len(sink.chunks) == count
    assert sum(map(len, sink.chunks)) == count * CHUNK_BYTES
    assert BYTES_PER_S == 100 * CHUNK_BYTES


def test_ausfall_der_ausgabe_wird_gemeldet():
    from sinks import SinkError

    class Broken:
        def write(self, pcm):
            raise SinkError('weg')

    errors = []
    pacer = Pacer(Broken(), on_error=errors.append)
    pacer.start()
    time.sleep(0.1)
    pacer.stop()
    assert len(errors) == 1 and isinstance(errors[0], SinkError)
