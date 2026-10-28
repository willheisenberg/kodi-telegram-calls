"""Kodi-Seite des Add-ons: Fenster, Ausführung der Aktionen aus AppState, Anrufprozess.

Alle Entscheidungen trifft AppState (ohne Kodi testbar). Dieses Modul zeigt
nur an, nimmt Tasten entgegen und führt Aktionen aus. Fenster-Callbacks und
der Lesethread des Anrufprozesses legen ihre Eingänge in eine Warteschlange;
abgearbeitet wird sie nur im Hauptthread (Controller.run).
"""
import json
import os
import queue
import shutil
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from tgc import instance, skin
from tgc.appstate import AppState
from tgc.favorites import Favorites
from tgc.workerclient import WorkerClient, WorkerError

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_PATH = ADDON.getAddonInfo('path')
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
TITLE = 'Telegram-Anrufe'
EXIT_LOCKED = 3  # worker/main.py

ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
ACTION_STOP = 13
ACTION_CONTEXT_MENU = 117
RESTARTS_PER_MINUTE = 3
# Ein zweiter Start setzt diese Eigenschaft am Home-Fenster; die laufende Instanz holt sich dann nach vorn.
RAISE_PROPERTY = 'script.telegram.calls.raise'
HOME_WINDOW = 10000
PARTYVIDEO_SUPPRESS = 'partyvideo.suppress'  # siehe docs/bot-api.md in visualization.partyvideo


def log(message, level=xbmc.LOGINFO):
    xbmc.log(f'{ADDON_ID}: {message}', level)


def rpc(method, **params):
    request = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}
    return json.loads(xbmc.executeJSONRPC(json.dumps(request))).get('result')


def avatar(path):
    return path or 'tgc-avatar.png'


def contact_item(entry, kind, label2=''):
    item = xbmcgui.ListItem(entry['name'], label2)
    item.setArt({'thumb': avatar(entry['bild'])})
    item.setProperty('kind', kind)
    item.setProperty('id', str(entry['id']))
    return item


# --- Fenster ----------------------------------------------------------------

