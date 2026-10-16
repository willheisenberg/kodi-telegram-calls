import os
import queue
import sys

import pytest

from tgc.workerclient import WorkerClient, WorkerError

FAKE = os.path.join(os.path.dirname(__file__), 'fake_worker.py')


def client(tmp_path, argv=None, **kwargs):
    events = queue.Queue()
    worker = WorkerClient(argv or [sys.executable, FAKE, str(tmp_path)], {'api_id': 1},
                          str(tmp_path / 'worker.sock'), events.put, **kwargs)
    return worker, events


def test_start_liefert_ready_mit_init_daten(tmp_path):
    worker, events = client(tmp_path)
    worker.start()
    assert events.get(timeout=5) == {'typ': 'ready', 'init': {'api_id': 1}}
    worker.send('call', id=5)
    assert events.get(timeout=5) == {'typ': 'echo', 'befehl': {'typ': 'call', 'id': 5}}
    worker.stop()


def test_quit_beendet_prozess(tmp_path):
    worker, events = client(tmp_path)
    worker.start()
    events.get(timeout=5)
    proc = worker._proc
    worker.stop()
    assert proc.poll() == 0
    with pytest.raises(queue.Empty):
        events.get(timeout=0.3)  # kein _lost bei gewolltem Ende


def test_absturz_meldet_lost(tmp_path):
    worker, events = client(tmp_path)
    worker.start()
    events.get(timeout=5)
    worker.send('crash')
    assert events.get(timeout=5) == {'typ': '_lost'}
    worker.stop()


def test_sofortiges_ende_wird_als_fehler_gemeldet(tmp_path):
    worker, _ = client(tmp_path, argv=[sys.executable, '-c', 'import sys; sys.exit(2)'])
    with pytest.raises(WorkerError, match='Code 2'):
        worker.start()


def test_zeitueberschreitung(tmp_path):
    worker, _ = client(tmp_path, argv=[sys.executable, '-c', 'import time; time.sleep(30)'], timeout=0.5)
    with pytest.raises(WorkerError, match='antwortet nicht'):
        worker.start()


def test_log_datei_ist_privat(tmp_path):
    log = tmp_path / 'worker.log'
    worker, events = client(tmp_path, log_path=str(log))
    worker.start()
    events.get(timeout=5)
    worker.stop()
    assert oct(os.stat(log).st_mode & 0o777) == '0o600'


def test_start_laesst_sich_abbrechen(tmp_path):
    """Kodi gibt 5 s zum Beenden; das Warten auf den Anrufprozess muss darauf reagieren."""
    import time

    worker, _ = client(tmp_path, argv=[sys.executable, '-c', 'import time; time.sleep(30)'], timeout=20)
    started = time.monotonic()
    with pytest.raises(WorkerError, match='abgebrochen'):
        worker.start(should_abort=lambda: time.monotonic() - started > 0.3)
    assert time.monotonic() - started < 2


def test_start_wartet_bis_die_alte_sperre_frei_ist(tmp_path):
    """Exit-Code 3 heißt: der alte Anrufprozess hält die Sperre noch. Kurz warten und neu starten."""
    marker = tmp_path / 'erster-versuch'
    script = (f'import os, runpy, sys\n'
              f'if not os.path.exists({str(marker)!r}):\n'
              f'    open({str(marker)!r}, "w").close(); sys.exit(3)\n'
              f'sys.argv = [{FAKE!r}, {str(tmp_path)!r}]\n'
              f'runpy.run_path({FAKE!r}, run_name="__main__")\n')
    worker, events = client(tmp_path, argv=[sys.executable, '-c', script])
    worker.start()
    assert events.get(timeout=5)['typ'] == 'ready'
    worker.stop()
