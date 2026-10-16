import asyncio

import numpy as np

import ringtone


def test_zyklus_ton_dann_stille():
    samples = np.frombuffer(ringtone.ring_cycle(), np.int16).reshape(-1, 2)
    assert len(samples) == 3 * 48000
    assert np.abs(samples[:38400]).max() > 3000
    assert np.abs(samples[39000:]).max() == 0


class Sink:
    def __init__(self):
        self.chunks = []

    def write(self, pcm):
        self.chunks.append(pcm)


def test_laeuft_in_echtzeit_bis_zum_abbruch():
    sink = Sink()

    async def run():
        task = asyncio.create_task(ringtone.RingTone().run(sink))
        await asyncio.sleep(0.25)
        task.cancel()

    asyncio.run(run())
    assert 2 <= len(sink.chunks) <= 4
    assert all(len(c) == ringtone.CHUNK_BYTES for c in sink.chunks)