class _Screen(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        self.push = kwargs['push']
        self.state = kwargs['state']
        self.ready = False

    def onInit(self):
        self.ready = True
        self.render()

    def render(self):
        pass

    def user(self, action, **data):
        self.push(('user', action, data))

    def onAction(self, action):
        code = action.getId()
        if code in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.user('back')
        elif code == ACTION_STOP:
            self.user('hangup')
        elif code == ACTION_CONTEXT_MENU:
            self.context()

    def context(self):
        pass

    def selected(self):
        item = self.getControl(100).getSelectedItem()
        if item is None or item.getProperty('kind') == 'all':
            return item, None
        return item, int(item.getProperty('id'))

    def fill(self, items):
        control = self.getControl(100)
        position = control.getSelectedPosition()
        control.reset()
        control.addItems(items)
        if 0 <= position < len(items):
            control.selectItem(position)
        # Beim Laden war die Liste leer und konnte den Fokus nicht nehmen (defaultcontrol).
        try:
            focused = self.getFocusId()
        except RuntimeError:
            focused = None
        if items and focused != 100:
            self.setFocusId(100)


class LoginScreen(_Screen):
    def render(self):
        if self.ready and self.state.qr:
            self.getControl(100).setImage(self.state.qr, False)

    def onClick(self, control_id):
        if control_id == 200:
            self.user('login_phone_start')


class HomeScreen(_Screen):
    def render(self):
        if not self.ready:
            return
        favorites = self.state.home_items()
        items = [contact_item(c, 'contact') for c in favorites]
        everyone = xbmcgui.ListItem('Alle Kontakte')
        everyone.setArt({'thumb': 'tgc-alle.png'})
        everyone.setProperty('kind', 'all')
        self.fill(items + [everyone])
        self.getControl(200).setLabel(self.state.banner)
        self.getControl(201).setVisible(not favorites)

    def onClick(self, control_id):
        if control_id != 100:
            return
        item, user_id = self.selected()
        if item is None:
            return
        if user_id is None:
            self.user('open_contacts')
        else:
            self.user('call', id=user_id)

    def context(self):
        item, user_id = self.selected()
        if user_id is None:
            return
        choice = xbmcgui.Dialog().contextmenu(['Aus Favoriten entfernen', 'Nach vorne', 'Nach hinten'])
        if choice == 0:
            self.user('fav_remove', id=user_id)
        elif choice in (1, 2):
            self.user('fav_move', id=user_id, step=-1 if choice == 1 else 1)


class ContactsScreen(_Screen):
    def render(self):
        if not self.ready:
            return
        items = []
        for entry in self.state.contacts:
            if entry['gruppe']:
                label2 = 'Gruppenanrufe folgen'
            elif self.state.is_favorite(entry['id']):
                label2 = 'Favorit'
            else:
                label2 = ''
            items.append(contact_item(entry, 'group' if entry['gruppe'] else 'contact', label2))
        self.fill(items)
        self.getControl(200).setLabel(self.state.banner)

    def onClick(self, control_id):
        if control_id == 100:
            item, user_id = self.selected()
            if user_id is not None:
                self.user('call', id=user_id)

    def context(self):
        item, user_id = self.selected()
        entries = ['Suchen …']
        favorite = None
        if user_id is not None and item.getProperty('kind') == 'contact':
            favorite = self.state.is_favorite(user_id)
            entries.append('Aus Favoriten entfernen' if favorite else 'Zu Favoriten hinzufügen')
        choice = xbmcgui.Dialog().contextmenu(entries)
        if choice == 0:
            self.search()
        elif choice == 1:
            self.user('fav_remove' if favorite else 'fav_add', id=user_id)

    def search(self):
        text = xbmcgui.Dialog().input('Kontakt suchen', type=xbmcgui.INPUT_ALPHANUM)
        index = self.state.find_contact(text) if text else None
        if index is None:
            if text:
                xbmcgui.Dialog().notification(TITLE, f'Kein Kontakt „{text}“', xbmcgui.NOTIFICATION_INFO, 3000)
            return
        self.getControl(100).selectItem(index)
        self.setFocusId(100)


class CallScreen(_Screen):
    def render(self):
        call = self.state.call
        if not self.ready or call is None:
            return
        self.getControl(100).setImage(avatar(call['bild']), False)
        self.getControl(101).setLabel(call['name'])
        self.getControl(200).setLabel('Ton an' if call['stumm'] else 'Stumm')
        self.render_status()

    def render_status(self):
        if self.ready:
            self.getControl(102).setLabel(self.state.call_status(time.monotonic()))

    def onClick(self, control_id):
        if control_id == 200:
            self.user('mute')
        elif control_id == 201:
            self.user('hangup')


class RingDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.push = kwargs['push']
        self.state = kwargs['state']

    def onInit(self):
        ringing = self.state.ringing
        if ringing is not None:
            self.getControl(100).setImage(avatar(ringing['bild']), False)
            self.getControl(101).setLabel(ringing['name'])

    def onClick(self, control_id):
        self.push(('user', 'accept' if control_id == 200 else 'decline', {}))

    def onAction(self, action):
        if action.getId() in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK, ACTION_STOP):
            self.push(('user', 'decline', {}))


