#!/usr/bin/env python3
"""Prüft auf dem Pi, ob das Bündel lädt, auch LiveKits native Bibliothek.

Aufruf: python3 import_check.py <add-on-ordner>
"""
import os
import sys

addon = sys.argv[1]
sys.path.insert(0, os.path.join(addon, 'vendor'))
want = open(os.path.join(addon, 'vendor', 'PYTHON_VERSION')).read().strip()
have = f'{sys.version_info.major}.{sys.version_info.minor}'
print(f'Python: Gerät {have}, Bündel {want}', 'OK' if have == want else 'FEHLER')

import ntgcalls  # noqa: E402
import numpy  # noqa: E402
import png  # noqa: E402, F401  (nur Ladeprüfung)
import pytgcalls  # noqa: E402
import qrcode  # noqa: E402, F401  (nur Ladeprüfung)
import telethon  # noqa: E402
from livekit.rtc import AudioProcessingModule  # noqa: E402

AudioProcessingModule(echo_cancellation=True, noise_suppression=True, high_pass_filter=True)
print('ntgcalls', getattr(ntgcalls, '__version__', '?'), '| telethon', telethon.__version__,
      '| numpy', numpy.__version__, '| pytgcalls', pytgcalls.__version__, '| qrcode, png ok')
print('LiveKit-Echounterdrückung: OK')
