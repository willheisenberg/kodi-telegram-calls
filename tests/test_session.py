import asyncio
import datetime
import os
from types import SimpleNamespace

from telethon.errors import PasswordHashInvalidError, PhoneCodeInvalidError, SessionPasswordNeededError

import session


def user(uid, first, last=None, **kw):
    return SimpleNamespace(id=uid, first_name=first, last_name=last, username=None, bot=False, deleted=False,
                           is_self=False, photo=None, **kw)


def test_anzeigename():
    assert session.display_name(user(1, 'Anna', 'Beck')) == 'Anna Beck'
    assert session.display_name(SimpleNamespace(title='Familie')) == 'Familie'
    assert session.display_name(SimpleNamespace(first_name=None, last_name=None, username='xy')) == 'xy'
    assert session.display_name(SimpleNamespace()) == 'Unbekannt'


def test_kontaktliste_personen_vor_gruppen_alphabetisch():
    entries = session.contact_entries([user(2, 'zoe'), user(1, 'Ärger'), user(3, 'Anna')],
                                      [SimpleNamespace(id=9, title='Verein')], lambda i: f'/b/{i}.jpg')
    assert [e['name'] for e in entries] == ['Anna', 'zoe', 'Ärger', 'Verein']
    assert entries[-1] == {'id': 9, 'name': 'Verein', 'bild': '/b/9.jpg', 'gruppe': True}


def test_wartezeit_in_minuten():
    assert 'bitte 2 Minuten' in session.wait_text(61)
    assert 'bitte 1 Minute warten' in session.wait_text(5)


class FakeQr:
    def __init__(self, waits):
        self.url = 'tg://login?token=a'
        self.expires = datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=30)
        self.waits = list(waits)
        self.recreated = 0

    async def wait(self, timeout=None):
        result = self.waits.pop(0)
        if isinstance(result, BaseException):
            raise result

    async def recreate(self):
        self.recreated += 1
        self.url = f'tg://login?token={self.recreated}'


class FakeClient:
    def __init__(self, qr=None, sign_in_errors=()):
        self.qr = qr
        self.sign_in_errors = list(sign_in_errors)
        self.sign_ins = []

    async def qr_login(self):
        return self.qr

    async def send_code_request(self, nummer):
        self.phone = nummer

    async def sign_in(self, **kwargs):
        self.sign_ins.append(kwargs)
        if self.sign_in_errors:
            raise self.sign_in_errors.pop(0)


def make(tmp_path, client):
    events, authorized = [], []

    async def on_authorized():
        authorized.append(True)

    sess = session.TelegramSession(client, lambda typ, **d: events.append((typ, d)), str(tmp_path), on_authorized)
    return sess, events, authorized


def test_qr_wird_erneuert_bis_gescannt(tmp_path):
    qr = FakeQr([TimeoutError(), None])
    sess, events, authorized = make(tmp_path, FakeClient(qr=qr))
    asyncio.run(sess.login_qr())
    qr_events = [d for t, d in events if t == 'qr']
    assert [d['url'] for d in qr_events] == ['tg://login?token=a', 'tg://login?token=1']
    assert qr_events[0]['bild'] != qr_events[1]['bild']
    assert os.path.exists(qr_events[1]['bild']) and not os.path.exists(qr_events[0]['bild'])
    assert events[-1] == ('login_ok', {}) and authorized == [True]


def test_qr_mit_zwei_faktor(tmp_path):
    sess, events, authorized = make(tmp_path, FakeClient(qr=FakeQr([SessionPasswordNeededError(None)])))
    asyncio.run(sess.login_qr())
    assert events[-1] == ('need_password', {}) and authorized == []


def test_telefon_code_und_passwort(tmp_path):
    client = FakeClient(sign_in_errors=[PhoneCodeInvalidError(None), SessionPasswordNeededError(None),
                                        PasswordHashInvalidError(None)])
    sess, events, authorized = make(tmp_path, client)

    async def scenario():
        await sess.login_phone('+491')
        await sess.login_code('111')
        await sess.login_code('222')
        await sess.login_password('falsch')
        await sess.login_password('richtig')

    asyncio.run(scenario())
    assert [t for t, d in events] == ['need_code', 'login_error', 'need_password', 'login_error', 'login_ok']
    assert events[1][1] == {'grund': 'Code falsch', 'erneut': 'code'}
    assert events[3][1] == {'grund': 'Passwort falsch', 'erneut': 'passwort'}
    assert client.sign_ins[0] == {'phone': '+491', 'code': '111'}
    assert authorized == [True]


def test_code_ohne_nummer(tmp_path):
    sess, events, _ = make(tmp_path, FakeClient())
    asyncio.run(sess.login_code('1'))
    assert events == [('login_error', {'grund': 'Zuerst die Telefonnummer eingeben'})]


def test_session_datei_wird_privat(tmp_path):
    path = tmp_path / 'telegram.session'
    path.write_text('x')
    os.chmod(path, 0o644)
    sess, events, _ = make(tmp_path, FakeClient(qr=FakeQr([None])))
    asyncio.run(sess.login_qr())
    assert oct(os.stat(path).st_mode & 0o777) == '0o600'
