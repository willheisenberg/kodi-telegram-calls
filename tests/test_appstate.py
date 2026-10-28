from tgc.appstate import AppState


class Fav:
    def __init__(self, ids=()):
        self.ids = list(ids)

    def add(self, i):
        if i not in self.ids:
            self.ids.append(i)

    def remove(self, i):
        if i in self.ids:
            self.ids.remove(i)

    def move(self, i, step):
        self.moved = (i, step)


CONTACTS = [
    {'id': 1, 'name': 'Anna', 'bild': '/b/1.jpg', 'gruppe': False},
    {'id': 2, 'name': 'Philipp', 'bild': '', 'gruppe': False},
    {'id': 9, 'name': 'Verein', 'bild': '', 'gruppe': True},
]


def logged_in(favorites=(2, 1, 9, 77)):
    state = AppState(Fav(favorites))
    state.on_event({'typ': 'ready', 'angemeldet': True}, 0)
    state.on_event({'typ': 'contacts', 'liste': CONTACTS}, 0)
    return state


def kinds(actions):
    return [a[0] for a in actions]


def test_ohne_anmeldung_qr_bildschirm():
    state = AppState(Fav())
    assert state.on_event({'typ': 'ready', 'angemeldet': False}, 0) == [('show', 'login'),
                                                                      ('send', 'login_qr', {})]
    assert state.on_event({'typ': 'qr', 'url': 'u', 'bild': '/q.png'}, 0) == [('refresh',)]
    assert state.qr == '/q.png'
    assert state.on_event({'typ': 'login_ok'}, 0) == [('show', 'home'), ('send', 'contacts', {})]


def test_anmeldung_per_telefon():
    state = AppState(Fav())
    state.on_event({'typ': 'ready', 'angemeldet': False}, 0)
    assert state.on_user('login_phone_start', 0) == [('ask', 'nummer')]
    assert state.on_user('login_phone', 0, nummer='+49') == [('send', 'login_phone', {'nummer': '+49'})]
    assert state.on_event({'typ': 'need_code'}, 0) == [('ask', 'code')]
    assert state.on_event({'typ': 'login_error', 'grund': 'Code falsch', 'erneut': 'code'}, 0) == [
        ('notify', 'Code falsch'), ('ask', 'code')]
    assert state.on_event({'typ': 'login_error', 'grund': 'Code abgelaufen'}, 0)[-1] == ('send', 'login_qr', {})
    assert state.on_user('login_cancel', 0) == [('send', 'login_qr', {})]


def test_favoriten_in_reihenfolge_nur_bekannte_personen():
    state = logged_in()
    assert [c['name'] for c in state.home_items()] == ['Philipp', 'Anna']


def test_anrufen_und_gespraech():
    state = logged_in()
    actions = state.on_user('call', 10, id=2)
    assert actions == [('pause_kodi',), ('screensaver', False), ('send', 'call', {'id': 2}), ('show', 'call')]
    assert state.call_status(10) == 'Wählt …'
    state.on_event({'typ': 'outgoing_state', 'zustand': 'klingelt'}, 11)
    assert state.call_status(11) == 'Klingelt …'
    state.on_event({'typ': 'connected'}, 12)
    assert state.call_status(75) == 'Verbunden 01:03'
    assert state.tick(75) == [('refresh_call',)]


def test_ende_wird_drei_sekunden_gezeigt_dann_zurueck():
    state = logged_in()
    state.on_user('open_contacts', 0)
    state.on_user('call', 1, id=1)
    state.on_event({'typ': 'ended', 'grund': 'besetzt'}, 5)
    assert state.call_status(6) == 'Besetzt'
    assert state.tick(7) == []
    assert state.tick(8) == [('show', 'contacts')]
    assert state.call is None


def test_gruppe_und_fehlendes_mikrofon_verhindern_anruf():
    state = logged_in()
    assert kinds(state.on_user('call', 0, id=9)) == ['notify']
    state.on_event({'typ': 'status', 'telegram_verbunden': True, 'mikrofon_ok': False}, 0)
    assert 'Mikrofon' in state.banner
    assert kinds(state.on_user('call', 0, id=2)) == ['notify']
    assert state.call is None


def test_keine_verbindung_im_banner():
    state = logged_in()
    state.on_event({'typ': 'status', 'telegram_verbunden': False, 'mikrofon_ok': True}, 0)
    assert state.banner == 'Keine Verbindung zu Telegram'


