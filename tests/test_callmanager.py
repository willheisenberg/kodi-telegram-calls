import asyncio

import pytest

import callmanager
from callmanager import CallFailed, CallManager, State
from sinks import SinkError


class FakeBackend:
    def __init__(self):
        self.started, self.accepted, self.hung_up, self.sent = [], [], [], []
        self.start_error = None
        self.start_wait = None

    async def start_call(self, user_id, timeout):
        self.started.append(user_id)
        if self.start_wait is not None:
            await self.start_wait.wait()
        if self.start_error:
            raise CallFailed(self.start_error)

    async def accept(self, user_id):
        self.accepted.append(user_id)

    async def hang_up(self, user_id):
        self.hung_up.append(user_id)

    async def send_audio(self, user_id, pcm):
        self.sent.append((user_id, pcm))


class FakeSink:
    delay_ms = 300

    def __init__(self):
        self.written, self.stopped, self.fail = [], False, False

    def write(self, pcm):
        if self.fail:
            raise SinkError('weg')
        self.written.append(pcm)

    def stop(self):
        self.stopped = True


class FakeEcho:
    def __init__(self):
        self.references, self.processed = [], []

    def add_reference(self, mono):
        self.references.append(mono)

    def process(self, mic):
        self.processed.append(mic)
        return mic


class FakeMic:
    def __init__(self, on_frame):
        self.on_frame, self.started, self.stopped = on_frame, False, False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class FakeRing:
    def __init__(self, audio):
        self.audio = audio

    async def run(self, sink):
        self.audio.ringing = True
        try:
            await asyncio.Event().wait()
        finally:
            self.audio.ringing = False


class FakeAudio:
    def __init__(self):
        self.sinks, self.echo, self.mic, self.ringing, self.open_error = [], None, None, False, None

    def open_sink(self):
        if self.open_error:
            raise self.open_error
        self.sinks.append(FakeSink())
        return self.sinks[-1]

    def make_echo(self, delay_ms):
        self.echo = FakeEcho()
        return self.echo

    def make_mic(self, on_frame):
        self.mic = FakeMic(on_frame)
        return self.mic

    def ringtone(self):
        return FakeRing(self)


async def name_for(user_id):
    return f'Kontakt {user_id}'


def setup(**kwargs):
    events = []
    backend, audio = FakeBackend(), FakeAudio()
    manager = CallManager(backend, lambda typ, **d: events.append((typ, d)), audio, name_for, **kwargs)
    return manager, backend, audio, events


def types(events):
    return [e[0] for e in events]


def run(coro):
    return asyncio.run(coro)


def test_ausgehender_anruf_verbindet():
    manager, backend, audio, events = setup()
    run(manager.call(7))
    assert backend.started == [7]
    assert events[0] == ('outgoing_state', {'zustand': 'waehlt'})
    assert types(events)[-1] == 'connected'
    assert manager.state is State.CONNECTED
    assert audio.mic.started and len(audio.sinks) == 1


def test_abgelehnt_ohne_tonausgabe():
    manager, backend, audio, events = setup()
    backend.start_error = 'abgelehnt'
    run(manager.call(7))
    assert events[-1] == ('ended', {'grund': 'abgelehnt'})
    assert manager.state is State.IDLE and audio.sinks == []


def test_auflegen_beim_waehlen():
    async def scenario():
        manager, backend, audio, events = setup()
        backend.start_wait = asyncio.Event()
        task = asyncio.create_task(manager.call(7))
        await asyncio.sleep(0.01)
        await manager.hangup()
        await asyncio.wait_for(task, 1)
        return manager, backend, events

    manager, backend, events = run(scenario())
    assert backend.hung_up == [7]
    assert events[-1] == ('ended', {'grund': 'aufgelegt'})
    assert types(events).count('ended') == 1 and 'connected' not in types(events)


def test_klingeln_beim_waehlen_wird_gemeldet():
    async def scenario():
        manager, backend, audio, events = setup()
        backend.start_wait = asyncio.Event()
        task = asyncio.create_task(manager.call(7))
        await asyncio.sleep(0.01)
        manager.on_ringing(7)
        manager.on_ringing(8)
        backend.start_wait.set()
        await task
        return events

    events = run(scenario())
    assert events[1] == ('outgoing_state', {'zustand': 'klingelt'})
    assert types(events).count('outgoing_state') == 2


