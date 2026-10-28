"""Telegram-Anrufe über py-tgcalls/ntgcalls, übersetzt in die Sprache von CallManager.

Mikrofon und Ton der Gegenseite laufen als externe Frames durch den Prozess,
damit die Echounterdrückung beide sieht (Messtest Teilprojekt 2).
"""
import logging

from ntgcalls import MediaSource
from pytgcalls import exceptions
from pytgcalls import filters as fl
from pytgcalls.types import CallConfig, ChatUpdate, Device, Direction
from pytgcalls.types.raw import AudioParameters, AudioStream, Stream
from telethon import events
from telethon.errors import UserPrivacyRestrictedError
from telethon.tl.types import PhoneCallWaiting, UpdatePhoneCall

from callmanager import CallFailed

log = logging.getLogger('worker.telegram')

MIC = AudioParameters(48000, 1)
SPEAKER = AudioParameters(48000, 2)  # 44,1 kHz bringt ntgcalls 3.0.3 zum Absturz


def mic_stream():
    return Stream(microphone=AudioStream(MediaSource.EXTERNAL, '', MIC))


def speaker_stream():
    # Bei record() steht der Ton der Gegenseite im Feld "microphone".
    return Stream(microphone=AudioStream(MediaSource.EXTERNAL, '', SPEAKER))


class TgCallsBackend:
    def __init__(self, client, calls):
        self._client = client
        self._calls = calls

    def bind(self, manager):
        """Leitet Telegram-Ereignisse an den CallManager weiter."""
        calls = self._calls

        @calls.on_update(fl.chat_update(ChatUpdate.Status.INCOMING_CALL))
        async def _incoming(_, update):
            await manager.on_incoming(update.chat_id)

        @calls.on_update(fl.chat_update(ChatUpdate.Status.LEFT_CALL))
        async def _left(_, update):
            grund = 'besetzt' if update.status & ChatUpdate.Status.BUSY_CALL else 'beendet'
            await manager.on_remote_ended(update.chat_id, grund)

        @calls.on_update(fl.stream_frame(Direction.INCOMING))
        async def _frames(_, update):
            for frame in update.frames:
                manager.on_frames(update.chat_id, frame.frame)

        @self._client.on(events.Raw(UpdatePhoneCall))
        async def _raw(update):
            call = update.phone_call
            if isinstance(call, PhoneCallWaiting) and call.receive_date:
                manager.on_ringing(call.participant_id)

    async def start_call(self, user_id, timeout):
        try:
            await self._calls.play(user_id, mic_stream(), config=CallConfig(timeout=timeout))
        except exceptions.TimedOutAnswer:
            raise CallFailed('keine_antwort') from None
        except exceptions.CallDeclined:
            raise CallFailed('abgelehnt') from None
        except exceptions.CallBusy:
            raise CallFailed('besetzt') from None
        except exceptions.CallDiscarded:
            raise CallFailed('abgebrochen') from None
        except UserPrivacyRestrictedError:
            raise CallFailed('privatsphaere') from None  # Person erlaubt keine Anrufe von dir
        await self._record(user_id)

    async def accept(self, user_id):
        try:
            await self._calls.play(user_id, mic_stream())
        except (exceptions.CallDiscarded, exceptions.NotInCallError):
            raise CallFailed('verpasst') from None
        await self._record(user_id)

    async def _record(self, user_id):
        try:
            await self._calls.record(user_id, speaker_stream())
        except Exception:
            log.exception('Empfang des Tons ließ sich nicht starten')
            await self.hang_up(user_id)
            raise CallFailed('fehler') from None

    async def hang_up(self, user_id):
        try:
            await self._calls.leave_call(user_id)
        except exceptions.NotInCallError:
            pass

    async def send_audio(self, user_id, pcm):
        await self._calls.send_frame(user_id, Device.MICROPHONE, pcm)
