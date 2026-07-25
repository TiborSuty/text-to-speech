from app.text import clean_text


def test_clean_text_removes_think_blocks_and_trims_whitespace():
    text = "\n  <think>hidden reasoning</think>\n  Final summary.  \n"

    result = clean_text(text)

    assert result == "Final summary."


def test_clean_text_preserves_text_without_think_blocks():
    assert clean_text("  Keep this text.  ") == "Keep this text."
