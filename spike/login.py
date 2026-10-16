#!/usr/bin/env python3
"""Einmalige Anmeldung. Fragt Telefonnummer, Code und ggf. 2FA-Passwort ab."""
import asyncio
import os

from common import SESSION, make_client


async def main():
    client = make_client()
    await client.start()
    me = await client.get_me()
    os.chmod(SESSION + '.session', 0o600)
    print(f'Angemeldet als {me.first_name} (id {me.id}). Session: {SESSION}.session')
    await client.disconnect()


asyncio.run(main())
