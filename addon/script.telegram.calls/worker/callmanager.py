"""Ablauf eines 1-zu-1-Anrufs: Zustände, Ton und Meldungen an das Add-on.

Ohne Telegram testbar: Telegram steckt hinter dem Backend (tgbackend.py), der
Ton hinter der AudioFactory (audio.py). Gründe in 'ended': aufgelegt, beendet,
abgelehnt, besetzt, keine_antwort, verpasst, abgebrochen, privatsphaere, tonausgabe, fehler.
"""
import asyncio
import enum
import logging

from echo import stereo_to_mono
from pacer import Pacer

log = logging.getLogger('worker.call')

RING_TIMEOUT = 45


class CallFailed(Exception):
    def __init__(self, grund):
        super().__init__(grund)
        self.grund = grund


class State(enum.Enum):
    IDLE = 'idle'
    OUTGOING = 'outgoing'
    INCOMING = 'incoming'
    CONNECTED = 'connected'


class CallManager:
    def __init__(self, backend, emit, audio, name_for, ring_timeout=RING_TIMEOUT):
        self._backend = backend
        self._emit = emit
        self._audio = audio
        self._name_for = name_for
        self._ring_timeout = ring_timeout
        self.state = State.IDLE
        self.peer = None
        self._sink = None
        self._echo = None
        self._mic = None
        self._ring_task = None
        self._pacer = None
        self._generation = 0  # zählt jedes Gesprächsende; erkennt Auflegen während eines await
        self._timeout_task = None
        self._dial_task = None
        self._muted = False
        self._sink_failed = False
        self._loop = None

    # --- Befehle vom Add-on ---------------------------------------------

    async def call(self, user_id):
        if self.state is not State.IDLE:
            self._emit('error', text='Es läuft schon ein Anruf')
            return
        self._loop = asyncio.get_running_loop()
        self.state, self.peer = State.OUTGOING, user_id
        self._emit('outgoing_state', zustand='waehlt')
        self._dial_task = asyncio.current_task()
        try:
            await self._backend.start_call(user_id, self._ring_timeout)
        except CallFailed as e:
            await self._end(e.grund)
            return
        except asyncio.CancelledError:
            return  # hangup() hat aufgelegt und aufgeräumt
        except Exception:
            # Unbekannter Fehler von Telegram: nicht in "Wählt …" hängen bleiben.
            log.exception('Anruf ließ sich nicht aufbauen')
            await self._hang_up_quietly(user_id)
            await self._end('fehler')
            return
        finally:
            self._dial_task = None
        if self.state is State.OUTGOING and self.peer == user_id:
            await self._connected()

    async def accept(self):
        if self.state is not State.INCOMING:
            return
        self._stop_ringing()
        # Dieselbe Ausgabe samt Taktgeber weiterbenutzen: Ein Stopp der Kodi-Wiedergabe hält der KodiMediaBot
        # für ein abgebrochenes Radio und startet es nach 5 s neu.
        user_id = self.peer
        try:
            await self._backend.accept(user_id)
        except CallFailed as e:
            await self._end(e.grund)
            return
        if self.state is State.INCOMING and self.peer == user_id:
            await self._connected()

    async def decline(self):
        if self.state is not State.INCOMING:
            return
        await self._hang_up_quietly(self.peer)
        await self._end('abgelehnt')

    async def hangup(self):
        if self.state not in (State.OUTGOING, State.CONNECTED):
            return
        if self._dial_task is not None:
            self._dial_task.cancel()
        await self._hang_up_quietly(self.peer)
        await self._end('aufgelegt')

    async def set_mute(self, on):
        self._muted = bool(on)

    async def shutdown(self):
        """Beim Beenden des Prozesses: laufenden Anruf sauber auflegen."""
        if self.state is State.IDLE:
            return
        if self._dial_task is not None:
            self._dial_task.cancel()
        await self._hang_up_quietly(self.peer)
        await self._end('aufgelegt')

    # --- Ereignisse von Telegram ----------------------------------------

    async def on_incoming(self, user_id):
        if self.state is not State.IDLE:
            log.info('Zweiter Anruf während eines Gesprächs: besetzt')
            try:
                await self._backend.reject_busy(user_id)
            except Exception:
                log.exception('Zweiten Anruf abweisen fehlgeschlagen')
            return
        self._loop = asyncio.get_running_loop()
        self.state, self.peer = State.INCOMING, user_id
        name = await self._name_for(user_id)
        if self.state is not State.INCOMING or self.peer != user_id:
            return  # während der Namenssuche schon wieder beendet
        self._emit('incoming', id=user_id, name=name)
        self._timeout_task = asyncio.create_task(self._ring_timeout_after(user_id))
        if not await self._ensure_sink():
            return
        self._ring_task = asyncio.create_task(self._audio.ringtone().run(self._pacer))

    def on_ringing(self, user_id):
        if self.state is State.OUTGOING and self.peer == user_id:
            self._emit('outgoing_state', zustand='klingelt')

    async def on_remote_ended(self, user_id, grund):
        # Beim Wählen meldet start_call() den Grund (abgelehnt, besetzt …) genauer.
        if user_id != self.peer or self.state in (State.IDLE, State.OUTGOING):
            return
        await self._end('verpasst' if self.state is State.INCOMING else grund)

    def on_frames(self, user_id, pcm):
        """Ton der Gegenseite (s16le, 48 kHz, Stereo)."""
        if self.state is not State.CONNECTED or user_id != self.peer or self._pacer is None:
            return
        self._pacer.write(pcm)

    def _on_sink_error(self, error):
        """Läuft im Taktgeber-Thread."""
        if not self._sink_failed:
            self._sink_failed = True
            log.error('Tonausgabe ausgefallen: %s', error)
            self._loop.call_soon_threadsafe(lambda: self._loop.create_task(self._fail('tonausgabe')))

    # --- intern ---------------------------------------------------------

    def _on_mic_frame(self, pcm):
        """Läuft im Mikrofon-Thread."""
        echo = self._echo
        if self.state is not State.CONNECTED or echo is None:
            return
        if self._muted:
            pcm = bytes(len(pcm))
        out = echo.process(pcm)
        self._loop.call_soon_threadsafe(self._send_audio, out)

    def _send_audio(self, pcm):
        if self.state is State.CONNECTED:
            self._loop.create_task(self._safe_send(self.peer, pcm))

    async def _safe_send(self, user_id, pcm):
        try:
            await self._backend.send_audio(user_id, pcm)
        except Exception as e:
            log.debug('Mikrofonblock nicht gesendet: %s', e)

    async def _ensure_sink(self):
        if self._sink is not None:
            return True
        generation = self._generation
        try:
            sink = await asyncio.to_thread(self._audio.open_sink)
        except Exception:
            log.exception('Tonausgabe lässt sich nicht öffnen')
            if generation == self._generation:
                await self._fail('tonausgabe')
            return False
        if generation != self._generation:
            # Während des Öffnens aufgelegt oder abgelehnt: sonst bliebe ein Anruf ohne Gegenüber "verbunden".
            await asyncio.to_thread(sink.stop)
            return False
        self._sink = sink
        # Fester 10-ms-Takt in eigenem Thread: Kodi darf nie leerlaufen (pacer.py).
        self._loop = asyncio.get_running_loop()
        self._sink_failed = False
        self._pacer = Pacer(self._sink, on_audio=self._reference, on_error=self._on_sink_error)
        self._pacer.start()
        return True

    async def _connected(self):
        if not await self._ensure_sink():
            return
        self._echo = self._audio.make_echo(self._sink.delay_ms)
        self._muted = False
        self.state = State.CONNECTED
        self._mic = self._audio.make_mic(self._on_mic_frame)
        self._mic.start()
        self._emit('connected')

    def _reference(self, pcm):
        """Was Kodi abspielt, echter Ton wie Stille, ist die Referenz der Echounterdrückung."""
        echo = self._echo
        if echo is not None:
            echo.add_reference(stereo_to_mono(pcm))

    async def _ring_timeout_after(self, user_id):
        await asyncio.sleep(self._ring_timeout)
        if self.state is State.INCOMING and self.peer == user_id:
            self._timeout_task = None  # nicht sich selbst in _end() abbrechen
            await self._hang_up_quietly(user_id)
            await self._end('verpasst')

    async def _fail(self, grund):
        if self.state is State.IDLE:
            return
        await self._hang_up_quietly(self.peer)
        await self._end(grund)

    async def _hang_up_quietly(self, user_id):
        try:
            await self._backend.hang_up(user_id)
        except Exception:
            log.exception('Auflegen fehlgeschlagen')

    def _stop_ringing(self):
        for task in (self._ring_task, self._timeout_task):
            if task is not None:
                task.cancel()
        self._ring_task = self._timeout_task = None

    async def _end(self, grund):
        if self.state is State.IDLE:
            return
        self._generation += 1
        self._stop_ringing()
        mic, pacer, sink = self._mic, self._pacer, self._sink
        self._mic = self._pacer = self._sink = self._echo = None
        self.state, self.peer = State.IDLE, None
        if mic is not None:
            await asyncio.to_thread(mic.stop)
        if pacer is not None:
            await asyncio.to_thread(pacer.stop)
        if sink is not None:
            await asyncio.to_thread(sink.stop)
        self._emit('ended', grund=grund)
