"""Fenster-XML an die Schriften des aktiven Skins anpassen.

Skript-Fenster kennen nur die Schriftnamen des aktiven Skins. Ein unbekannter
Name fällt auf "font13" zurück; fehlt auch der (Arctic Zephyr), bleibt der
Text unsichtbar (GUIFontManager::GetFont). Deshalb stehen in den XML-Dateien
Platzhalter $FONT_KLEIN$ usw., die beim Start ersetzt werden.
"""
import os
import re
import shutil

ROLES = {
    'KLEIN': ('font12', 'font13', 'Small', 'font10'),
    'MITTEL': ('font30', 'font27', 'font25_title', 'Medium', 'font13'),
    'GROSS': ('font45', 'font37', 'font36', 'Large', 'font30'),
    'RIESIG': ('font52', 'font60', 'LargeX2', 'Large', 'font45'),
}


def available_fonts(skin_path):
    """Schriftnamen aus den Font.xml-Dateien des Skins (eine Ebene unter dem Skin-Ordner)."""
    names = set()
    try:
        folders = os.listdir(skin_path)
    except OSError:
        return names
    for folder in folders:
        path = os.path.join(skin_path, folder, 'Font.xml')
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                names.update(re.findall(r'<name>\s*([^<\s]+)\s*</name>', f.read()))
        except OSError:
            continue
    return names


def font_roles(names):
    lower = {n.lower(): n for n in names}
    fallback = sorted(names)[0] if names else 'font13'
    roles = {}
    for role, wanted in ROLES.items():
        roles[role] = next((lower[w.lower()] for w in wanted if w.lower() in lower), fallback)
    return roles


def prepare(addon_path, target, roles):
    """Kopiert resources/skins/Default nach target, ersetzt die Platzhalter, gibt target zurück.

    target dient als scriptPath für xbmcgui.WindowXML.
    """
    source = os.path.join(addon_path, 'resources', 'skins', 'Default')
    dest = os.path.join(target, 'resources', 'skins', 'Default')
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(source, dest)
    xml_dir = os.path.join(dest, '1080i')
    for name in os.listdir(xml_dir):
        path = os.path.join(xml_dir, name)
        with open(path, encoding='utf-8') as f:
            text = f.read()
        for role, font in roles.items():
            text = text.replace('$FONT_' + role + '$', font)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
    return target
