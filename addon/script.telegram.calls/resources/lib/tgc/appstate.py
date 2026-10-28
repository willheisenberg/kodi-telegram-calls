"""Zustandslogik der Oberfläche, ohne Kodi testbar.

on_event (Ereignis vom Anrufprozess), on_user (Taste oder Klick) und tick
(Uhr) ändern den Zustand und geben eine Liste von Aktionen zurück, die
kodi_ui ausführt:

  ('send', typ, daten)     Befehl an den Anrufprozess
  ('show', bildschirm)     'login' | 'home' | 'contacts' | 'call'
  ('refresh',)             aktuellen Bildschirm neu zeichnen
  ('refresh_call',)        nur die Statuszeile im Anruf (Uhr)
  ('ring', an)             Klingeldialog zeigen oder schließen
  ('play_kodi', pfad) | ('stop_kodi',) | ('pause_kodi',)
  ('screensaver', erlaubt) False: Bildschirmschoner beenden und unterdrücken
  ('notify', text)
  ('ask', 'nummer' | 'code' | 'passwort')
  ('confirm_exit',) | ('exit',) | ('restart_worker',)
"""

GRUND = {
    'aufgelegt': 'Aufgelegt',
    'beendet': 'Gespräch beendet',
    'abgelehnt': 'Abgelehnt',
    'besetzt': 'Besetzt',
    'keine_antwort': 'Keine Antwort',
    'verpasst': 'Verpasst',
    'abgebrochen': 'Verbindung abgebrochen',
    'privatsphaere': 'Anrufe nicht erlaubt (Datenschutz)',
    'tonausgabe': 'Tonausgabe fehlgeschlagen',
    'fehler': 'Fehler beim Verbinden',
}
ENDED_SHOW_SECONDS = 3
NO_MIC = 'Kein Mikrofon: Webcam anschließen bzw. Mikrofon-Regler prüfen'


