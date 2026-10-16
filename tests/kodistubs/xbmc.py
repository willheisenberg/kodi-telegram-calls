"""Minimale Attrappe von Kodis Modul xbmc, nur damit kodi_ui in Tests importierbar ist."""
LOGINFO, LOGERROR = 1, 3
builtins = []
rpc_results = {}


def log(message, level=LOGINFO):
    pass


def executebuiltin(command, wait=False):
    builtins.append(command)


def executeJSONRPC(request):
    import json
    method = json.loads(request)['method']
    return json.dumps({'result': rpc_results.get(method)})


class Player:
    def __init__(self):
        self.played = []

    def play(self, path, item):
        self.played.append(path)

    def isPlaying(self):
        return bool(self.played)

    def getPlayingFile(self):
        return self.played[-1]

    def stop(self):
        self.played.clear()


class Monitor:
    """Attrappe: Tests setzen on_wait, um Kodis Wartefunktion zu beobachten."""
    on_wait = None

    def abortRequested(self):
        return False

    def waitForAbort(self, timeout=None):
        if Monitor.on_wait is not None:
            return Monitor.on_wait(timeout)
        return False
