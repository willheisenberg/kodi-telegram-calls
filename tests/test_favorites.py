import os
import stat

from tgc.favorites import Favorites


def test_hinzufuegen_ohne_doppelte_und_dauerhaft(tmp_path):
    path = str(tmp_path / 'favoriten.json')
    fav = Favorites(path)
    fav.add(5)
    fav.add(7)
    fav.add(5)
    assert fav.ids == [5, 7]
    assert Favorites(path).ids == [5, 7]


def test_entfernen(tmp_path):
    fav = Favorites(str(tmp_path / 'f.json'))
    fav.add(1)
    fav.add(2)
    fav.remove(1)
    fav.remove(99)
    assert fav.ids == [2]


def test_verschieben_bleibt_in_den_grenzen(tmp_path):
    fav = Favorites(str(tmp_path / 'f.json'))
    for i in (1, 2, 3):
        fav.add(i)
    fav.move(3, -1)
    assert fav.ids == [1, 3, 2]
    fav.move(1, -5)
    assert fav.ids == [1, 3, 2]
    fav.move(1, 10)
    assert fav.ids == [3, 2, 1]
    fav.move(42, 1)
    assert fav.ids == [3, 2, 1]


def test_kaputte_datei_ergibt_leere_liste(tmp_path):
    path = tmp_path / 'f.json'
    path.write_text('{kaputt')
    assert Favorites(str(path)).ids == []
    path.write_text('{"a": 1}')
    assert Favorites(str(path)).ids == []


def test_unbrauchbare_eintraege_werden_ignoriert(tmp_path):
    path = tmp_path / 'f.json'
    path.write_text('[1, "2", true, 1, 3.5, 4]')
    assert Favorites(str(path)).ids == [1, 4]


def test_datei_nur_fuer_eigentuemer_lesbar(tmp_path):
    path = tmp_path / 'f.json'
    Favorites(str(path)).add(1)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
