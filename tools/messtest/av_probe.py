#!/usr/bin/env python3
"""Teilprojekt 3a: Was kann PyAV auf dem Pi? Encoder, Muxer, V4L2-Eingang, Kodiergeschwindigkeit.

Aufruf auf dem Pi: python3 /storage/tgcalls-probe/av_probe.py
Jede Fähigkeit wird einzeln als OK/FEHLT gemeldet; ein Fehlen bricht nicht ab.
"""
import os
import sys
import time

sys.path.insert(0, '/storage/tgcalls-probe/vendor')
import av  # noqa: E402
import numpy as np  # noqa: E402

VIDEO = ['mpeg2video', 'libx264', 'libopenh264', 'h264_v4l2m2m', 'mjpeg']
AUDIO = ['mp2', 'aac', 'libopus', 's302m']
SIZES = [(1280, 720), (960, 540), (640, 360)]
FPS = 25


def has_codec(name):
    try:
        av.codec.Codec(name, 'w')
        return True
    except Exception:
        return False


def report(name, ok, detail=''):
    print(f'[{"OK" if ok else "FEHLT"}] {name}' + (f': {detail}' if detail else ''), flush=True)


def cpu_seconds():
    t = os.times()
    return t.user + t.system


def bench(codec, width, height, seconds=4):
    """Kodiert Testbilder in Echtzeitmenge; liefert (erreichte fps, CPU-Anteil in % eines Kerns)."""
    out = av.open(os.devnull, mode='w', format='mpegts')
    stream = out.add_stream(codec, rate=FPS)
    stream.width, stream.height, stream.pix_fmt = width, height, 'yuv420p'
    stream.options = {'g': str(FPS), 'bf': '0'}
    if codec == 'libx264':
        stream.options.update({'preset': 'ultrafast', 'tune': 'zerolatency'})
    frames = FPS * seconds
    rgb = np.zeros((height, width, 3), np.uint8)
    t0, c0 = time.monotonic(), cpu_seconds()
    for i in range(frames):
        rgb[:, :, 0] = i % 255
        frame = av.VideoFrame.from_ndarray(rgb, format='rgb24').reformat(format='yuv420p')
        frame.pts = i
        for packet in stream.encode(frame):
            out.mux(packet)
    for packet in stream.encode(None):
        out.mux(packet)
    out.close()
    wall, cpu = time.monotonic() - t0, cpu_seconds() - c0
    return frames / wall, 100 * cpu / (frames / FPS)


def main():
    report('PyAV', True, f'{av.__version__}, FFmpeg {av.library_versions.get("libavcodec")}')
    report('Muxer mpegts', 'mpegts' in av.formats_available)
    report('Eingang v4l2', 'v4l2' in av.formats_available)
    for name in VIDEO + AUDIO:
        report(f'Encoder {name}', has_codec(name))
    for codec in [c for c in VIDEO if has_codec(c) and c != 'h264_v4l2m2m']:
        for width, height in SIZES:
            try:
                fps, cpu = bench(codec, width, height)
                report(f'Kodieren {codec} {width}x{height}', fps >= FPS,
                       f'{fps:.0f} fps möglich, CPU {cpu:.0f} % eines Kerns bei {FPS} fps')
            except Exception as e:
                report(f'Kodieren {codec} {width}x{height}', False, f'{type(e).__name__}: {e}')


if __name__ == '__main__':
    main()
