"""Server-side text-to-speech for Tamil, Hindi and English.

WHY THIS EXISTS
---------------
The browser's Web Speech API can only speak a language if the OPERATING SYSTEM
has a voice pack installed for it. On most Android phones and on essentially
every desktop Chrome install, Tamil and Hindi voices are absent. When they are,
`speechSynthesis` does not fail loudly — it silently substitutes the default
voice, which is US English, and reads Devanagari or Tamil text with English
phonetics. That is the "voice only comes in English" symptom.

No amount of frontend work fixes that. You cannot install a system voice from a
web page. The only reliable answer is to synthesise the audio on the SERVER,
where we control what is installed, and send the phone an MP3 it can simply
play. A farmer with no Tamil voice pack still hears Tamil.

The browser path is kept as a fallback for when this service is unavailable,
because a device that DOES have the voice pack gets lower latency from it.

CACHING
-------
Farmers ask overlapping questions and re-play the same answers. Synthesis is
the slow part, so identical (text, language) pairs are cached on disk and
served straight from there afterwards.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from pathlib import Path
from typing import Optional, Tuple

from app.core.config import settings

log = logging.getLogger("agri.tts")

# gTTS language codes. These three are the languages the app fully supports.
TTS_LANGS = {
    "en": {"code": "en", "tld": "co.in", "name": "English (Indian)"},
    "hi": {"code": "hi", "tld": "co.in", "name": "Hindi"},
    "ta": {"code": "ta", "tld": "co.in", "name": "Tamil"},
}

CACHE_DIR = Path(settings.TTS_CACHE_DIR)
_LOCK = threading.Lock()

# Speech engines choke on markdown. A farmer does not want to hear "asterisk
# asterisk bold asterisk asterisk", and bullet characters get read as "dot".
_MD_PATTERNS = [
    (re.compile(r"```.*?```", re.S), " "),      # fenced code blocks
    (re.compile(r"`([^`]*)`"), r"\1"),          # inline code
    (re.compile(r"\*\*([^*]*)\*\*"), r"\1"),    # bold
    (re.compile(r"\*([^*]*)\*"), r"\1"),        # italic
    (re.compile(r"^#{1,6}\s*", re.M), ""),      # headings
    (re.compile(r"^\s*[-•*]\s+", re.M), ""),    # bullets
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),  # links -> link text
    (re.compile(r"[_~>|]"), " "),
    (re.compile(r"\n{2,}"), ". "),
    (re.compile(r"\s{2,}"), " "),
]


def clean_for_speech(text: str) -> str:
    """Strip markdown so the engine reads words, not punctuation."""
    out = text or ""
    for pattern, repl in _MD_PATTERNS:
        out = pattern.sub(repl, out)
    return out.strip()


def _cache_path(text: str, lang: str) -> Path:
    digest = hashlib.sha256(f"{lang}|{text}".encode("utf-8")).hexdigest()[:32]
    return CACHE_DIR / f"{lang}_{digest}.mp3"


def available() -> Tuple[bool, str]:
    """Is server-side synthesis usable? Returns (ok, reason)."""
    if not settings.TTS_ENABLED:
        return False, "TTS_ENABLED is false in backend/.env"
    try:
        import gtts  # noqa: F401
    except ImportError:
        return False, ("gTTS is not installed. Run: pip install gTTS. "
                       "Until then the app falls back to browser voices, "
                       "which cannot speak Tamil or Hindi unless the device "
                       "has those voice packs installed.")
    return True, "ready"


def status() -> dict:
    ok, reason = available()
    cached = 0
    try:
        cached = len(list(CACHE_DIR.glob("*.mp3")))
    except OSError:
        pass
    return {
        "enabled": settings.TTS_ENABLED,
        "ready": ok,
        "reason": reason,
        "languages": {k: v["name"] for k, v in TTS_LANGS.items()},
        "cached_clips": cached,
        "note": ("Server-side synthesis means Tamil and Hindi speech works "
                 "even on devices with no voice packs installed."),
    }


def synthesize(text: str, lang: str = "hi") -> Optional[Path]:
    """Render text to an MP3 and return its path, or None on failure.

    Blocking — call it from a thread. Never raises: a failed synthesis must
    degrade to "no audio", letting the client fall back to browser speech,
    rather than turning an answer the farmer can READ into an error page.
    """
    ok, reason = available()
    if not ok:
        log.info("TTS unavailable: %s", reason)
        return None

    lang = (lang or "hi").strip().lower()[:2]
    if lang not in TTS_LANGS:
        lang = "hi"

    spoken = clean_for_speech(text)
    if not spoken:
        return None
    # gTTS rejects very long inputs; a spoken answer this long is unusable
    # anyway, so truncate at a sentence boundary rather than mid-word.
    if len(spoken) > settings.TTS_MAX_CHARS:
        cut = spoken[:settings.TTS_MAX_CHARS]
        stop = max(cut.rfind("."), cut.rfind("।"), cut.rfind("!"))
        spoken = cut[:stop + 1] if stop > 200 else cut

    path = _cache_path(spoken, lang)
    if path.exists() and path.stat().st_size > 0:
        return path

    with _LOCK:
        if path.exists() and path.stat().st_size > 0:
            return path
        try:
            from gtts import gTTS
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cfg = TTS_LANGS[lang]
            tmp = path.with_suffix(".part")
            gTTS(text=spoken, lang=cfg["code"], tld=cfg["tld"],
                 slow=False).save(str(tmp))
            tmp.rename(path)          # atomic, so a crash never leaves a
            return path               # half-written file in the cache
        except Exception as exc:      # noqa: BLE001
            log.warning("TTS synthesis failed (%s): %s", lang, exc)
            try:
                path.with_suffix(".part").unlink(missing_ok=True)
            except OSError:
                pass
            return None


def clear_cache() -> int:
    removed = 0
    try:
        for f in CACHE_DIR.glob("*.mp3"):
            f.unlink()
            removed += 1
    except OSError as exc:
        log.warning("could not clear TTS cache: %s", exc)
    return removed
