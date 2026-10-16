"""Ersatz für worker/main.py in Tests: Socket, ready-Ereignis, Echo der Befehle, quit."""
import json
import os
import socket
import sys

data = sys.argv[1]
init = json.loads(sys.stdin.readline())
path = os.path.join(data, 'worker.sock')
if os.path.exists(path):
    os.unlink(path)
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(path)
server.listen(1)
conn, _ = server.accept()
conn.sendall((json.dumps({'typ': 'ready', 'init': init}) + '\n').encode())
for line in conn.makefile('rb'):
    message = json.loads(line)
    if message['typ'] == 'quit':
        break
    if message['typ'] == 'crash':
        os._exit(9)
    conn.sendall((json.dumps({'typ': 'echo', 'befehl': message}) + '\n').encode())
conn.close()
