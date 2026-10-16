import sys

import pytest

import sinks


def collect():
    events = []
    return events, lambda typ, **data: events.append((typ, data))


def test_hdmi_busy_liest_den_alsa_zustand(tmp_path):
    status = tmp_path / 'status'
    status.write_text('closed\n')
    assert sinks.hdmi_busy(str(status)) is False
    status.write_text('state: RUNNING\nowner_pid   : 123\n')
    assert sinks.hdmi_busy(str(status)) is True
    assert sinks.hdmi_busy(str(tmp_path / 'fehlt')) is True


def test_kodi_ausgabe_schreibt_sdp_und_meldet_play_kodi(tmp_path):
    events, emit = collect()
    sdp_path = str(tmp_path / 'anruf.sdp')
    sink = sinks.open_sink(False, sdp_path, emit)
    assert isinstance(sink, sinks.KodiSink)
    assert 'L16/48000/2' in open(sdp_path).read()
    assert events == [('play_kodi', {'sdp_pfad': sdp_path})]
    sink.write(bytes(1920))
    sink.stop()
    assert events[-1] == ('stop_kodi', {})


def test_open_sink_nimmt_alsa_wenn_frei(tmp_path):
    events, emit = collect()
    command = [sys.executable, '-c', 'import sys; sys.stdin.buffer.read()']
    sink = sinks.open_sink(True, str(tmp_path / 'a.sdp'), emit, busy=lambda: False, alsa_command=command)
    assert isinstance(sink, sinks.AlsaSink)
    sink.write(bytes(1920))
    sink.stop()
    assert events == []


def test_open_sink_faellt_bei_belegtem_hdmi_auf_kodi_zurueck(tmp_path):
    events, emit = collect()
    sink = sinks.open_sink(True, str(tmp_path / 'a.sdp'), emit, busy=lambda: True)
    assert isinstance(sink, sinks.KodiSink)
    sink.stop()


def test_open_sink_faellt_zurueck_wenn_aplay_sofort_endet(tmp_path):
    events, emit = collect()
    command = [sys.executable, '-c', 'import sys; sys.stderr.write("Gerät belegt"); sys.exit(1)']
    sink = sinks.open_sink(True, str(tmp_path / 'a.sdp'), emit, busy=lambda: False, alsa_command=command)
    assert isinstance(sink, sinks.KodiSink)
    assert events[0][0] == 'play_kodi'
    sink.stop()


def test_alsa_schreiben_nach_ende_meldet_fehler():
    sink = sinks.AlsaSink(command=[sys.executable, '-c', 'import time; time.sleep(0.4)'])
    sink.start()
    sink._proc.wait()
    with pytest.raises(sinks.SinkError):
        for _ in range(100):
            sink.write(bytes(65536))
    sink.stop()
