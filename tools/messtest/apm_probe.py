#!/usr/bin/env python3
"""Messtest: CPU-Bedarf und Wirkung der WebRTC-Echounterdrückung auf dem Pi (künstliches Echo, 20 s)."""
import sys
import time

sys.path.insert(0, '/storage/tgcalls-addon/vendor')
import numpy as np  # noqa: E402
from livekit.rtc import AudioFrame, AudioProcessingModule  # noqa: E402

RATE, FRAME, SECONDS, DELAY = 48000, 480, 20, int(0.3 * 48000)
LEAD = int(0.15 * RATE)  # Referenz 150 ms früher, wie MARGIN_MS in worker/echo.py
rng = np.random.default_rng(1)
n = RATE * SECONDS
t = np.arange(n) / RATE
far = ((np.sin(2 * np.pi * 300 * t) * np.sin(2 * np.pi * 3 * t)
        + 0.5 * rng.standard_normal(n) * (np.sin(2 * np.pi * 0.7 * t) > 0)) * 6000).astype(np.int16)
mic = np.zeros(n, np.int16)
mic[DELAY:] = (0.5 * far[:-DELAY]).astype(np.int16)
apm = AudioProcessingModule(echo_cancellation=True, noise_suppression=True, high_pass_filter=True)
apm.set_stream_delay_ms(150)
out = []
cpu = time.process_time()
for i in range(0, n, FRAME):
    start = i - DELAY + LEAD
    ref = far[start:start + FRAME] if start >= 0 else np.zeros(FRAME, np.int16)
    apm.process_reverse_stream(AudioFrame(ref.tobytes(), RATE, 1, FRAME))
    frame = AudioFrame(mic[i:i + FRAME].tobytes(), RATE, 1, FRAME)
    apm.process_stream(frame)
    out.append(np.frombuffer(bytes(frame.data), np.int16))
cpu = time.process_time() - cpu
res = np.concatenate(out).astype(float)[-3 * RATE:]
src = mic.astype(float)[-3 * RATE:]
damping = 10 * np.log10((np.mean(src ** 2) + 1e-9) / (np.mean(res ** 2) + 1e-9))
print(f'CPU: {100 * cpu / SECONDS:.1f} % eines Kerns, Dämpfung letzte 3 s: {damping:.1f} dB')