def test_eingehend_annehmen():
    state = logged_in()
    actions = state.on_event({'typ': 'incoming', 'id': 1, 'name': 'Anna'}, 0)
    assert actions == [('pause_kodi',), ('screensaver', False), ('ring', True)]
    assert state.ringing['bild'] == '/b/1.jpg'
    assert state.on_user('accept', 1) == [('ring', False), ('send', 'accept', {}), ('show', 'call')]
    assert state.call['name'] == 'Anna' and state.ringing is None


def test_eingehend_ablehnen_und_verpasst():
    state = logged_in()
    state.on_event({'typ': 'incoming', 'id': 1, 'name': 'Anna'}, 0)
    assert state.on_user('decline', 1) == [('ring', False), ('send', 'decline', {}), ('screensaver', True)]
    state.on_event({'typ': 'incoming', 'id': 1, 'name': 'Anna'}, 2)
    actions = state.on_event({'typ': 'ended', 'grund': 'verpasst'}, 3)
    assert actions == [('ring', False), ('screensaver', True), ('notify', 'Verpasster Anruf: Anna')]


def test_incoming_waehrend_anruf_wird_ignoriert():
    state = logged_in()
    state.on_user('call', 0, id=2)
    assert state.on_event({'typ': 'incoming', 'id': 1, 'name': 'Anna'}, 1) == []
    assert state.ringing is None


def test_zurueck_im_anruf_legt_auf_sonst_schliessen_fragen():
    state = logged_in()
    assert state.on_user('back', 0) == [('confirm_exit',)]
    state.on_user('open_contacts', 0)
    assert state.on_user('back', 0) == [('show', 'home')]
    state.on_user('call', 0, id=2)
    assert state.on_user('back', 1) == [('send', 'hangup', {})]
    state.on_event({'typ': 'ended', 'grund': 'aufgelegt'}, 2)
    assert state.on_user('back', 2) == [('show', 'home')]
    assert state.on_user('hangup', 2) == []


def test_stumm_schaltet_um():
    state = logged_in()
    state.on_user('call', 0, id=2)
    assert state.on_user('mute', 1)[0] == ('send', 'mute', {'an': True})
    assert state.on_user('mute', 2)[0] == ('send', 'mute', {'an': False})


def test_verlust_beendet_anruf_und_startet_neu():
    state = logged_in()
    state.on_user('call', 0, id=2)
    actions = state.on_event({'typ': '_lost'}, 1)
    assert actions == [('show', 'home'), ('stop_kodi',), ('screensaver', True),
                       ('notify', 'Anrufteil neu gestartet'), ('restart_worker',)]
    assert state.call is None


def test_kodi_wiedergabe_und_favoriten():
    state = logged_in()
    assert state.on_event({'typ': 'play_kodi', 'sdp_pfad': '/a.sdp'}, 0) == [('play_kodi', '/a.sdp')]
    assert state.on_event({'typ': 'stop_kodi'}, 0) == [('stop_kodi',)]
    state.on_user('fav_remove', 0, id=2)
    assert not state.is_favorite(2)
    state.on_user('fav_add', 0, id=2)
    assert state.favorites.ids[-1] == 2
    state.on_user('fav_move', 0, id=2, step=-1)
    assert state.favorites.moved == (2, -1)


def test_unbekannte_ereignisse_und_aktionen_tun_nichts():
    state = logged_in()
    assert state.on_event({'typ': 'neu'}, 0) == []
    assert state.on_user('neu', 0) == []


def test_start_zeigt_startseite_bis_ready():
    state = AppState(Fav())
    assert state.start() == [('show', 'home')]
    assert state.banner == 'Verbinde mit Telegram …'
    assert state.on_event({'typ': 'ready', 'angemeldet': False}, 0)[0] == ('show', 'login')
    assert state.banner == ''


def test_kontaktsuche():
    state = logged_in()
    assert state.find_contact('phi') == 1
    assert state.find_contact('ANN') == 0
    assert state.find_contact('ver') == 2
    assert state.find_contact('lipp') == 1
    assert state.find_contact('xyz') is None
    assert state.find_contact('  ') is None


def test_datenschutz_grund_hat_einen_text():
    state = logged_in()
    state.on_user('call', 0, id=2)
    state.on_event({'typ': 'ended', 'grund': 'privatsphaere'}, 1)
    assert 'Datenschutz' in state.call_status(1)
