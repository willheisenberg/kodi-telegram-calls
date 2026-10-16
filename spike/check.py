#!/usr/bin/env python3
"""Prüft, ob das Bundle auf diesem Gerät lauffähig ist."""
import os
import subprocess
import sys

from common import VENDOR, kodi_rpc

GUARD_ONLY = '--guard' in sys.argv
failed = False


def report(name, ok, detail=''):
    global failed
    failed = failed or not ok
    print(f"[{'OK' if ok else 'FEHLER'}] {name}{': ' + detail if detail else ''}")


def pactl(*args):
    return subprocess.run(['pactl', *args], capture_output=True, text=True, check=True).stdout


def guard():
    """Prüft, dass PulseAudio so steht, wie Soloist es braucht, und niemand Module nachgeladen hat."""
    try:
        modules = pactl('list', 'short', 'modules')
        sources = dict(line.split('\t')[:2] for line in pactl('list', 'short', 'sources').splitlines())
        outputs = [line.split('\t') for line in pactl('list', 'short', 'source-outputs').splitlines()]
        default_sink = pactl('get-default-sink').strip()
        default_source = pactl('get-default-source').strip()
    except (OSError, subprocess.CalledProcessError) as e:
        report('Wächter: pactl', False, str(e))
        return
    foreign = [line for line in modules.splitlines() if 'module-alsa-sink' in line or 'module-alsa-source' in line]
    report('Wächter: keine nachgeladenen ALSA-Module in PulseAudio', not foreign, '; '.join(foreign))
    if 'sink_name=soloist' not in modules:
        print('[INFO] Wächter: Soloist ist nicht aktiv, Audioweg nicht prüfbar')
        return
    rtp = [sources.get(o[1], o[1]) for o in outputs if 'module-rtp-send' in o[3]]
    report('Wächter: Soloist-RTP liest von soloist.monitor', rtp == ['soloist.monitor'], ', '.join(rtp) or 'kein RTP-Stream')
    report('Wächter: Standard-Ausgabe', default_sink == 'soloist', default_sink)
    report('Wächter: Standard-Quelle', default_source == 'soloist.monitor', default_source)


guard()
if GUARD_ONLY:
    sys.exit(1 if failed else 0)

have = f'{sys.version_info.major}.{sys.version_info.minor}'
try:
    want = open(os.path.join(VENDOR, 'PYTHON_VERSION')).read().strip()
    report('Python-Version', have == want, f'Gerät {have}, Bundle {want}')
except OSError as e:
    report('Bundle', False, str(e))

for module in ('ntgcalls', 'telethon', 'pytgcalls'):
    try:
        mod = __import__(module)
        report(f'Import {module}', True, getattr(mod, '__version__', ''))
    except Exception as e:
        report(f'Import {module}', False, f'{type(e).__name__}: {e}')

# Audio läuft über ALSA, nicht über PulseAudio (siehe CLAUDE.md).
try:
    cards = open('/proc/asound/cards').read()
except OSError as e:
    cards = ''
    report('ALSA-Karten', False, str(e))
report('Webcam-Mikrofon (ALSA-Karte "Webcam")', '[Webcam' in cards)
videos = sorted(d for d in os.listdir('/dev') if d.startswith('video'))
names = []
for d in videos:
    try:
        names.append(f"{d}: {open(f'/sys/class/video4linux/{d}/name').read().strip()}")
    except OSError:
        pass
report('Webcam-Kamera', any('Webcam' in n for n in names), ', '.join(names) or 'keine')
try:
    report('Kodi erreichbar (JSON-RPC 9090)', True, f"aktive Player: {len(kodi_rpc('Player.GetActivePlayers'))}")
except Exception as e:
    report('Kodi erreichbar (JSON-RPC 9090)', False, f'{type(e).__name__}: {e}')

sys.exit(1 if failed else 0)
