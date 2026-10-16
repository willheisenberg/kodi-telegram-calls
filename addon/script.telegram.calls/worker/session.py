"""Telegram-Konto: Anmeldung per QR-Code oder Telefonnummer, Kontakte, Profilbilder.

Telefonnummer, Code und Passwort werden nur an Telegram weitergegeben, nie
gespeichert oder protokolliert. Gespeichert wird nur die Session (Rechte 600).
"""
import asyncio
import datetime
import logging
import math
import os

from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.tl.functions.contacts import GetContactsRequest

log = logging.getLogger('worker.session')

SESSION_NAME = 'telegram'  # Telethon hängt .session an


def display_name(entity):
    title = getattr(entity, 'title', None)
    if title:
        return title
    parts = [getattr(entity, 'first_name', None), getattr(entity, 'last_name', None)]
    name = ' '.join(p for p in parts if p)
    return name or getattr(entity, 'username', None) or 'Unbekannt'


def contact_entries(users, groups, avatar_for):
    """Liste für das Add-on: Personen alphabetisch, danach Gruppen alphabetisch."""
    def key(entry):
        return entry['name'].casefold()

    people = [{'id': u.id, 'name': display_name(u), 'bild': avatar_for(u.id), 'gruppe': False} for u in users]
    chats = [{'id': g.id, 'name': display_name(g), 'bild': avatar_for(g.id), 'gruppe': True} for g in groups]
    return sorted(people, key=key) + sorted(chats, key=key)


def wait_text(seconds):
    minutes = max(1, math.ceil(seconds / 60))
    return f'Telegram verlangt eine Pause: bitte {minutes} {"Minute" if minutes == 1 else "Minuten"} warten'


class TelegramSession:
    def __init__(self, client, emit, data_dir, on_authorized):
        self._client = client
        self._emit = emit
        self._on_authorized = on_authorized
        self._data_dir = data_dir
        self._avatar_dir = os.path.join(data_dir, 'bilder')
        self._session_file = os.path.join(data_dir, SESSION_NAME + '.session')
        self._names = {}
        self._phone = None
        self._login_task = None
        self._qr_count = 0

    # --- Anmeldung ------------------------------------------------------

    async def login_qr(self):
        self._cancel_login()
        self._login_task = asyncio.current_task()
        try:
            qr = await self._client.qr_login()
            while True:
                self._emit('qr', url=qr.url, bild=self._qr_image(qr.url))
                remaining = (qr.expires - datetime.datetime.now(datetime.UTC)).total_seconds()
                try:
                    await qr.wait(timeout=max(5.0, remaining - 2))
                    break
                except TimeoutError:
                    await qr.recreate()
        except asyncio.CancelledError:
            return
        except SessionPasswordNeededError:
            self._emit('need_password')
            return
        except FloodWaitError as e:
            self._emit('login_error', grund=wait_text(e.seconds))
            return
        finally:
            if self._login_task is asyncio.current_task():
                self._login_task = None
        await self._logged_in()

    async def login_phone(self, nummer):
        self._cancel_login()
        try:
            await self._client.send_code_request(nummer)
        except PhoneNumberInvalidError:
            self._emit('login_error', grund='Telefonnummer ungültig')
            return
        except FloodWaitError as e:
            self._emit('login_error', grund=wait_text(e.seconds))
            return
        self._phone = nummer
        self._emit('need_code')

    async def login_code(self, code):
        if self._phone is None:
            self._emit('login_error', grund='Zuerst die Telefonnummer eingeben')
            return
        try:
            await self._client.sign_in(phone=self._phone, code=code)
        except SessionPasswordNeededError:
            self._emit('need_password')
            return
        except PhoneCodeInvalidError:
            self._emit('login_error', grund='Code falsch', erneut='code')
            return
        except PhoneCodeExpiredError:
            self._emit('login_error', grund='Code abgelaufen')
            return
        except FloodWaitError as e:
            self._emit('login_error', grund=wait_text(e.seconds))
            return
        await self._logged_in()

    async def login_password(self, passwort):
        try:
            await self._client.sign_in(password=passwort)
        except PasswordHashInvalidError:
            self._emit('login_error', grund='Passwort falsch', erneut='passwort')
            return
        except FloodWaitError as e:
            self._emit('login_error', grund=wait_text(e.seconds))
            return
        await self._logged_in()

    async def logout(self):
        await self._client.log_out()

    async def _logged_in(self):
        self._phone = None
        try:
            os.chmod(self._session_file, 0o600)
        except OSError:
            pass
        await self._on_authorized()
        self._emit('login_ok')

    def _cancel_login(self):
        task = self._login_task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        self._login_task = None

    def _qr_image(self, url):
        """PNG mit neuem Namen, weil Kodi Bilder nach Pfad zwischenspeichert."""
        import qrcode
        import qrcode.image.pure

        for name in os.listdir(self._data_dir):
            if name.startswith('qr-') and name.endswith('.png'):
                os.remove(os.path.join(self._data_dir, name))
        self._qr_count += 1
        path = os.path.join(self._data_dir, f'qr-{self._qr_count}.png')
        qrcode.make(url, image_factory=qrcode.image.pure.PyPNGImage, box_size=12, border=2).save(path)
        return path

    # --- Kontakte -------------------------------------------------------

    async def send_contacts(self):
        result = await self._client(GetContactsRequest(hash=0))
        users = [u for u in result.users if not (u.bot or u.deleted or u.is_self)]
        groups = []
        async for dialog in self._client.iter_dialogs(limit=300):
            if dialog.is_group:
                groups.append(dialog.entity)
        for user in users:
            self._names[user.id] = display_name(user)
        self._emit('contacts', liste=contact_entries(users, groups, self._avatar_for))
        if await self._download_avatars(users + groups):
            self._emit('contacts', liste=contact_entries(users, groups, self._avatar_for))

    async def name_for(self, user_id):
        if user_id not in self._names:
            try:
                self._names[user_id] = display_name(await self._client.get_entity(user_id))
            except Exception as e:
                log.warning('Name für %s nicht gefunden: %s', user_id, e)
                return 'Unbekannt'
        return self._names[user_id]

    def _avatar_path(self, entity_id):
        return os.path.join(self._avatar_dir, f'{entity_id}.jpg')

    def _avatar_for(self, entity_id):
        path = self._avatar_path(entity_id)
        return path if os.path.exists(path) else ''

    async def _download_avatars(self, entities):
        os.makedirs(self._avatar_dir, mode=0o700, exist_ok=True)
        fetched = False
        for entity in entities:
            path = self._avatar_path(entity.id)
            if os.path.exists(path) or not getattr(entity, 'photo', None):
                continue
            try:
                if await self._client.download_profile_photo(entity, file=path, download_big=False):
                    fetched = True
            except Exception as e:
                log.warning('Profilbild %s nicht geladen: %s', entity.id, e)
        return fetched
