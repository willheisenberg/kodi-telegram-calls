#!/usr/bin/env bash
# Lädt die aarch64-Wheels für LibreELECs Python und entpackt sie nach vendor/.
# Aufruf: ./build-bundle.sh [python-version]   (Standard: 3.11 = LibreELEC 12.2)
set -euo pipefail

PYVER="${1:-3.11}"
HERE="$(cd "$(dirname "$0")" && pwd)"
VENDOR="$HERE/vendor"

# Reine Python-Pakete ohne Wheel auf PyPI (nur sdist) werden vorab lokal gebaut.
WHEELHOUSE="$(mktemp -d)"
trap 'rm -rf "$WHEELHOUSE"' EXIT
python3 -m pip wheel --no-deps --wheel-dir "$WHEELHOUSE" pyaes

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
    "py-tgcalls>=3.0,<4" "ntgcalls>=3.0,<4" "telethon>=1.36" \
    typing_extensions  # von pip bei abweichender Host-Python-Version nicht mit aufgelöst

echo "$PYVER" > "$VENDOR/PYTHON_VERSION"
du -sh "$VENDOR"
