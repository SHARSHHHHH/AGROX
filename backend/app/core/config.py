"""Central configuration for the Gemini-powered application."""
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_FILE)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    APP_NAME: str = "Sustainable Agriculture AI Advisory Platform"

    # NOTE the "./" — this was a RELATIVE path, resolved against whatever
    # directory uvicorn was launched from. Start the server from backend/ and
    # you get backend/agri.db; start it from the project root and you silently
    # get a DIFFERENT, empty database. That is a very confusing way to "lose"
    # your data. resolve_database_url() below anchors it to backend/ instead.
    DATABASE_URL: str = "sqlite:///./agri.db"
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7

    # Google Gemini — used for conversational AI, NLP/translation and vision.
    # --- Provider selection -------------------------------------------
    # "groq"   = Groq cloud API (fastest — LPU inference, ~0.3-1s replies)
    # "gemini" = Google Gemini API
    # "qwen"   = local Qwen2.5 via transformers (offline, no API key, but
    #            slow on CPU — this is what you were seeing before)
    LLM_PROVIDER: str = "groq"

    # --- Groq -----------------------------------------------------------
    # Create a free key at https://console.groq.com/keys
    GROQ_API_KEY: str = ""
    # openai/gpt-oss-120b: best quality/speed balance for this app.
    # For even faster (slightly less capable) replies try
    # "openai/gpt-oss-20b". See https://console.groq.com/docs/models
    # Verified against https://console.groq.com/docs/models (Sept 2026).
    # gpt-oss-20b runs at ~1000 tok/s vs ~500 for the 120B, is production
    # tier, and costs half. It is only rephrasing facts the deterministic
    # engines already computed, so the larger model bought nothing.
    # NOTE: llama-3.1-8b-instant is Enterprise-only ("contact sales") and is
    # NOT usable on a standard account.
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    # A farmer answer is 3-5 sentences. Generation latency is roughly linear
    # in output tokens, so 1024 was paying for a page and a half nobody read.
    GROQ_MAX_OUTPUT_TOKENS: int = 350
    # Timeouts are no longer retried, so this is the WORST case wait, not a
    # third of it. Beyond ~12s a farmer on a phone has already given up.
    GROQ_TIMEOUT_S: int = 12

    # --- Local Qwen ---------------------------------------------------
    QWEN_MODEL: str = "Qwen/Qwen2.5-1.5B-Instruct"
    # Main latency control on CPU: generation time is roughly linear in output
    # length. Our answers are short because the facts are computed elsewhere.
    QWEN_MAX_NEW_TOKENS: int = 200
    # Hard ceiling on one generation. A CPU-only laptop needs headroom; a
    # hung generation must surface as an error, not an indefinite hang.
    QWEN_TIMEOUT_S: int = 120

    # --- Vision -------------------------------------------------------
    # "gemini" = Gemini vision  |  "huggingface" = local HF vision model
    VISION_PROVIDER: str = "groq"

    # Groq vision (Llama 4 multimodal). Reuses GROQ_API_KEY.
    # Groq retires vision models regularly, so this is configurable rather
    # than hardcoded; a wrong id returns an explicit 404 naming this setting.
    GROQ_VISION_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    # Longer than the text timeout: an image round trip includes upload.
    GROQ_VISION_TIMEOUT_S: int = 60
    GROQ_VISION_MAX_TOKENS: int = 700
    HF_VISION_MODEL: str = "Kathir56/plant-disease-tamilnadu"

    # Image-classifier softmax is badly calibrated: a photo of a dog still
    # scores 0.95 on some leaf class. Three independent gates must pass before
    # a prediction is accepted, so an unclear photo returns "uncertain"
    # instead of a confident wrong diagnosis.
    HF_VISION_MIN_CONFIDENCE: float = 0.60   # top-1 probability
    HF_VISION_MIN_MARGIN: float = 0.15       # top1 - top2 separation
    HF_VISION_MAX_ENTROPY: float = 0.55      # 0=certain, 1=uniform guess

    # If the configured vision provider cannot LOAD (model not downloaded,
    # missing dependency, no API key), should we try the other one?
    # Set false to guarantee no request ever leaves your machine — useful when
    # the network blocks Google anyway, or when you want zero API keys.
    VISION_ALLOW_FALLBACK: bool = True

    # Cosine-similarity threshold for resolving an unfamiliar pest label to
    # the curated knowledge base.
    PEST_SEMANTIC_MATCH_THRESHOLD: float = 0.78

    # --- Data sources -------------------------------------------------
    # When true, market/fertilizer services may return clearly MOCK-tagged
    # sample rows for demos. In production leave this false so the services
    # return an explicit "data unavailable" instead of invented numbers.
    ALLOW_MOCK_MARKET_DATA: bool = True

    # --- data.gov.in (AGMARKNET mandi prices) -------------------------
    # SERVER SIDE ONLY. Never returned in a response body, never sent to the
    # browser. The React app calls our /api/market-prices, which calls this.
    DATA_GOV_API_KEY: str = ""
    DATA_GOV_RESOURCE_ID: str = "9ef84268-d588-465a-a308-a864a43d0070"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.7-flash"
    VISION_MODEL: str = "gemini-3.7-flash"

    # Cap the answer length. Farmer-facing replies are short; without a cap a
    # reasoning model can run long, which costs both latency and tokens.
    GEMINI_MAX_OUTPUT_TOKENS: int = 1024

    # Reasoning ("thinking") budget in tokens for gemini-3.7-flash.
    #   0   = thinking disabled, fastest, best for short grounded answers
    #   512 = light reasoning
    #   -1  = let the model decide (slowest, and what caused the long waits)
    # Our own engines compute the agronomic facts, so the model is mostly
    # phrasing them and does not need a deep chain of thought.
    GEMINI_THINKING_BUDGET: int = 0

    # Speech-to-text remains local/browser based; it is independent of the LLM.
    STT_PROVIDER: str = "whisper"
    WHISPER_MODEL: str = "base"

    WEATHER_API_KEY: str = ""
    WEATHER_API_URL: str = "https://api.open-meteo.com/v1/forecast"

    # --- Google Earth Engine / Sentinel-2 -----------------------------
    # SERVER SIDE ONLY. Exactly like DATA_GOV_API_KEY above: these values are
    # read inside app/services/satellite.py, are never placed in a response
    # body, and never reach the browser. React calls /api/satellite/*, which
    # calls Earth Engine on the server.
    #
    # NOTHING IS DOWNLOADED. Every reduction runs on Google's servers and only
    # summary statistics (a few dozen floats) cross the network. There is no
    # export, no GeoTIFF, and no imagery cache on disk.
    GEE_ENABLED: bool = True
    GEE_PROJECT: str = ""

    # Credentials, in priority order. Leave all three blank to use the
    # credentials `earthengine authenticate` already stored for this user.
    GEE_SERVICE_ACCOUNT_JSON: str = ""   # raw key JSON (containers, CI)
    GEE_SERVICE_ACCOUNT_FILE: str = ""   # path to a key file
    GEE_SERVICE_ACCOUNT_EMAIL: str = ""  # informational only

    GEE_COLLECTION: str = "COPERNICUS/S2_SR_HARMONIZED"
    GEE_SCALE_M: int = 10                # Sentinel-2 red/NIR native resolution

    # Field footprint. A circle of this radius around the farmer's point.
    # 100 m ~= 3.14 ha, which is a sensible default for an Indian smallholding
    # and comfortably larger than GPS error.
    GEE_BUFFER_M: int = 100

    # Scene-level metadata filter: skip passes that are mostly cloud before
    # doing any pixel work. The per-pixel SCL + cloud-probability mask is what
    # actually protects the numbers; this only saves computation.
    GEE_MAX_CLOUD_PCT: int = 60
    # Per-pixel cloud probability ceiling (MSK_CLDPRB, 0-100).
    GEE_MAX_PIXEL_CLOUD_PROB: int = 30
    # A pass is only used if at least this fraction of the FIELD is cloud-free.
    GEE_MIN_VALID_FRACTION: float = 0.40

    GEE_LOOKBACK_DAYS: int = 30          # how far back to hunt for a clear pass
    GEE_STALE_AFTER_DAYS: int = 12       # older than this is flagged as stale
    GEE_MAX_IMAGES_PER_QUERY: int = 12   # scenes reduced per NDVI request
    GEE_MAX_SERIES_MONTHS: int = 24
    GEE_MAX_PIXELS: int = 10_000_000

    # Sentinel-2 revisits every ~5 days, so re-querying an unchanged field
    # every few minutes burns quota for an identical answer.
    GEE_CACHE_TTL_S: int = 21600         # 6 h for a good observation
    GEE_SERIES_CACHE_TTL_S: int = 86400  # 24 h for a monthly series
    GEE_NO_OBS_CACHE_TTL_S: int = 3600   # 1 h when every pass was cloudy
    GEE_ERROR_CACHE_TTL_S: int = 600     # 10 min on error, so a blip recovers

    GEE_TIMEOUT_S: int = 60

    # How long the CROP ADVISOR may spend on satellite context before giving
    # up. Deliberately tiny: the observation is context only and never changes
    # the ranking, so it must never be the reason a farmer waits. In practice
    # this only succeeds on a warm cache, which is exactly the intent.
    # DEMO_FAST_MODE: skip every optional network leg entirely.
    #
    # The crop ranking itself is pure arithmetic over MP_CROPS and needs no
    # network at all — measured at 1.9 ms. Everything that can make a page
    # wait is optional enrichment: weather, satellite, mandi prices.
    #
    # With this on, those are not called. Not shortened, not retried — not
    # called. The ranking is still computed from the farmer's real soil,
    # season and rotation, so it still changes when the inputs change; it
    # simply loses the garnish it never needed.
    #
    # Turn it on for a demo or a poor connection. Turn it off in the field,
    # where a farmer benefits from live weather and satellite context.
    DEMO_FAST_MODE: bool = False

    ADVISOR_SATELLITE_BUDGET_S: float = 2.5

    # Same reasoning for market prices: a 12% weight must never cost a minute.
    # data.gov.in retries 3x at a 20s read timeout (~65s worst case).
    ADVISOR_MARKET_BUDGET_S: float = 8.0
    ADVISOR_WEATHER_BUDGET_S: float = 6.0

    # /api/farm/profile is called on page MOUNT by several screens, so it is
    # on the critical path for how fast the app feels. Both legs are optional
    # context that already degrade to "unavailable" cleanly.
    PROFILE_WEATHER_BUDGET_S: float = 5.0
    PROFILE_SATELLITE_BUDGET_S: float = 3.0

    # /api/alerts is polled from the alerts page, so both legs are felt on
    # every load. Satellite alerts simply appear on the next poll if skipped.
    ALERTS_WEATHER_BUDGET_S: float = 5.0
    ALERTS_SATELLITE_BUDGET_S: float = 3.0
    GEE_MAX_WORKERS: int = 4

    # --- Server-side text to speech -----------------------------------
    # The browser can only speak a language the DEVICE has a voice pack for,
    # and Tamil/Hindi packs are absent on most phones. Synthesising on the
    # server means those languages work everywhere.
    # --- Browser push notifications -----------------------------------
    # Alerts are ALWAYS stored in-app; push is an extra nudge. With no VAPID
    # keys the app degrades to in-app only rather than erroring.
    # Generate a key pair with:
    #   python -c "from py_vapid import Vapid01; v=Vapid01(); v.generate_keys(); \
    #              print(v.private_key_pem(), v.public_key_pem())"
    PUSH_ENABLED: bool = True
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_CONTACT_EMAIL: str = "admin@example.com"

    TTS_ENABLED: bool = True
    TTS_CACHE_DIR: str = "tts_cache"
    TTS_MAX_CHARS: int = 2000

    DEMO_MODE: bool = True


def _resolve_database_url(url: str) -> str:
    """Anchor a relative SQLite path to the backend directory.

    Without this, the database you get depends on your current working
    directory, so running uvicorn from the wrong folder looks exactly like
    "all my data disappeared". Absolute URLs and non-SQLite URLs pass through
    untouched.
    """
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return url

    path = url[len(prefix):]
    if path.startswith("/") or (len(path) > 1 and path[1] == ":"):
        return url                      # already absolute (POSIX or Windows)

    backend_dir = Path(__file__).resolve().parents[2]
    return prefix + str((backend_dir / path.lstrip("./")).resolve())


settings = Settings()
settings.DATABASE_URL = _resolve_database_url(settings.DATABASE_URL)
