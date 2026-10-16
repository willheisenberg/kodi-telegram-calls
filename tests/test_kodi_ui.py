"""Rauchtest: kodi_ui lässt sich mit Kodi-Attrappen importieren, die Aktionen werden ausgeführt."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'kodistubs'))

import xbmc  # noqa: E402

from tgc import kodi_ui  # noqa: E402


class FakeWorker:
    def __init__(self):
        self.sent = []

    def send(self, typ, **data):
        self.sent.append((typ, data))


def controller():
    c = kodi_ui.Controller.__new__(kodi_ui.Controller)
    c.player = xbmc.Player()
    c.sdp_path = None
    c.worker = FakeWorker()
    c.running = True
    return c


def test_senden_und_beenden():
    c = controller()
    c.execute(('send', 'call', {'id': 3}))
    c.execute(('exit',))
    assert c.worker.sent == [('call', {'id': 3})] and c.running is False


def test_sdp_abspielen_und_nur_eigenen_stream_stoppen():
    c = controller()
    c.execute(('play_kodi', '/p/anruf.sdp'))
    assert c.player.played == ['/p/anruf.sdp']
    c.player.played.append('/film.mkv')
    c.execute(('stop_kodi',))
    assert c.player.played == ['/p/anruf.sdp', '/film.mkv']


def test_bildschirmschoner():
    c = controller()
    c.execute(('screensaver', False))
    c.execute(('screensaver', True))
    assert xbmc.builtins[-2:] == ['InhibitScreensaver(true)', 'InhibitScreensaver(false)']


def test_worker_umgebung_ohne_pythonhome(monkeypatch):
    monkeypatch.setenv('PYTHONHOME', '/kodi')
    env = kodi_ui.worker_env()
    assert 'PYTHONHOME' not in env
    assert env['PYTHONPATH'].split(os.pathsep) == ['/addon/vendor', '/addon/resources/lib']
    assert kodi_ui.worker_command()[1:] == ['/addon/worker/main.py', '--data', '/profile/']


def test_hauptschleife_wartet_in_kodis_wartefunktion():
    """Kodi stellt onInit/onClick/onAction nur zu, während das Skript in waitForAbort/sleep steckt."""
    import queue

    from tgc.appstate import AppState

    class Fav:
        ids = []

    c = controller()
    c.events = queue.Queue()
    c.state = AppState(Fav())
    c.ui = type('Ui', (), {'show': lambda self, s: None, 'refresh': lambda self: None})()
    waits = []

    def on_wait(timeout):
        waits.append(timeout)
        if len(waits) == 1:
            c.events.put(('user', 'exit', {}))
        return False

    import threading

    xbmc.Monitor.on_wait = on_wait
    loop = threading.Thread(target=c.run, daemon=True)
    try:
        loop.start()
        loop.join(3)
        assert not loop.is_alive(), 'Hauptschleife endet nicht: wartet sie in waitForAbort?'
    finally:
        c.running = False
        loop.join(1)
        xbmc.Monitor.on_wait = None
    assert waits and all(t is not None and t <= 0.2 for t in waits)
    assert c.running is False


def test_liste_bekommt_nach_dem_fuellen_den_fokus():
    """Beim Laden ist die Liste leer und kann den Fokus nicht nehmen; nach dem Füllen holt das Fenster ihn nach."""

    class FakeList:
        def getSelectedPosition(self):
            return -1

        def reset(self):
            pass

        def addItems(self, items):
            self.items = items

    screen = kodi_ui.HomeScreen.__new__(kodi_ui.HomeScreen)
    lst = FakeList()
    focused = []
    screen.getControl = lambda control_id: lst

    def no_focus():
        raise RuntimeError('kein Fokus')

    screen.getFocusId = no_focus
    screen.setFocusId = focused.append
    screen.fill(['a'])
    assert focused == [100]


class KodiHistory:
    """Bildet Kodis Fensterverlauf nach: show() legt oben auf, close() schließt immer das oberste Fenster."""

    def __init__(self):
        self.stack = ['kodi-hauptmenue']

    def screen_class(self, name):
        history = self

        class FakeScreen:
            def __init__(self, *args, **kwargs):
                self.ready = False

            def show(self):
                history.stack.append(name)

            def close(self):
                history.stack.pop()  # TMSG_GUI_PREVIOUS_WINDOW: egal welches Objekt, das aktive geht

            def render(self):
                pass

        return FakeScreen


def test_fensterwechsel_folgt_kodis_verlauf(monkeypatch):
    history = KodiHistory()
    monkeypatch.setattr(kodi_ui.Ui, 'FILES', {n: ('x.xml', history.screen_class(n))
                                              for n in ('login', 'home', 'contacts', 'call')})
    ui = kodi_ui.Ui(push=None, state=None, root='/r')
    ui.show('home')
    ui.show('login')
    ui.show('home')
    assert history.stack[-1] == 'home'
    ui.show('contacts')
    ui.show('call')
    ui.show('contacts')
    assert history.stack[-1] == 'contacts'
    ui.show('home')
    assert history.stack == ['kodi-hauptmenue', 'home']
    ui.close_all()
    assert history.stack == ['kodi-hauptmenue']


def test_start_des_anrufprozesses_reagiert_auf_kodis_abbruch(monkeypatch):
    """Startet man das Add-on erneut, fordert Kodi die alte Instanz zum Beenden auf und schießt sie nach 5 s ab."""
    seen = {}

    class FakeWorker:
        def start(self, should_abort=None):
            seen['should_abort'] = should_abort

    monkeypatch.setattr(kodi_ui, 'make_worker', lambda on_event: FakeWorker())
    c = controller()
    c.events = None
    assert c.start_worker() is True
    assert callable(seen['should_abort']) and seen['should_abort']() is False


def test_zweiter_start_holt_die_laufende_instanz_nach_vorn():
    """Ein zweiter Start (z. B. per Kore) beendet sich und bittet die laufende Instanz, ihr Fenster zu zeigen."""
    import queue

    import xbmcgui

    from tgc.appstate import AppState

    class Fav:
        ids = []

    raised = []
    c = controller()
    c.events = queue.Queue()
    c.state = AppState(Fav())
    c.ui = type('Ui', (), {'raise_top': lambda self: raised.append(True)})()
    xbmcgui.Window(10000).setProperty(kodi_ui.RAISE_PROPERTY, '1')
    c.process(0.0)
    assert raised == [True]
    assert xbmcgui.Window(10000).getProperty(kodi_ui.RAISE_PROPERTY) == ''


def test_visualisierung_verdeckt_den_anruf_nicht():
    """Party Video (oder Kodi) schaltet beim Anrufton auf die Visualisierung; im Anruf holt sich das Add-on zurück."""
    import queue

    from tgc.appstate import AppState

    class Fav:
        ids = []

    raised = []
    c = controller()
    c.events = queue.Queue()
    c.state = AppState(Fav())
    c.ui = type('Ui', (), {'raise_top': lambda self: raised.append(True), 'refresh_call': lambda self: None})()
    xbmc.conditions.add('Window.IsActive(visualisation)')
    try:
        c.process(0.0)
        assert raised == []  # ohne Anruf darf Musik ihre Visualisierung behalten
        c.state.call = {'id': 1, 'name': 'A', 'bild': '', 'status': 'Wählt …', 'since': None,
                        'stumm': False, 'ended_at': None}
        c.process(0.1)
        assert raised == [True]
    finally:
        xbmc.conditions.clear()


def test_party_video_schaltet_waehrend_des_anrufs_nicht_um():
    """visualization.partyvideo prüft partyvideo.suppress am Home-Fenster (docs/bot-api.md dort)."""
    import xbmcgui

    c = controller()
    c.execute(('screensaver', False))  # Klingeln oder Anruf beginnt
    assert xbmcgui.Window(10000).getProperty('partyvideo.suppress') == 'script.telegram.calls'
    c.execute(('screensaver', True))   # Anruf vorbei, Absturz oder Beenden
    assert xbmcgui.Window(10000).getProperty('partyvideo.suppress') == ''
