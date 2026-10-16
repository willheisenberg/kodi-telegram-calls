import os

from tgc import instance


def test_nur_eine_instanz_bekommt_die_sperre(tmp_path):
    path = str(tmp_path / 'addon.lock')
    first = instance.acquire(path)
    assert first is not None
    assert instance.acquire(path) is None  # zweiter Start im selben Kodi-Prozess
    os.close(first)
    again = instance.acquire(path)
    assert again is not None
    os.close(again)
