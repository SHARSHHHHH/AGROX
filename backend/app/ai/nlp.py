"""Multilingual NLP pipeline:
   language detection -> intent -> entity extraction -> (LLM translation).

Language detection uses Unicode script ranges (fast, offline, reliable for the
6 supported languages). Translation uses the LLM provider so it stays high
quality and swappable. Intent/entity use keyword rules per language so the
agent works even when the LLM is offline.
"""
import re
from app.ai.llm import chat
from app.ml.knowledge import DISEASE_KB, NUTRIENT_KB

LANGS = {"en": "English", "ta": "Tamil", "te": "Telugu",
         "kn": "Kannada", "ml": "Malayalam", "hi": "Hindi"}

# Unicode block ranges for script detection
_SCRIPTS = {
    "ta": (0x0B80, 0x0BFF),
    "te": (0x0C00, 0x0C7F),
    "kn": (0x0C80, 0x0CFF),
    "ml": (0x0D00, 0x0D7F),
    "hi": (0x0900, 0x097F),
}


def detect_language(text: str) -> str:
    counts = {k: 0 for k in _SCRIPTS}
    for ch in text:
        cp = ord(ch)
        for lang, (lo, hi) in _SCRIPTS.items():
            if lo <= cp <= hi:
                counts[lang] += 1
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else "en"


# Intent keywords across languages (lowercased). Extendable.
INTENT_KEYWORDS = {
    "irrigation": ["water", "irrigate", "irrigation", "தண்ணி", "ஊத்த", "నీరు",
                   "ನೀರು", "വെള്ളം", "पानी", "सिंचाई"],
    "disease":    ["disease", "yellow", "spot", "leaf", "இலை", "மஞ்ச", "నోగ",
                   "ರೋಗ", "രോഗം", "बीमारी", "पत्ती", "पीला"],
    "scheme":     ["scheme", "subsidy", "government", "மானிய", "அரசு", "పథకం",
                   "ಯೋಜನೆ", "പദ്ധതി", "योजना", "सब्सिडी", "सरकार"],
    "soil":       ["soil", "nitrogen", "npk", "fertility", "மண்", "நைட்ரஜன்",
                   "మట్టి", "ಮಣ್ಣು", "മണ്ണ്", "मिट्टी", "नाइट्रोजन"],
    "weather":    ["weather", "rain", "forecast", "வானிலை", "மழை", "వాతావరణం",
                   "ಹವಾಮಾನ", "കാലാവസ്ഥ", "मौसम", "बारिश"],
    "fertilizer": ["fertilizer", "fertiliser", "urea", "உரம்", "ఎరువు",
                   "ಗೊಬ್ಬರ", "വളം", "खाद", "उर्वरक"],
    "pest_management": [
        # English
        "pest", "insect", "insects", "bug", "bugs", "aphid", "aphids", "whitefly",
        "whiteflies", "thrips", "borer", "borers", "leaf miner", "leafminer",
        "caterpillar", "caterpillars", "cutworm", "worm", "infestation",
        "infested", "pest attack", "pest control", "mealybug", "mites",
        # Tamil
        "பூச்சி", "பூச்சிகள்", "அசுவினி", "புழு", "தத்துப்பூச்சி",
        # Telugu
        "పురుగు", "పురుగులు", "చీడ", "పేను",
        # Kannada
        "ಕೀಟ", "ಕೀಟಗಳು", "ಹೇನು", "ಹುಳು",
        # Malayalam
        "കീടം", "കീടങ്ങൾ", "പുഴു", "മുഞ്ഞ",
        # Hindi
        "कीट", "कीड़े", "कीड़ा", "माहू", "सुंडी", "इल्ली", "संक्रमण",
    ],
}

CROP_KEYWORDS = {
    "tomato": ["tomato", "தக்காளி", "టమాటా", "ಟೊಮ್ಯಾಟೊ", "തക്കാളി", "टमाटर"],
    "rice":   ["rice", "paddy", "நெல்", "వరి", "ಅಕ್ಕಿ", "നെല്ല്", "चावल", "धान"],
    "chilli": ["chilli", "chili", "மிளகாய்", "మిర్చి", "ಮೆಣಸು", "मिर्च"],
    "onion":  ["onion", "வெங்காயம்", "ఉల్లి", "ಈರುಳ್ಳಿ", "प्याज"],
    "potato": ["potato", "உருளை", "బంగాళా", "ಆಲೂಗಡ್ಡೆ", "आलू"],
}


