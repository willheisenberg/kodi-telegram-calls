import pytest

from tgc import protocol


def test_hin_und_zurueck():
    line = protocol.encode('call', id=42)
    assert line.endswith(b'\n')
    assert protocol.decode(line) == {'typ': 'call', 'id': 42}


def test_umlaute_bleiben_lesbar():
    assert 'Jürgen'.encode() in protocol.encode('incoming', id=1, name='Jürgen')


@pytest.mark.parametrize('line', [b'kein json\n', b'[1, 2]\n', b'{"id": 1}\n', b'{"typ": 3}\n', b'\xff\n'])
def test_decode_weist_muell_ab(line):
    with pytest.raises(protocol.ProtocolError):
        protocol.decode(line)


def test_unbekannter_befehl():
    with pytest.raises(protocol.ProtocolError, match='unbekannter Befehl'):
        protocol.check_command({'typ': 'rm_rf'})


def test_fehlendes_pflichtfeld():
    with pytest.raises(protocol.ProtocolError, match='id'):
        protocol.check_command({'typ': 'call'})


def test_gueltiger_befehl():
    protocol.check_command({'typ': 'mute', 'an': True})


def test_redact_versteckt_geheimes_ohne_original_zu_aendern():
    message = {'typ': 'login_password', 'passwort': 'geheim'}
    assert protocol.redact(message) == {'typ': 'login_password', 'passwort': '***'}
    assert message['passwort'] == 'geheim'
