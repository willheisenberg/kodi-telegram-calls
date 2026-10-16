import asyncio
import json
import os
import stat

from server import Server


async def connect(path):
    reader, writer = await asyncio.open_unix_connection(path)
    return reader, writer


async def read_event(reader):
    return json.loads(await asyncio.wait_for(reader.readline(), 2))


def test_puffer_wird_beim_verbinden_nachgeliefert_und_befehle_kommen_an(tmp_path):
    async def scenario():
        received = []

        async def on_command(message):
            received.append(message)

        server = Server(str(tmp_path / 'w.sock'), on_command)
        await server.start()
        server.emit('ready', angemeldet=True)
        reader, writer = await connect(str(tmp_path / 'w.sock'))
        first = await read_event(reader)
        writer.write(b'{"typ": "call", "id": 5}\n')
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.close()
        await writer.wait_closed()
        await server.close()
        return first, received

    first, received = asyncio.run(scenario())
    assert first == {'typ': 'ready', 'angemeldet': True}
    assert received == [{'typ': 'call', 'id': 5}]


def test_unbekannter_befehl_ergibt_fehlerereignis(tmp_path):
    async def scenario():
        async def on_command(message):
            raise AssertionError('darf nicht aufgerufen werden')

        server = Server(str(tmp_path / 'w.sock'), on_command)
        await server.start()
        reader, writer = await connect(str(tmp_path / 'w.sock'))
        writer.write(b'{"typ": "rm_rf"}\nkein json\n')
        events = [await read_event(reader), await read_event(reader)]
        writer.close()
        await writer.wait_closed()
        await server.close()
        return events

    events = asyncio.run(scenario())
    assert [e['typ'] for e in events] == ['error', 'error']
    assert 'unbekannter Befehl' in events[0]['text']


def test_fehler_im_befehl_wird_gemeldet(tmp_path):
    async def scenario():
        async def on_command(message):
            raise RuntimeError('kaputt')

        server = Server(str(tmp_path / 'w.sock'), on_command)
        await server.start()
        reader, writer = await connect(str(tmp_path / 'w.sock'))
        writer.write(b'{"typ": "contacts"}\n')
        event = await read_event(reader)
        writer.close()
        await writer.wait_closed()
        await server.close()
        return event

    assert asyncio.run(scenario()) == {'typ': 'error', 'text': 'contacts: kaputt'}


def test_langer_befehl_blockiert_folgende_nicht(tmp_path):
    async def scenario():
        order = []
        release = asyncio.Event()

        async def on_command(message):
            order.append(message['typ'])
            if message['typ'] == 'call':
                await release.wait()

        server = Server(str(tmp_path / 'w.sock'), on_command)
        await server.start()
        reader, writer = await connect(str(tmp_path / 'w.sock'))
        writer.write(b'{"typ": "call", "id": 1}\n{"typ": "hangup"}\n')
        await writer.drain()
        await asyncio.sleep(0.05)
        release.set()
        writer.close()
        await writer.wait_closed()
        await server.close()
        return order

    assert asyncio.run(scenario()) == ['call', 'hangup']


def test_alter_socket_wird_ersetzt_und_ist_privat(tmp_path):
    path = tmp_path / 'w.sock'
    path.write_text('Rest')

    async def scenario():
        async def on_command(message):
            pass

        server = Server(str(path), on_command)
        await server.start()
        mode = stat.S_IMODE(os.stat(path).st_mode)
        reader, writer = await connect(str(path))
        writer.close()
        await writer.wait_closed()
        await server.close()
        return mode

    assert asyncio.run(scenario()) == 0o600
    assert not path.exists()
