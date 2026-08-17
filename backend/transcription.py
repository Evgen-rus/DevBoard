"""Транскрибация аудио через gpt-4o-mini-transcribe. Отдельного сервиса нет — это один модуль backend."""

from __future__ import annotations

from io import BytesIO

from openai import OpenAI

MAX_AUDIO_BYTES = 25 * 1024 * 1024
ALLOWED_AUDIO_TYPES = {
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/m4a": ".m4a",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/wav": ".wav",
    "audio/webm": ".webm",
    "audio/x-m4a": ".m4a",
    "audio/x-wav": ".wav",
    "video/webm": ".webm",
    "video/mp4": ".m4a",
}


class TranscriptionError(ValueError):
    """Аудио нельзя расшифровать."""


def suffix_for_audio(filename: str, content_type: str) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized in ALLOWED_AUDIO_TYPES:
        return ALLOWED_AUDIO_TYPES[normalized]
    name = (filename or "").lower()
    for suffix in {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".opus", ".aac", ".flac"}:
        if name.endswith(suffix):
            return suffix
    raise TranscriptionError("Неподдерживаемый тип аудио")


def transcribe_audio(
    data: bytes,
    *,
    filename: str,
    content_type: str,
    api_key: str,
    model: str = "gpt-4o-mini-transcribe",
    language: str = "ru",
) -> str:
    if not api_key.strip():
        raise TranscriptionError("OPENAI_API_KEY не задан")
    if not data:
        raise TranscriptionError("Пустой аудиофайл")
    if len(data) > MAX_AUDIO_BYTES:
        raise TranscriptionError("Аудио больше 25 МБ")
    suffix = suffix_for_audio(filename, content_type)
    buffer = BytesIO(data)
    buffer.name = filename if "." in filename else f"audio{suffix}"
    client = OpenAI(api_key=api_key)
    try:
        result = client.audio.transcriptions.create(
            model=model,
            file=buffer,
            language=language or "ru",
        )
    except Exception as exc:
        raise TranscriptionError(f"Не удалось расшифровать аудио: {exc}") from exc
    text = (getattr(result, "text", None) or "").strip()
    if not text:
        raise TranscriptionError("Модель вернула пустой транскрипт")
    return text