def test_eingehend_klingeln_und_annehmen():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.on_incoming(9)
        await asyncio.sleep(0.01)
        rang = audio.ringing
        await manager.accept()
        await asyncio.sleep(0.01)
        return manager, backend, audio, events, rang

    manager, backend, audio, events, rang = run(scenario())
    assert events[0] == ('incoming', {'id': 9, 'name': 'Kontakt 9'})
    assert rang is True and audio.ringing is False
    assert backend.accepted == [9]
    assert types(events)[-1] == 'connected'
    assert len(audio.sinks) == 1  # Klingelton und Gespräch nutzen dieselbe Ausgabe


def test_zweiter_anruf_wird_abgewiesen():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.call(7)
        await manager.on_incoming(8)
        return manager, backend, events

    manager, backend, events = run(scenario())
    assert backend.hung_up == [8]
    assert manager.state is State.CONNECTED and manager.peer == 7
    assert 'incoming' not in types(events)


def test_nicht_angenommen_gilt_als_verpasst():
    async def scenario():
        manager, backend, audio, events = setup(ring_timeout=0.05)
        await manager.on_incoming(9)
        await asyncio.sleep(0.2)
        return manager, backend, audio, events

    manager, backend, audio, events = run(scenario())
    assert events[-1] == ('ended', {'grund': 'verpasst'})
    assert backend.hung_up == [9] and audio.sinks[0].stopped


def test_anrufer_legt_beim_klingeln_auf():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.on_incoming(9)
        await manager.on_remote_ended(9, 'beendet')
        return events

    assert run(scenario())[-1] == ('ended', {'grund': 'verpasst'})


def test_ablehnen():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.on_incoming(9)
        await manager.decline()
        return backend, events

    backend, events = run(scenario())
    assert backend.hung_up == [9] and events[-1] == ('ended', {'grund': 'abgelehnt'})


def test_gegenseite_legt_auf():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.call(7)
        await manager.on_remote_ended(7, 'beendet')
        return audio, events

    audio, events = run(scenario())
    assert events[-1] == ('ended', {'grund': 'beendet'})
    assert audio.mic.stopped and audio.sinks[0].stopped


def test_ton_der_gegenseite_geht_an_ausgabe_und_echo():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.call(7)
        manager.on_frames(7, bytes(1920))
        manager.on_frames(8, bytes(1920))
        return audio

    audio = run(scenario())
    assert audio.sinks[0].written == [bytes(1920)]
    assert audio.echo.references == [bytes(960)]


def test_mikrofon_geht_durch_echo_an_telegram_und_stumm_sendet_stille():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.call(7)
        loud = b'\x01\x02' * 480
        audio.mic.on_frame(loud)
        await manager.set_mute(True)
        audio.mic.on_frame(loud)
        await asyncio.sleep(0.01)
        return backend, audio, loud

    backend, audio, loud = run(scenario())
    assert audio.echo.processed == [loud, bytes(960)]
    assert backend.sent == [(7, loud), (7, bytes(960))]


def test_shutdown_legt_auf():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.call(7)
        await manager.shutdown()
        return manager, backend, events

    manager, backend, events = run(scenario())
    assert backend.hung_up == [7] and events[-1] == ('ended', {'grund': 'aufgelegt'})
    assert manager.state is State.IDLE


def test_tonausgabe_laesst_sich_nicht_oeffnen():
    manager, backend, audio, events = setup()
    audio.open_error = OSError('kaputt')
    run(manager.call(7))
    assert backend.hung_up == [7] and events[-1] == ('ended', {'grund': 'tonausgabe'})


def test_tonausgabe_faellt_im_gespraech_aus():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.call(7)
        audio.sinks[0].fail = True
        manager.on_frames(7, bytes(1920))
        manager.on_frames(7, bytes(1920))
        await asyncio.sleep(0.05)
        return backend, events

    backend, events = run(scenario())
    assert backend.hung_up == [7]
    assert events[-1] == ('ended', {'grund': 'tonausgabe'}) and types(events).count('ended') == 1


def test_anruf_waehrend_anruf_meldet_fehler():
    async def scenario():
        manager, backend, audio, events = setup()
        await manager.call(7)
        await manager.call(8)
        return backend, events

    backend, events = run(scenario())
    assert backend.started == [7] and events[-1] == ('error', {'text': 'Es läuft schon ein Anruf'})


def test_ring_timeout_standard():
    assert callmanager.RING_TIMEOUT == 45


@pytest.mark.parametrize('method', ['accept', 'decline', 'hangup'])
def test_befehle_ohne_anruf_tun_nichts(method):
    manager, backend, audio, events = setup()
    run(getattr(manager, method)())
    assert events == [] and backend.hung_up == []
