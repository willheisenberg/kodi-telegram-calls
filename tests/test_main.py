import asyncio

import main


def test_sperre_verhindert_zweiten_prozess(tmp_path):
    path = str(tmp_path / 'worker.lock')
    first = main.acquire_lock(path)
    assert first is not None
    assert main.acquire_lock(path) is None
    main.os.close(first)
    again = main.acquire_lock(path)
    assert again is not None
    main.os.close(again)


class Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        async def method(*args):
            self.calls.append((name, args))
        return method


def make_worker(tmp_path, with_calls=True):
    worker = main.Worker({'api_id': 1, 'api_hash': 'x'}, str(tmp_path))
    events = []
    worker.server.emit = lambda typ, **d: events.append((typ, d))
    worker.session = Recorder()
    worker.calls = Recorder() if with_calls else None
    return worker, events


def test_befehle_werden_verteilt(tmp_path):
    worker, events = make_worker(tmp_path)

    async def scenario():
        for message in ({'typ': 'login_phone', 'nummer': '+49'}, {'typ': 'contacts'},
                        {'typ': 'call', 'id': '7'}, {'typ': 'mute', 'an': 1}, {'typ': 'hangup'}):
            await worker.on_command(message)

    asyncio.run(scenario())
    assert worker.session.calls == [('login_phone', ('+49',)), ('send_contacts', ())]
    assert worker.calls.calls == [('call', (7,)), ('set_mute', (True,)), ('hangup', ())]


def test_anrufbefehl_ohne_anmeldung(tmp_path):
    worker, events = make_worker(tmp_path, with_calls=False)
    asyncio.run(worker.on_command({'typ': 'call', 'id': 7}))
    assert events == [('error', {'text': 'Nicht angemeldet'})]


def test_quit_setzt_ende(tmp_path):
    async def scenario():
        worker, events = make_worker(tmp_path)
        await worker.on_command({'typ': 'quit'})
        return worker.quit.is_set()

    assert asyncio.run(scenario()) is True


def test_widerrufene_session_fuehrt_zur_anmeldung(tmp_path):
    from telethon.errors import UnauthorizedError

    worker, events = make_worker(tmp_path)

    async def revoked(*args):
        raise UnauthorizedError(None, 'AUTH_KEY_UNREGISTERED')

    worker.session.send_contacts = revoked
    asyncio.run(worker.on_command({'typ': 'contacts'}))
    assert events == [('ready', {'angemeldet': False})]


def test_import_verdraengt_installierte_pakete_nicht():
    """main.py darf vendor/ (aarch64) nur hinten anhängen; vorn würde es auf dem Entwicklungsrechner gewinnen."""
    import site
    import sys

    vendor = main.os.path.join(main.ADDON, 'vendor')
    site_packages = site.getsitepackages()[0]
    assert sys.path.index(vendor) > sys.path.index(site_packages)