# Named pests -> canonical PEST_KB key. Multilingual where a common term exists.
PEST_KEYWORDS = {
    "Aphids": ["aphid", "aphids", "மாஉ", "அசுவினி", "పేను", "ಹೇನು", "മുഞ്ഞ", "माहू", "एफिड"],
    "Whiteflies": ["whitefly", "whiteflies", "வெள்ளை ஈ", "తెల్లదోమ", "ಬಿಳಿ ನೊಣ",
                   "വെള്ളീച്ച", "सफेद मक्खी"],
    "Thrips": ["thrips", "த்ரிப்ஸ்", "త్రిప్స్", "ತ್ರಿಪ್ಸ್", "ത്രിപ്സ്", "थ्रिप्स"],
    "Fruit Borers": ["fruit borer", "fruit borers", "காய் புழு", "కాయ తొలుచు",
                     "ಕಾಯಿ ಕೊರಕ", "फल छेदक"],
    "Stem Borers": ["stem borer", "stem borers", "தண்டு துளைப்பான்", "కాండం తొలుచు",
                    "ಕಾಂಡ ಕೊರಕ", "तना छेदक"],
    "Leaf Miners": ["leaf miner", "leafminer", "leaf miners", "இலை சுரங்கப்பூச்சி",
                    "ఆకు తొలుచు", "ಎಲೆ ಕೊರಕ", "पत्ती सुरंगक"],
    "Cutworms": ["cutworm", "cutworms", "வெட்டுப்புழு", "కట్ వార్మ్", "कटवर्म"],
    "Caterpillars": ["caterpillar", "caterpillars", "கம்பளிப்பூச்சி", "గొంగళి పురుగు",
                     "ಕಂಬಳಿ ಹುಳು", " കാറ്റർപില്ലർ", "इल्ली", "सुंडी"],
}


