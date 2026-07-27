# Imports the text-cleaning helper under test.
from app.text import clean_text


# Verifies that hidden thinking blocks are removed from model output.
def test_clean_text_removes_think_blocks_and_trims_whitespace():
    # Creates sample model output with a thinking block and extra whitespace.
    text = "\n  <think>hidden reasoning</think>\n  Final summary.  \n"

    # Cleans the sample text using the production helper.
    result = clean_text(text)

    # Confirms only the final visible summary remains.
    assert result == "Final summary."


# Verifies that normal text is preserved except for surrounding whitespace.
def test_clean_text_preserves_text_without_think_blocks():
    # Confirms the helper trims whitespace without changing the core text.
    assert clean_text("  Keep this text.  ") == "Keep this text."
