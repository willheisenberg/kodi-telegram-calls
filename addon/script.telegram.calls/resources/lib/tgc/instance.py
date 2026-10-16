"""Nur eine Instanz des Add-ons: Kodi startet bei JSON-RPC (z. B. Kore) eine zweite, statt die erste zu zeigen.

Zwei Instanzen teilen sich Socket und Anrufprozess und schließen sich gegenseitig die Fenster.
"""
import fcntl
import os


def acquire(path):
    """Sperrdatei belegen. Gibt den Dateideskriptor zurück oder None, wenn schon eine Instanz läuft.

    flock gilt je geöffneter Datei, deshalb sperrt es auch zwei Instanzen im selben Kodi-Prozess gegeneinander.
    """
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd
