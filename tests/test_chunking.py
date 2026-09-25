"""Unit tests for chunking strategy and token estimation."""

import pytest
from src.chunker import estimate_token_count, chunk_markdown
from src.assistant import validate_optibot_response


def test_estimate_token_count():
    assert estimate_token_count("") == 0
    assert estimate_token_count("Hello") >= 1
    # 400 characters is roughly 100 tokens
    text = "word " * 80
    tokens = estimate_token_count(text)
    assert 70 <= tokens <= 130


def test_chunk_markdown_small_text():
    text = "This is a short text that easily fits in one chunk."
    chunks = chunk_markdown(text, max_chunk_tokens=500, overlap_tokens=50)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_markdown_splits_large_text():
    # Generate 5 distinct paragraphs
    paras = [f"Paragraph {i}: " + ("Content details for testing chunking. " * 30) for i in range(1, 6)]
    full_text = "\n\n".join(paras)

    chunks = chunk_markdown(full_text, max_chunk_tokens=200, overlap_tokens=50)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) > 0


def test_validate_optibot_response_compliance():
    # Compliant response: 3 bullets, 1 citation
    good_response = """
To add a YouTube video:
1. Open Files/Assets.
2. Select YouTube App.
3. Paste video URL and Save.

Article URL: https://support.optisigns.com/hc/en-us/articles/360051014713-How-to-Use-YouTube-with-OptiSigns
"""
    v = validate_optibot_response(good_response)
    assert v["is_compliant"] is True
    assert v["bullets_ok"] is True
    assert v["citations_ok"] is True

    # Non-compliant response: 7 bullets
    bad_response = "\n".join([f"- Step {i}" for i in range(1, 8)])
    v2 = validate_optibot_response(bad_response)
    assert v2["bullets_ok"] is False
    assert v2["is_compliant"] is False
