import asyncio

import pytest
from pytgcalls import exceptions

import tgbackend
from callmanager import CallFailed


class FakeCalls:
    def __init__(self, play_error=None, record_error=None, leave_error=None):
        self.play_error, self.record_error, self.leave_error = play_error, record_error, leave_error
        self.played, self.recorded, self.left, self.frames = [], [], [], []

    async def play(self, chat_id, stream, config=None):
        self.played.append((chat_id, stream, config))
        if self.play_error:
            raise self.play_error

    async def record(self, chat_id, stream):
        self.recorded.append((chat_id, stream))
        if self.record_error:
            raise self.record_error

    async def leave_call(self, chat_id):
        self.left.append(chat_id)
        if self.leave_error:
            raise self.leave_error

    async def send_frame(self, chat_id, device, data):
        self.frames.append((chat_id, device, data))


def backend(calls):
    return tgbackend.TgCallsBackend(client=None, calls=calls)


def test_anruf_startet_mikrofon_und_empfang_mit_48khz():
    calls = FakeCalls()
    asyncio.run(backend(calls).start_call(7, 45))
    chat_id, stream, config = calls.played[0]
    assert chat_id == 7 and config.timeout == 45
    assert stream.microphone.parameters.bitrate == 48000 and stream.microphone.parameters.channels == 1
    assert calls.recorded[0][1].microphone.parameters.bitrate == 48000
    assert calls.recorded[0][1].microphone.parameters.channels == 2


@pytest.mark.parametrize('error, grund', [
    (exceptions.TimedOutAnswer(), 'keine_antwort'),
    (exceptions.CallDeclined(7), 'abgelehnt'),
    (exceptions.CallBusy(7), 'besetzt'),
    (exceptions.CallDiscarded(7), 'abgebrochen'),
])
def test_gruende_beim_waehlen(error, grund):
    with pytest.raises(CallFailed) as info:
        asyncio.run(backend(FakeCalls(play_error=error)).start_call(7, 45))
    assert info.value.grund == grund


def test_fehler_beim_empfang_legt_auf():
    calls = FakeCalls(record_error=RuntimeError('kaputt'))
    with pytest.raises(CallFailed) as info:
        asyncio.run(backend(calls).start_call(7, 45))
    assert info.value.grund == 'fehler' and calls.left == [7]


def test_auflegen_ohne_anruf_ist_kein_fehler():
    calls = FakeCalls(leave_error=exceptions.NotInCallError())
    asyncio.run(backend(calls).hang_up(7))
    assert calls.left == [7]


def test_mikrofon_geht_als_externer_frame_raus():
    calls = FakeCalls()
    asyncio.run(backend(calls).send_audio(7, b'ab'))
    assert calls.frames == [(7, tgbackend.Device.MICROPHONE, b'ab')]


def test_datenschutz_sperre_wird_zum_eigenen_grund():
    """Telegram verweigert den Anruf, wenn die Person Anrufe in ihren Datenschutzeinstellungen gesperrt hat."""
    from telethon.errors import UserPrivacyRestrictedError

    with pytest.raises(CallFailed) as info:
        asyncio.run(backend(FakeCalls(play_error=UserPrivacyRestrictedError(None))).start_call(7, 45))
    assert info.value.grund == 'privatsphaere'