class Ui:
    FILES = {'login': ('tgc-login.xml', LoginScreen), 'home': ('tgc-home.xml', HomeScreen),
             'contacts': ('tgc-contacts.xml', ContactsScreen), 'call': ('tgc-call.xml', CallScreen)}

    def __init__(self, push, state, root):
        self._push = push
        self._state = state
        self._root = root
        self._screens = {}
        # Kodis Fensterverlauf: close() schließt immer das *aktive* Fenster (TMSG_GUI_PREVIOUS_WINDOW).
        # Neue Bildschirme kommen deshalb oben drauf, zurück geht es durch Schließen von oben.
        self._stack = []
        self._ring = None

    def _screen(self, name):
        if name not in self._screens:
            xml, cls = self.FILES[name]
            self._screens[name] = cls(xml, self._root, 'Default', '1080i', push=self._push, state=self._state)
        return self._screens[name]

    def show(self, name):
        if self._stack and self._stack[-1] == name:
            self._screens[name].render()
            return
        if name in self._stack:
            while self._stack[-1] != name:
                self._screens[self._stack.pop()].close()
            self._screens[name].render()
            return
        screen = self._screen(name)
        screen.ready = False
        screen.show()
        self._stack.append(name)

    def raise_top(self):
        """Oberstes Fenster wieder zeigen, z. B. nachdem man in Kodi woanders hin gewechselt ist."""
        if self._stack:
            self._screens[self._stack[-1]].show()
        # Den Klingeldialog nicht neu zeigen: er liegt ohnehin über jedem Fenster, und neu zeigen
        # setzt den Fokus auf "Annehmen" zurück.

    def refresh(self):
        if self._stack:
            self._screens[self._stack[-1]].render()

    def refresh_call(self):
        if self._stack and self._stack[-1] == 'call':
            self._screens['call'].render_status()

    def ring(self, on):
        if on and self._ring is None:
            self._ring = RingDialog('tgc-ring.xml', self._root, 'Default', '1080i',
                                    push=self._push, state=self._state)
            self._ring.show()
        elif not on and self._ring is not None:
            self._ring.close()
            self._ring = None

    def close_all(self):
        self.ring(False)
        while self._stack:
            self._screens[self._stack.pop()].close()
        self._screens.clear()


# --- Steuerung --------------------------------------------------------------

def worker_command():
    python = shutil.which('python3') or '/usr/bin/python3'
    return [python, os.path.join(ADDON_PATH, 'worker', 'main.py'), '--data', PROFILE]


def worker_env():
    env = dict(os.environ)
    env.pop('PYTHONHOME', None)  # Kodis eingebettetes Python darf den Prozess nicht beeinflussen
    env['PYTHONPATH'] = os.pathsep.join([os.path.join(ADDON_PATH, 'vendor'),
                                         os.path.join(ADDON_PATH, 'resources', 'lib')])
    env['PYTHONNOUSERSITE'] = '1'
    return env


def worker_init():
    return {
        'api_id': ADDON.getSettingInt('api_id'),
        'api_hash': ADDON.getSettingString('api_hash'),
        'direkt': ADDON.getSettingBool('direkte_ausgabe'),
        'echo': ADDON.getSettingString('echo') or 'webrtc',
        'mikrofon': ADDON.getSettingString('mikrofon'),
    }


def make_worker(on_event):
    return WorkerClient(worker_command(), worker_init(), os.path.join(PROFILE, 'worker.sock'), on_event,
                        env=worker_env(), log_path=os.path.join(PROFILE, 'worker.log'))


