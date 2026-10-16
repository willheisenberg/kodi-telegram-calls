#!/usr/bin/env bash
# Kopiert den Test auf den Pi. config.ini und Session-Dateien bleiben dort unangetastet.
# Aufruf: ./deploy.sh [ziel]   (Standard: root@192.168.178.10)
set -euo pipefail

TARGET="${1:-root@192.168.178.10}"
DEST=/storage/tgcalls-test
HERE="$(cd "$(dirname "$0")" && pwd)"

[ -d "$HERE/vendor" ] || { echo "vendor/ fehlt, zuerst build-bundle.sh ausführen" >&2; exit 1; }

ssh "$TARGET" "mkdir -p $DEST && rm -rf $DEST/vendor"
tar -C "$HERE" -czf - vendor common.py check.py login.py call.py rtp_send.py mic_capture.py config.example.ini \
    | ssh "$TARGET" "tar -C $DEST -xzf -"
echo "Kopiert nach $TARGET:$DEST"
