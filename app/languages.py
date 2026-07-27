# Stores the Kokoro language code used as the app's default language.
DEFAULT_LANGUAGE_CODE = "a"

# Lists the languages exposed to the frontend language dropdown.
SUPPORTED_LANGUAGES = [
    # Adds American English with Kokoro language code "a".
    {"label": "🇺🇸 American English", "code": "a"},
    # Adds British English with Kokoro language code "b".
    {"label": "🇬🇧 British English", "code": "b"},
    # Adds Spanish with Kokoro language code "e".
    {"label": "🇪🇸 Spanish", "code": "e"},
    # Adds French with Kokoro language code "f".
    {"label": "🇫🇷 French", "code": "f"},
    # Adds Hindi with Kokoro language code "h".
    {"label": "🇮🇳 Hindi", "code": "h"},
    # Adds Italian with Kokoro language code "i".
    {"label": "🇮🇹 Italian", "code": "i"},
    # Adds Japanese with Kokoro language code "j".
    {"label": "🇯🇵 Japanese", "code": "j"},
    # Adds Brazilian Portuguese with Kokoro language code "p".
    {"label": "🇧🇷 Brazilian Portuguese", "code": "p"},
    # Adds Mandarin Chinese with Kokoro language code "z".
    {"label": "🇨🇳 Mandarin Chinese", "code": "z"},
]

# Builds a set of valid language codes for fast membership checks.
SUPPORTED_LANGUAGE_CODES = {language["code"] for language in SUPPORTED_LANGUAGES}


# Returns whether a requested Kokoro language code is supported by this app.
def is_supported_language_code(language_code: str) -> bool:
    # Checks the provided code against the precomputed set of supported codes.
    return language_code in SUPPORTED_LANGUAGE_CODES
