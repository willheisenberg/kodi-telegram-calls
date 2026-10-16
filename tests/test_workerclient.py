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
    worker, _ = client(tmp_path, argv=[sys.executable, '-c', 'import sys; sys.exit(3)'])
    with pytest.raises(WorkerError, match='Code 3'):
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