class Controller:
    def __init__(self):
        self.events = queue.Queue()
        self.state = AppState(Favorites(os.path.join(PROFILE, 'favoriten.json')))
        roles = skin.font_roles(skin.available_fonts(xbmcvfs.translatePath('special://skin/')))
        root = skin.prepare(ADDON_PATH, os.path.join(PROFILE, 'ui'), roles)
        self.ui = Ui(self.events.put, self.state, root)
        self.player = xbmc.Player()
        self.sdp_path = None
        self.worker = None
        self.restarts = []
        self.running = True

    def start_worker(self):
        self.worker = make_worker(lambda message: self.events.put(('event', message)))
        try:
            # Abbrechbar: Kodi fordert beim erneuten Start die alte Instanz zum Beenden auf (5 s Frist).
            self.worker.start(should_abort=xbmc.Monitor().abortRequested)
        except WorkerError as e:
            log(f'Anrufprozess startet nicht: {e}', xbmc.LOGERROR)
            xbmcgui.Dialog().ok(TITLE, f'Der Anrufteil startet nicht ({e}).[CR]Details: {PROFILE}worker.log')
            return False
        return True

    def run(self):
        monitor = xbmc.Monitor()
        for action in self.state.start():
            self.execute(action)
        # In waitForAbort warten, nicht in queue.get: Nur dort stellt Kodi onInit, onClick und onAction zu.
        while self.running and not monitor.waitForAbort(0.1):
            self.process(time.monotonic())

    def process(self, now):
        home = xbmcgui.Window(HOME_WINDOW)
        if home.getProperty(RAISE_PROPERTY):
            home.clearProperty(RAISE_PROPERTY)
            self.ui.raise_top()
        elif self.state.call is not None or self.state.ringing is not None:
            # Der Anrufton läuft über Kodis Player; Visualisierungs-Add-ons (z. B. Party Video) halten ihn
            # für Musik und schalten auf die Visualisierung. Im Anruf gehört der Bildschirm dem Add-on.
            # Nur beim Auftauchen verdrängen: dauerndes Neuzeigen setzte den Fokus immer wieder zurück.
            covered = xbmc.getCondVisibility('Window.IsActive(visualisation)')
            if covered and not getattr(self, 'visualisation_seen', False):
                self.ui.raise_top()
            self.visualisation_seen = covered
        handled = False
        while self.running:
            try:
                item = self.events.get_nowait()
            except queue.Empty:
                break
            handled = True
            if item[0] == 'event':
                actions = self.state.on_event(item[1], now)
            else:
                actions = self.state.on_user(item[1], now, **item[2])
            for action in actions:
                self.execute(action)
        if not handled:
            for action in self.state.tick(now):
                self.execute(action)

    def execute(self, action):
        kind, args = action[0], action[1:]
        if kind == 'send':
            self.worker.send(args[0], **args[1])
        elif kind == 'show':
            self.ui.show(args[0])
        elif kind == 'refresh':
            self.ui.refresh()
        elif kind == 'refresh_call':
            self.ui.refresh_call()
        elif kind == 'ring':
            self.ui.ring(args[0])
        elif kind == 'play_kodi':
            self.play_kodi(args[0])
        elif kind == 'stop_kodi':
            self.stop_kodi()
        elif kind == 'pause_kodi':
            self.pause_other_playback()
        elif kind == 'screensaver':
            self.screensaver(args[0])
        elif kind == 'notify':
            xbmcgui.Dialog().notification(TITLE, args[0], xbmcgui.NOTIFICATION_INFO, 4000)
        elif kind == 'ask':
            self.ask(args[0])
        elif kind == 'confirm_exit':
            if xbmcgui.Dialog().yesno(TITLE, 'Telegram-Anrufe schließen? Du bist dann nicht mehr erreichbar.'):
                self.running = False
        elif kind == 'exit':
            self.running = False
        elif kind == 'restart_worker':
            self.restart_worker()

    def play_kodi(self, path):
        self.sdp_path = path
        item = xbmcgui.ListItem(path=path)  # ohne inputstream: ffmpegs Whitelist lehnt sonst rtp ab
        item.getMusicInfoTag().setTitle('Telegram-Anruf')
        self.player.play(path, item)

    def stop_kodi(self):
        try:
            if self.sdp_path and self.player.isPlaying() and self.player.getPlayingFile() == self.sdp_path:
                self.player.stop()
        except RuntimeError:
            pass

    def pause_other_playback(self):
        for player in rpc('Player.GetActivePlayers') or []:
            item = (rpc('Player.GetItem', playerid=player['playerid'], properties=['file']) or {}).get('item', {})
            if item.get('file') != self.sdp_path:
                rpc('Player.PlayPause', playerid=player['playerid'], play=False)

    def screensaver(self, allowed):
        """Klingeln/Anruf beginnt (allowed=False) oder ist vorbei: Bildschirmschoner und Party Video."""
        home = xbmcgui.Window(HOME_WINDOW)
        if allowed:
            xbmc.executebuiltin('InhibitScreensaver(false)')
            home.clearProperty(PARTYVIDEO_SUPPRESS)
        else:
            # Der Anrufton läuft über Kodis Player; visualization.partyvideo schaltet sonst auf das Video.
            home.setProperty(PARTYVIDEO_SUPPRESS, ADDON_ID)
            xbmc.executebuiltin('InhibitScreensaver(true)')
            rpc('Input.ExecuteAction', action='noop')  # weckt einen laufenden Bildschirmschoner

    def ask(self, what):
        dialog = xbmcgui.Dialog()
        if what == 'nummer':
            value = dialog.input('Telefonnummer mit Ländervorwahl, z. B. +4917…', type=xbmcgui.INPUT_ALPHANUM)
            action, key = 'login_phone', 'nummer'
        elif what == 'code':
            value = dialog.input('Code aus der Telegram-App', type=xbmcgui.INPUT_NUMERIC)
            action, key = 'login_code', 'code'
        else:
            value = dialog.input('Zwei-Faktor-Passwort', type=xbmcgui.INPUT_ALPHANUM,
                                 option=xbmcgui.ALPHANUM_HIDE_INPUT)
            action, key = 'login_password', 'passwort'
        if value:
            self.events.put(('user', action, {key: value}))
        else:
            self.events.put(('user', 'login_cancel', {}))

    def restart_worker(self):
        now = time.monotonic()
        self.restarts = [t for t in self.restarts if now - t < 60] + [now]
        self.worker.stop()
        if len(self.restarts) > RESTARTS_PER_MINUTE:
            xbmcgui.Dialog().ok(TITLE, f'Der Anrufteil stürzt wiederholt ab.[CR]Details: {PROFILE}worker.log')
            self.running = False
            return
        if not self.start_worker():
            self.running = False

    def shutdown(self):
        if self.worker is not None:
            self.worker.stop()  # der Anrufprozess legt einen laufenden Anruf vorher auf
        self.stop_kodi()
        self.screensaver(True)
        self.ui.close_all()


