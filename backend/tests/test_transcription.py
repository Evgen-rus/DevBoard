from transcription import TranscriptionError, suffix_for_audio


def test_suffix_for_browser_recording() -> None:
    assert suffix_for_audio("voice.webm", "video/webm") == ".webm"
    assert suffix_for_audio("note.mp3", "audio/mpeg") == ".mp3"


def test_rejects_unknown_audio_type() -> None:
    try:
        suffix_for_audio("note.txt", "text/plain")
    except TranscriptionError:
        return
    raise AssertionError("ожидалась ошибка")
