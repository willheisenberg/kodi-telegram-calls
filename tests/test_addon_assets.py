"""Kodi zeigt das Add-on in Listen mit dem Icon aus addon.xml; fehlt es, erscheint ein graues Standardbild."""
import os
import struct
import xml.etree.ElementTree as ET

ADDON = os.path.join(os.path.dirname(__file__), '..', 'addon', 'script.telegram.calls')


def test_addon_xml_nennt_ein_vorhandenes_quadratisches_png_als_icon():
    root = ET.parse(os.path.join(ADDON, 'addon.xml')).getroot()
    icon = root.find("./extension[@point='xbmc.addon.metadata']/assets/icon")
    assert icon is not None and icon.text == 'resources/icon.png'
    with open(os.path.join(ADDON, icon.text), 'rb') as f:
        head = f.read(24)
    assert head[:8] == b'\x89PNG\r\n\x1a\n'
    width, height = struct.unpack('>II', head[16:24])
    assert width == height == 512