def credentials_missing():
    return not ADDON.getSettingInt('api_id') or not ADDON.getSettingString('api_hash')


def main():
    os.makedirs(PROFILE, mode=0o700, exist_ok=True)
    if credentials_missing():
        xbmcgui.Dialog().ok(TITLE, 'Bitte zuerst api_id und api_hash von my.telegram.org in den '
                                   'Einstellungen eintragen.')
        ADDON.openSettings()
        return
    lock = instance.acquire(os.path.join(PROFILE, 'addon.lock'))
    if lock is None:
        # Läuft schon: nicht ein zweites Mal starten, sondern die laufende Instanz nach vorn holen.
        xbmcgui.Window(HOME_WINDOW).setProperty(RAISE_PROPERTY, '1')
        return
    controller = Controller()
    try:
        if controller.start_worker():
            controller.run()
    finally:
        controller.shutdown()
        os.close(lock)


def logout():
    """Aus den Einstellungen: Session bei Telegram abmelden und löschen."""
    if credentials_missing():
        return
    if not xbmcgui.Dialog().yesno(TITLE, 'Dieses Gerät bei Telegram abmelden?'):
        return
    events = queue.Queue()
    worker = make_worker(events.put)
    try:
        worker.start()
    except WorkerError as e:
        if worker.returncode() == EXIT_LOCKED or f'Code {EXIT_LOCKED}' in str(e):
            xbmcgui.Dialog().ok(TITLE, 'Bitte zuerst Telegram-Anrufe schließen.')
        else:
            xbmcgui.Dialog().ok(TITLE, f'Abmelden fehlgeschlagen ({e}).')
        return
    try:
        deadline = time.monotonic() + 20
        sent = False
        while time.monotonic() < deadline:
            try:
                message = events.get(timeout=0.5)
            except queue.Empty:
                continue
            if message['typ'] == 'ready' and message.get('angemeldet') and not sent:
                worker.send('logout')
                sent = True
            elif message['typ'] == 'ready' and not message.get('angemeldet'):
                xbmcgui.Dialog().notification(TITLE, 'Abgemeldet', xbmcgui.NOTIFICATION_INFO, 4000)
                return
    finally:
        worker.stop()
