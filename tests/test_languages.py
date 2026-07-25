from app.languages import (
    DEFAULT_LANGUAGE_CODE,
    SUPPORTED_LANGUAGES,
    is_supported_language_code,
)


def test_supported_languages_include_default_american_english():
    assert DEFAULT_LANGUAGE_CODE == "a"
    assert SUPPORTED_LANGUAGES[0]["code"] == "a"
    assert "American English" in SUPPORTED_LANGUAGES[0]["label"]


def test_language_code_validation_accepts_known_codes():
    assert is_supported_language_code("a") is True
    assert is_supported_language_code("z") is True


def test_language_code_validation_rejects_unknown_codes():
    assert is_supported_language_code("") is False
    assert is_supported_language_code("xx") is False
