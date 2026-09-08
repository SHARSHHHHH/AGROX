"""Speech-to-text.

Providers:
  - whisper: local openai-whisper (offline, multilingual, auto-detects language)
  - browser: no server work — the frontend used the browser Web Speech API and
             already sent text; this path just echoes.

Whisper handles Tamil/Telugu/Kannada/Malayalam/Hindi/English audio and returns
both the transcript and the detected language, which feeds the NLP pipeline.
"""
from app.core.config import settings

_model = None


def _load():
    global _model
    if _model is None:
        import whisper  # imported lazily so the app runs without it installed
        _model = whisper.load_model(settings.WHISPER_MODEL)
    return _model


def transcribe(audio_path: str) -> dict:
    if settings.STT_PROVIDER.lower() != "whisper":
        return {"text": "", "language": "en",
                "note": "Browser speech mode — text sent directly from client."}
    try:
        model = _load()
        result = model.transcribe(audio_path)
        return {
            "text": result.get("text", "").strip(),
            "language": result.get("language", "en"),
        }
    except Exception as e:
        return {"text": "", "language": "en",
                "error": f"Whisper unavailable: {type(e).__name__}. "
                         f"Install with: pip install openai-whisper"}
