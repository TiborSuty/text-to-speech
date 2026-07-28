DEFAULT_LANGUAGE_CODE = "a"


VOICE_IDS_BY_LANGUAGE = {
    "a": (
        "af_heart",
        "af_alloy",
        "af_aoede",
        "af_bella",
        "af_jessica",
        "af_kore",
        "af_nicole",
        "af_nova",
        "af_river",
        "af_sarah",
        "af_sky",
        "am_adam",
        "am_echo",
        "am_eric",
        "am_fenrir",
        "am_liam",
        "am_michael",
        "am_onyx",
        "am_puck",
        "am_santa",
    ),
    "b": (
        "bf_alice",
        "bf_emma",
        "bf_isabella",
        "bf_lily",
        "bm_daniel",
        "bm_fable",
        "bm_george",
        "bm_lewis",
    ),
    "e": ("ef_dora", "em_alex", "em_santa"),
    "f": ("ff_siwis",),
    "h": ("hf_alpha", "hf_beta", "hm_omega", "hm_psi"),
    "i": ("if_sara", "im_nicola"),
    "j": ("jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo"),
    "p": ("pf_dora", "pm_alex", "pm_santa"),
    "z": (
        "zf_xiaobei",
        "zf_xiaoni",
        "zf_xiaoxiao",
        "zf_xiaoyi",
        "zm_yunjian",
        "zm_yunxi",
        "zm_yunxia",
        "zm_yunyang",
    ),
}


DEFAULT_VOICE_BY_LANGUAGE = {
    "a": "af_heart",
    "b": "bf_emma",
    "e": "ef_dora",
    "f": "ff_siwis",
    "h": "hf_alpha",
    "i": "if_sara",
    "j": "jf_alpha",
    "p": "pf_dora",
    "z": "zf_xiaoxiao",
}


LANGUAGE_LABELS = {
    "a": "🇺🇸 American English",
    "b": "🇬🇧 British English",
    "e": "🇪🇸 Spanish",
    "f": "🇫🇷 French",
    "h": "🇮🇳 Hindi",
    "i": "🇮🇹 Italian",
    "j": "🇯🇵 Japanese",
    "p": "🇧🇷 Brazilian Portuguese",
    "z": "🇨🇳 Mandarin Chinese",
}


def voice_label(voice_id: str) -> str:

    name = voice_id.split("_", maxsplit=1)[1].replace("_", " ").title()

    gender = "Female" if voice_id[1] == "f" else "Male"

    return f"{name} ({gender})"


def voice_option(voice_id: str) -> dict[str, str]:

    return {"id": voice_id, "label": voice_label(voice_id)}


SUPPORTED_LANGUAGES = [
    {
        "label": LANGUAGE_LABELS[language_code],
        "code": language_code,
        "default_voice": DEFAULT_VOICE_BY_LANGUAGE[language_code],
        "voices": [
            voice_option(voice_id) for voice_id in VOICE_IDS_BY_LANGUAGE[language_code]
        ],
    }
    for language_code in LANGUAGE_LABELS
]


SUPPORTED_LANGUAGE_CODES = set(VOICE_IDS_BY_LANGUAGE)


SUPPORTED_VOICE_IDS_BY_LANGUAGE = {
    language_code: set(voice_ids)
    for language_code, voice_ids in VOICE_IDS_BY_LANGUAGE.items()
}


def is_supported_language_code(language_code: str) -> bool:

    return language_code in SUPPORTED_LANGUAGE_CODES


def get_default_voice(language_code: str) -> str | None:

    return DEFAULT_VOICE_BY_LANGUAGE.get(language_code)


def is_supported_voice(language_code: str, voice_id: str) -> bool:

    return voice_id in SUPPORTED_VOICE_IDS_BY_LANGUAGE.get(language_code, set())
