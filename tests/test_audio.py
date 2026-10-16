import audio
import echo
import mic


def test_factory_folgt_den_einstellungen(tmp_path):
    events = []
    factory = audio.AudioFactory({'direkt': False, 'echo': 'daempfen', 'mikrofon': 'plughw:CARD=X,DEV=0'},
                                 str(tmp_path), lambda typ, **d: events.append(typ))
    assert isinstance(factory.make_echo(300), echo.Ducker)
    capture = factory.make_mic(lambda chunk: None)
    assert isinstance(capture, mic.MicCapture) and 'plughw:CARD=X,DEV=0' in capture._command
    sink = factory.open_sink()
    assert events == ['play_kodi'] and (tmp_path / 'anruf.sdp').exists()
    sink.stop()
