"""Einstieg des Add-ons: Oberfläche, oder mit Argument "logout" Abmelden (aus den Einstellungen)."""
import os
import sys

import xbmcaddon

sys.path.insert(0, os.path.join(xbmcaddon.Addon().getAddonInfo('path'), 'resources', 'lib'))

from tgc import kodi_ui  # noqa: E402

if len(sys.argv) > 1 and sys.argv[1] == 'logout':
    kodi_ui.logout()
else:
    kodi_ui.main()
