#!/usr/bin/env bash
# Probebündel für Teilprojekt 3a: PyAV + numpy (aarch64, LibreELECs Python) nach /storage/tgcalls-probe.
# Aufruf: tools/build-probe.sh [host]
set -euo pipefail
HOST="${1:-root@192.168.178.10}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT
python3 -m pip install --target "$OUT/vendor" --only-binary=:all: --implementation cp \
    --python-version 3.11 --platform manylinux_2_28_aarch64 --platform manylinux_2_17_aarch64 \
    --platform manylinux2014_aarch64 --no-compile av numpy
cp "$ROOT"/tools/messtest/av_probe.py "$ROOT"/tools/messtest/videolag.py \
   "$ROOT"/tools/messtest/beeplag.py "$ROOT"/tools/messtest/videocall_probe.py "$OUT"/
du -sh "$OUT/vendor"
ssh "$HOST" "rm -rf /storage/tgcalls-probe && mkdir -p /storage/tgcalls-probe"
tar -C "$OUT" -czf - . | ssh "$HOST" "tar -C /storage/tgcalls-probe -xzf -"
echo "Probebündel nach $HOST:/storage/tgcalls-probe"
