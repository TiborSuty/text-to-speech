# Imports the language constants and validator under test.
from app.languages import (
    # Imports the default language code configured by the app.
    DEFAULT_LANGUAGE_CODE,
    # Imports the list of languages exposed to the frontend.
    SUPPORTED_LANGUAGES,
    # Imports the helper that validates language codes.
    is_supported_language_code,
)


# Verifies that the configured default language is American English.
def test_supported_languages_include_default_american_english():
    # Confirms the default language code is Kokoro's American English code.
    assert DEFAULT_LANGUAGE_CODE == "a"
    # Confirms the first supported language matches the default code.
    assert SUPPORTED_LANGUAGES[0]["code"] == "a"
    # Confirms the first supported language label names American English.
    assert "American English" in SUPPORTED_LANGUAGES[0]["label"]


# Verifies that known language codes pass validation.
def test_language_code_validation_accepts_known_codes():
    # Confirms American English is accepted.
    assert is_supported_language_code("a") is True
    # Confirms Mandarin Chinese is accepted.
    assert is_supported_language_code("z") is True


# Verifies that unknown language codes fail validation.
def test_language_code_validation_rejects_unknown_codes():
    # Confirms an empty code is rejected.
    assert is_supported_language_code("") is False
    # Confirms a code not in the supported list is rejected.
    assert is_supported_language_code("xx") is False
