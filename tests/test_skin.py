from tgc import skin


def test_schriften_aus_font_xml(tmp_path):
    (tmp_path / '1080i').mkdir()
    (tmp_path / '1080i' / 'Font.xml').write_text(
        '<fonts><fontset id="Default"><font><name>Small</name></font><font><name> Large </name></font>'
        '</fontset></fonts>')
    assert skin.available_fonts(str(tmp_path)) == {'Small', 'Large'}
    assert skin.available_fonts(str(tmp_path / 'fehlt')) == set()


def test_rollen_fuer_estuary_und_arctic_zephyr():
    estuary = skin.font_roles({'font10', 'font12', 'font13', 'font30', 'font45', 'font52'})
    assert estuary == {'KLEIN': 'font12', 'MITTEL': 'font30', 'GROSS': 'font45', 'RIESIG': 'font52'}
    zephyr = skin.font_roles({'Small', 'Medium', 'Large', 'LargeX2', 'Mini'})
    assert zephyr == {'KLEIN': 'Small', 'MITTEL': 'Medium', 'GROSS': 'Large', 'RIESIG': 'LargeX2'}


def test_unbekannter_skin_nimmt_irgendeine_vorhandene_schrift():
    assert set(skin.font_roles({'Zeta', 'Alpha'}).values()) == {'Alpha'}


def test_prepare_ersetzt_platzhalter(tmp_path):
    addon = tmp_path / 'addon'
    xml_dir = addon / 'resources' / 'skins' / 'Default' / '1080i'
    xml_dir.mkdir(parents=True)
    (addon / 'resources' / 'skins' / 'Default' / 'media').mkdir()
    (xml_dir / 'tgc-home.xml').write_text('<font>$FONT_GROSS$</font><font>$FONT_KLEIN$</font>')
    target = skin.prepare(str(addon), str(tmp_path / 'ui'), {'GROSS': 'Large', 'KLEIN': 'Small'})
    out = tmp_path / 'ui' / 'resources' / 'skins' / 'Default' / '1080i' / 'tgc-home.xml'
    assert target == str(tmp_path / 'ui')
    assert out.read_text() == '<font>Large</font><font>Small</font>'
    skin.prepare(str(addon), str(tmp_path / 'ui'), {'GROSS': 'font45', 'KLEIN': 'font12'})
    assert out.read_text() == '<font>font45</font><font>font12</font>'
