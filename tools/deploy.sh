#!/usr/bin/env bash
# Kopiert das Add-on auf den Pi. addon_data (Session, Favoriten) bleibt unberührt.
# Aufruf: tools/deploy.sh [ziel] [host]
#   ziel Standard: /storage/.kodi/addons/script.telegram.calls
#   Testziel ohne Kodi: /storage/tgcalls-addon
set -euo pipefail

DEST="${1:-/storage/.kodi/addons/script.telegram.calls}"
HOST="${2:-root@192.168.178.10}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/addon/script.telegram.calls"
KODI_ADDON=/storage/.kodi/addons/script.telegram.calls

[ -d "$SRC/vendor" ] || { echo "vendor/ fehlt, zuerst tools/build-bundle.sh ausführen" >&2; exit 1; }
case "$DEST" in
    *addon_data*) echo "Ziel darf nicht in addon_data liegen" >&2; exit 1 ;;
esac

ssh "$HOST" "mkdir -p '$DEST' && rm -rf '$DEST/vendor' '$DEST/worker' '$DEST/resources'"
tar -C "$SRC" --exclude=__pycache__ -czf - . | ssh "$HOST" "tar -C '$DEST' -xzf -"

if [ "$DEST" = "$KODI_ADDON" ]; then
    # Kodi das neue bzw. geänderte Add-on einlesen lassen und es einschalten.
    ssh "$HOST" "kodi-send -a 'UpdateLocalAddons' >/dev/null && sleep 3 && python3 -c '
import json, socket
s = socket.create_connection((\"127.0.0.1\", 9090), timeout=5)
s.sendall(json.dumps({\"jsonrpc\": \"2.0\", \"id\": 1, \"method\": \"Addons.SetAddonEnabled\",
                      \"params\": {\"addonid\": \"script.telegram.calls\", \"enabled\": True}}).encode())
print(s.recv(4096).decode())
'"
fi
echo "Kopiert nach $HOST:$DEST"
