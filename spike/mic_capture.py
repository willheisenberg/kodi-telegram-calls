#!/usr/bin/env python3
"""Nimmt per ALSA auf und gibt s16le (48 kHz, Stereo) auf stdout aus, mit begrenzter Verzögerung.

ntgcalls liest erst nach dem Abnehmen. Ohne diesen Zwischenleser staut sich
die Aufnahme aus der Klingelphase in Pipe und ALSA-Puffer (etwa 1 s) und
bleibt das ganze Gespräch über als Verzögerung erhalten. Hier wird die Pipe
klein gehalten und alles verworfen, was älter als MAX_BACKLOG ist.
Aufruf: mic_capture.py <alsa-gerät>
"""
import collections
import fcntl
import os
import subprocess
import sys
import threading
import time

RATE = 48000
CHUNK = RATE // 100 * 2 * 2  # 10 ms
MAX_BACKLOG = 15  # Blöcke à 10 ms; ntgcalls liest in 100-ms-Blöcken, etwas Luft darüber
PIPE_SIZE = 4096


def main():
    device = sys.argv[1]
    try:
        fcntl.fcntl(sys.stdout.fileno(), fcntl.F_SETPIPE_SZ, PIPE_SIZE)
    except OSError:
        pass  # stdout ist keine Pipe (Test im Terminal)
    arecord = subprocess.Popen(
        ['aplay', '-C', '-q', '-D', device, '-f', 'S16_LE', '-r', str(RATE), '-c', '2', '-t', 'raw',
         '--buffer-time=40000'],
        stdout=subprocess.PIPE,
    )
    queue = collections.deque()
    ready = threading.Condition()
    dropped = [0]
    reported = [0, 0.0]  # zuletzt gemeldete Anzahl, Zeitpunkt

    def capture():
        while True:
            chunk = arecord.stdout.read(CHUNK)
            if len(chunk) < CHUNK:
                with ready:
                    queue.append(None)
                    ready.notify()
                return
            with ready:
                queue.append(chunk)
                while len(queue) > MAX_BACKLOG:
                    queue.popleft()
                    dropped[0] += 1
                ready.notify()
            if dropped[0] != reported[0] and time.monotonic() - reported[1] >= 1:
                print(f'mic_capture: {dropped[0]} Blöcke à 10 ms verworfen', file=sys.stderr, flush=True)
                reported[:] = [dropped[0], time.monotonic()]

    threading.Thread(target=capture, daemon=True).start()
    out = sys.stdout.buffer
    try:
        while True:
            with ready:
                ready.wait_for(lambda: queue)
                chunk = queue.popleft()
            if chunk is None:
                return
            out.write(chunk)
            out.flush()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    finally:
        arecord.terminate()


if __name__ == '__main__':
    main()
