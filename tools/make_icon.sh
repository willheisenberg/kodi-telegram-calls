#!/usr/bin/env bash
# Erzeugt Add-on-Icon (512×512) und README-Banner aus den SVGs in assets/. Braucht rsvg-convert (librsvg).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
rsvg-convert -w 512 -h 512 "$ROOT/assets/icon.svg" -o "$ROOT/addon/script.telegram.calls/resources/icon.png"
rsvg-convert -w 1280 -h 360 "$ROOT/assets/banner.svg" -o "$ROOT/assets/banner.png"
echo "geschrieben: addon/script.telegram.calls/resources/icon.png, assets/banner.png"