def classify_intent(text: str) -> str:
    t = text.lower()
    scores = {intent: sum(1 for kw in kws if kw in t)
              for intent, kws in INTENT_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def extract_pest(text: str):
    """Return a canonical pest name if one is named in the text, else None."""
    t = text.lower()
    for pest, kws in PEST_KEYWORDS.items():
        if any(kw in t for kw in kws):
            return pest
    return None


def extract_entities(text: str) -> dict:
    t = text.lower()
    crop = None
    for c, kws in CROP_KEYWORDS.items():
        if any(kw in t for kw in kws):
            crop = c
            break
    return {"crop": crop, "pest": extract_pest(text)}


# ---------------------------------------------------------------------------
# Text-based crop-problem detection (diseases & nutrient deficiencies)
# ---------------------------------------------------------------------------
# Same design as PEST_KEYWORDS above: a curated, high-precision phrase list
# per DISEASE_KB / NUTRIENT_KB entry, not a free-text word-overlap search.
# Free-text overlap over "symptoms"/"causes" would match on common filler
# words ("leaf", "warm", "growth") and produce confident-looking nonsense; a
# short list of the phrases a farmer actually types/says is far more precise,
# and it is what identify_pest already does successfully for pests.
#
# HONESTY NOTE: this is keyword matching, not a trained classifier. It is
# used exactly like the pest path — to hand the LLM a short list of GROUNDED
# candidates from the verified knowledge base, always phrased as "possible"
# with a confidence caveat, and always paired with "for a confirmed diagnosis,
# upload a photo". It never invents a disease that is not in DISEASE_KB.
#
# Coverage is strongest in English; a few common regional-language symptom
# words are included for Tamil/Hindi as a best-effort aid, not a guarantee —
# extend these as real farmer phrasing is observed.
DISEASE_SYMPTOM_KEYWORDS = {
    "Early Blight": [
        "concentric ring", "concentric rings", "ring spot", "ring spots",
        "brown spot", "brown spots", "dark brown spot", "target spot",
        "lower leaves turning brown", "older leaves spots",
    ],
    "Late Blight": [
        "water-soaked", "water soaked", "grey-green patch", "gray-green patch",
        "white fungal growth", "white mold under leaf", "rapid collapse",
        "plant collapsing fast", "leaves rotting fast", "blight",
    ],
    "Leaf Mold": [
        "olive mold", "olive-green mold", "velvety mold", "mold underneath leaf",
        "fuzzy underside", "pale yellow spots upper leaf",
    ],
    "Bacterial Spot": [
        "yellow halo", "spots with yellow ring", "water-soaked spots on fruit",
        "small dark spots leaves and fruit",
    ],
    "Powdery Mildew": [
        "white powder", "powdery", "white powdery patches", "white dust on leaves",
        "தூள் பூஞ்சை",   # Tamil: powdery mold (best-effort)
        "सफेद चूर्ण",      # Hindi: white powder (best-effort)
    ],
    "Leaf Curl": [
        "leaf curl", "leaves curling", "curling leaves", "upward curl",
        "crinkled leaves", "crinkling", "curled up leaves",
        "இலை சுருள்",     # Tamil: leaf curl (best-effort)
        "पत्ती मुड़", "पत्तियां मुड़",  # Hindi: leaf curling (best-effort)
    ],
    "Blast": [
        "diamond shaped lesion", "diamond-shaped spot", "grey centre lesion",
        "gray center lesion", "neck rot rice", "panicle blast",
    ],
    "Downy Mildew": [
        "yellow angular patch", "angular yellow spots", "grey growth under leaf",
        "downy mildew",
    ],
    "Anthracnose": [
        "sunken spot on fruit", "sunken dark lesion", "pink spore",
        "black sunken spots fruit",
    ],
    "Mosaic Virus": [
        "mosaic pattern", "mottled leaves", "mottling", "distorted leaves virus",
        "stunted mosaic", "light and dark green patches",
    ],
}

NUTRIENT_SYMPTOM_KEYWORDS = {
    "Nitrogen": [
        "older leaves yellow", "yellowing older leaves", "pale green plant",
        "stunted growth pale", "general yellowing",
    ],
    "Phosphorus": [
        "purplish leaves", "purple leaves", "poor root growth", "reddish purple",
    ],
    "Potassium": [
        "leaf edge scorching", "yellow leaf margins", "brown leaf edges",
        "scorched leaf tips",
    ],
    "Calcium": [
        "blossom end rot", "black spot bottom of tomato", "rot on fruit bottom",
    ],
    "Magnesium": [
        "yellowing between veins", "interveinal yellowing", "veins stay green",
    ],
    "Iron": [
        "young leaves yellow", "new leaves pale yellow", "yellow new growth green veins",
    ],
    "Zinc": [
        "small leaves stunted", "little leaf", "shortened stem internodes",
    ],
}


def match_diseases(text: str, crop: str = None, top_n: int = 2) -> list:
    """Match a free-text symptom description against DISEASE_KB.

    Deterministic keyword match, not a model guess — mirrors extract_pest().
    Returns [] rather than a low-confidence guess when nothing matches, so the
    caller falls back to asking for a photo instead of inventing a diagnosis.
    """
    t = text.lower()
    hits = []
    for disease, phrases in DISEASE_SYMPTOM_KEYWORDS.items():
        info = DISEASE_KB[disease]
        if crop and crop not in info["crops"]:
            continue
        matched = [p for p in phrases if p in t]
        if matched:
            hits.append({"disease": disease, "matched_terms": matched, **info})
    hits.sort(key=lambda h: len(h["matched_terms"]), reverse=True)
    return hits[:top_n]


def match_nutrient_deficiency(text: str, top_n: int = 1) -> list:
    """Match a free-text description against NUTRIENT_KB deficiency symptoms."""
    t = text.lower()
    hits = []
    for nutrient, phrases in NUTRIENT_SYMPTOM_KEYWORDS.items():
        matched = [p for p in phrases if p in t]
        if matched:
            hits.append({"nutrient": nutrient, "matched_terms": matched,
                        "info": NUTRIENT_KB[nutrient]})
    hits.sort(key=lambda h: len(h["matched_terms"]), reverse=True)
    return hits[:top_n]


async def translate(text: str, target_lang: str) -> str:
    """Translate text into the target language using the LLM provider.
    If target is English or provider is offline, returns text unchanged where
    safe (English) or best-effort."""
    if target_lang == "en":
        return text
    lang_name = LANGS.get(target_lang, "English")
    system = (f"You are a precise translator. Translate the user's message into "
              f"{lang_name}. Output ONLY the translation, no notes, no quotes. "
              f"Keep technical crop/agriculture terms clear and simple.")
    return await chat(system, text, temperature=0.1)


# The three languages this deployment is fully translated into. Anything else
# is coerced to Hindi, the primary language here, rather than silently
# falling back to English.
SUPPORTED_LANGS = ("hi", "en", "ta")
DEFAULT_LANG = "hi"


def resolve_language(text: str, ui_language: str = "") -> str:
    """Which language should the ANSWER be written in?

    The farmer's explicit UI choice wins over script detection, always.

    WHY THIS ORDER MATTERS
    ----------------------
    detect_language() reads Unicode script ranges. That works when a farmer
    types in Devanagari, and fails in three very common cases:

      1. Romanised input. "mera fasal kharab ho raha hai" is Hindi typed in
         Latin script. Script detection returns English.
      2. Speech recognition that returns a transliteration rather than native
         script, which Android does for some engines.
      3. A one-word or numeric message ("25 kg?"), which carries no script
         signal at all.

    In every one of those, a farmer who has explicitly set the app to Tamil
    was getting an English answer back. That was the bug: the UI language was
    accepted by the API schema and then thrown away before it reached here.
    """
    choice = (ui_language or "").strip().lower()[:2]
    if choice in SUPPORTED_LANGS:
        return choice

    detected = detect_language(text)
    if detected in SUPPORTED_LANGS:
        return detected

    # A script we do not fully support. Answer in the primary language rather
    # than dropping to English, which no one asked for.
    return DEFAULT_LANG


async def analyze(text: str, ui_language: str = "") -> dict:
    lang = resolve_language(text, ui_language)
    return {
        "language": lang,
        "language_name": LANGS.get(lang, "English"),
        "language_source": ("user_setting"
                            if (ui_language or "").strip().lower()[:2]
                            in SUPPORTED_LANGS else "detected_from_script"),
        "detected_script_language": detect_language(text),
        "intent": classify_intent(text),
        "entities": extract_entities(text),
    }
