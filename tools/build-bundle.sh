#!/usr/bin/env bash
# Lädt die aarch64-Wheels für LibreELECs Python nach addon/script.telegram.calls/vendor/.
# Aufruf: tools/build-bundle.sh [python-version]   (Standard: 3.11 = LibreELEC 12.2)
set -euo pipefail

PYVER="${1:-3.11}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR="$ROOT/addon/script.telegram.calls/vendor"

# pyaes gibt es auf PyPI nur als sdist; reines Python, wird lokal gebaut.
WHEELHOUSE="$(mktemp -d)"
trap 'rm -rf "$WHEELHOUSE"' EXIT
python3 -m pip wheel --no-deps --wheel-dir "$WHEELHOUSE" pyaes==1.6.1

rm -rf "$VENDOR"
python3 -m pip install \
    --find-links "$WHEELHOUSE" \
    --target "$VENDOR" \
    --only-binary=:all: \
    --implementation cp \
    --python-version "$PYVER" \
    --platform manylinux_2_28_aarch64 \
    --platform manylinux_2_17_aarch64 \
    --platform manylinux2014_aarch64 \
    --no-compile \
    py-tgcalls==3.0.0 ntgcalls==3.0.3 telethon==1.45.0 \
    livekit==1.1.21 qrcode==8.2 pypng==0.20220715.0 \
    typing_extensions  # von pip bei abweichender Host-Python-Version nicht mit aufgelöst

echo "$PYVER" > "$VENDOR/PYTHON_VERSION"
du -sh "$VENDOR"
