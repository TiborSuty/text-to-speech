DEFAULT_LANGUAGE_CODE = "a"

SUPPORTED_LANGUAGES = [
    {"label": "🇺🇸 American English", "code": "a"},
    {"label": "🇬🇧 British English", "code": "b"},
    {"label": "🇪🇸 Spanish", "code": "e"},
    {"label": "🇫🇷 French", "code": "f"},
    {"label": "🇮🇳 Hindi", "code": "h"},
    {"label": "🇮🇹 Italian", "code": "i"},
    {"label": "🇯🇵 Japanese", "code": "j"},
    {"label": "🇧🇷 Brazilian Portuguese", "code": "p"},
    {"label": "🇨🇳 Mandarin Chinese", "code": "z"},
]

SUPPORTED_LANGUAGE_CODES = {language["code"] for language in SUPPORTED_LANGUAGES}


def is_supported_language_code(language_code: str) -> bool:
    return language_code in SUPPORTED_LANGUAGE_CODES