class AppState:
    def __init__(self, favorites):
        self.favorites = favorites
        self.screen = None
        self.previous = 'home'
        self.contacts = []
        self.qr = ''
        self.banner = ''
        self.mic_ok = True
        self.call = None     # id, name, bild, status, since, stumm, ended_at
        self.ringing = None  # id, name, bild

    # --- Abfragen für die Fenster ---------------------------------------

    def contact(self, user_id):
        for entry in self.contacts:
            if entry['id'] == user_id:
                return entry
        return {'id': user_id, 'name': str(user_id), 'bild': '', 'gruppe': False}

    def home_items(self):
        known = {c['id']: c for c in self.contacts if not c['gruppe']}
        return [known[i] for i in self.favorites.ids if i in known]

    def is_favorite(self, user_id):
        return user_id in self.favorites.ids

    def find_contact(self, text):
        """Position des ersten Kontakts, dessen Name mit text beginnt, sonst der ihn enthält; sonst None."""
        needle = text.strip().casefold()
        if not needle:
            return None
        names = [c['name'].casefold() for c in self.contacts]
        for test in (lambda n: n.startswith(needle), lambda n: needle in n):
            for index, name in enumerate(names):
                if test(name):
                    return index
        return None

    def call_status(self, now):
        call = self.call
        if call is None:
            return ''
        if call['ended_at'] is None and call['since'] is not None:
            seconds = int(now - call['since'])
            return f'Verbunden {seconds // 60:02d}:{seconds % 60:02d}'
        return call['status']

    # --- Eingänge -------------------------------------------------------

    def start(self):
        """Sofort beim Öffnen: Startseite zeigen, bis der Anrufprozess meldet, ob man angemeldet ist."""
        self.banner = 'Verbinde mit Telegram …'
        return self._show('home')

    def on_event(self, message, now):
        handler = getattr(self, '_ev_' + message['typ'], None)
        return handler(message, now) if handler else []

    def on_user(self, action, now, **data):
        handler = getattr(self, '_user_' + action, None)
        return handler(now, **data) if handler else []

    def tick(self, now):
        call = self.call
        if call is None:
            return []
        if call['ended_at'] is not None:
            if now - call['ended_at'] >= ENDED_SHOW_SECONDS:
                self.call = None
                return self._show(self.previous)
            return []
        if call['since'] is not None and self.screen == 'call':
            return [('refresh_call',)]
        return []

    # --- Ereignisse -----------------------------------------------------

    def _ev_ready(self, message, now):
        if self.banner == 'Verbinde mit Telegram …':
            self.banner = ''
        if message.get('angemeldet'):
            return self._show('home') + [('send', 'contacts', {})]
        return self._show('login') + [('send', 'login_qr', {})]

    def _ev_login_ok(self, message, now):
        return self._show('home') + [('send', 'contacts', {})]

    def _ev_qr(self, message, now):
        self.qr = message.get('bild', '')
        return [('refresh',)] if self.screen == 'login' else []

    def _ev_need_code(self, message, now):
        return [('ask', 'code')]

    def _ev_need_password(self, message, now):
        return [('ask', 'passwort')]

    def _ev_login_error(self, message, now):
        actions = [('notify', message.get('grund', 'Anmeldung fehlgeschlagen'))]
        again = message.get('erneut')
        if again in ('code', 'passwort'):
            return actions + [('ask', again)]
        return actions + [('send', 'login_qr', {})]

    def _ev_contacts(self, message, now):
        self.contacts = message.get('liste', [])
        return [('refresh',)]

    def _ev_incoming(self, message, now):
        if self.call is not None or self.ringing is not None:
            return []  # der Anrufprozess lehnt selbst als besetzt ab
        user_id = message['id']
        self.ringing = {'id': user_id, 'name': message.get('name') or str(user_id),
                        'bild': self.contact(user_id)['bild']}
        return [('pause_kodi',), ('screensaver', False), ('ring', True)]

    def _ev_outgoing_state(self, message, now):
        if self.call is None or self.call['ended_at'] is not None:
            return []
        self.call['status'] = 'Klingelt …' if message.get('zustand') == 'klingelt' else 'Wählt …'
        return [('refresh',)] if self.screen == 'call' else []

    def _ev_connected(self, message, now):
        if self.call is None:
            return []
        self.call['since'] = now
        return [('refresh',)]

    def _ev_ended(self, message, now):
        grund = message.get('grund', 'beendet')
        if self.ringing is not None:
            ringing, self.ringing = self.ringing, None
            actions = [('ring', False), ('screensaver', True)]
            if grund == 'verpasst':
                actions.append(('notify', f'Verpasster Anruf: {ringing["name"]}'))
            return actions
        if self.call is None or self.call['ended_at'] is not None:
            return []
        self.call['status'] = GRUND.get(grund, grund)
        self.call['ended_at'] = now
        return [('refresh',), ('screensaver', True)]

    def _ev_play_kodi(self, message, now):
        return [('play_kodi', message['sdp_pfad'])]

    def _ev_stop_kodi(self, message, now):
        return [('stop_kodi',)]

    def _ev_status(self, message, now):
        self.mic_ok = bool(message.get('mikrofon_ok', True))
        if not message.get('telegram_verbunden', True):
            self.banner = 'Keine Verbindung zu Telegram'
        elif not self.mic_ok:
            self.banner = NO_MIC
        else:
            self.banner = ''
        return [('refresh',)]

    def _ev_error(self, message, now):
        return [('notify', message.get('text', 'Fehler'))]

    def _ev__lost(self, message, now):
        actions = []
        if self.ringing is not None:
            self.ringing = None
            actions.append(('ring', False))
        notify = [('notify', 'Anrufteil neu gestartet')]
        if self.call is not None:
            # Wie bei jedem Ende: Grund groß im Anruffenster, tick() kehrt danach zurück.
            if self.call['ended_at'] is None:
                self.call['status'] = GRUND['abgebrochen']
                self.call['ended_at'] = now
            actions.append(('refresh',))
            notify = []
        return actions + [('stop_kodi',), ('screensaver', True)] + notify + [('restart_worker',)]

    # --- Bedienung ------------------------------------------------------

    def _user_call(self, now, id):
        if self.call is not None or self.ringing is not None:
            return []
        entry = self.contact(id)
        if entry['gruppe']:
            return [('notify', 'Gruppenanrufe folgen in einer späteren Version')]
        if not self.mic_ok:
            return [('notify', NO_MIC)]
        self.call = {'id': id, 'name': entry['name'], 'bild': entry['bild'], 'status': 'Wählt …',
                     'since': None, 'stumm': False, 'ended_at': None}
        return [('pause_kodi',), ('screensaver', False), ('send', 'call', {'id': id})] + self._show('call')

    def _user_accept(self, now):
        if self.ringing is None:
            return []
        if not self.mic_ok:
            return [('notify', NO_MIC)]
        ringing, self.ringing = self.ringing, None
        self.call = {'id': ringing['id'], 'name': ringing['name'], 'bild': ringing['bild'],
                     'status': 'Verbinde …', 'since': None, 'stumm': False, 'ended_at': None}
        return [('ring', False), ('send', 'accept', {})] + self._show('call')

    def _user_decline(self, now):
        if self.ringing is None:
            return []
        self.ringing = None
        return [('ring', False), ('send', 'decline', {}), ('screensaver', True)]

    def _user_hangup(self, now):
        if self.call is None or self.call['ended_at'] is not None:
            return []
        return [('send', 'hangup', {})]

    def _user_mute(self, now):
        if self.call is None or self.call['ended_at'] is not None:
            return []
        self.call['stumm'] = not self.call['stumm']
        return [('send', 'mute', {'an': self.call['stumm']}), ('refresh',)]

    def _user_back(self, now):
        if self.screen == 'call':
            if self.call is not None and self.call['ended_at'] is None:
                return [('send', 'hangup', {})]
            self.call = None
            return self._show(self.previous)
        if self.screen == 'contacts':
            return self._show('home')
        return [('confirm_exit',)]

    def _user_exit(self, now):
        return [('exit',)]

    def _user_open_contacts(self, now):
        return self._show('contacts')

    def _user_fav_add(self, now, id):
        self.favorites.add(id)
        return [('refresh',)]

    def _user_fav_remove(self, now, id):
        self.favorites.remove(id)
        return [('refresh',)]

    def _user_fav_move(self, now, id, step):
        self.favorites.move(id, step)
        return [('refresh',)]

    def _user_login_phone_start(self, now):
        return [('ask', 'nummer')]

    def _user_login_phone(self, now, nummer):
        return [('send', 'login_phone', {'nummer': nummer})]

    def _user_login_code(self, now, code):
        return [('send', 'login_code', {'code': code})]

    def _user_login_password(self, now, passwort):
        return [('send', 'login_password', {'passwort': passwort})]

    def _user_login_cancel(self, now):
        return [('send', 'login_qr', {})]

    # --- intern ---------------------------------------------------------

    def _show(self, screen):
        if screen == self.screen:
            return [('refresh',)]
        if self.screen in ('home', 'contacts'):
            self.previous = self.screen
        self.screen = screen
        return [('show', screen)]
