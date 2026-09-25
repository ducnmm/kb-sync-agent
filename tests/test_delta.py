"""Unit tests for incremental delta detection and state tracking."""

import pytest
from pathlib import Path
from src.delta_sync import (
    compute_text_hash,
    detect_delta,
    update_sync_state_records,
)


def test_compute_text_hash():
    h1 = compute_text_hash("Hello World")
    h2 = compute_text_hash("Hello World")
    h3 = compute_text_hash("Different Content")

    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64  # SHA-256 length


def test_detect_delta_categories(tmp_path):
    # Setup test file
    file1 = tmp_path / "art1.md"
    file1.write_text("Original content of article 1", encoding="utf-8")

    file2 = tmp_path / "art2.md"
    file2.write_text("Content of article 2", encoding="utf-8")

    scraped = [
        {"id": 1, "file_path": str(file1), "title": "Art 1", "slug": "art-1", "filename": "art1.md"},
        {"id": 2, "file_path": str(file2), "title": "Art 2", "slug": "art-2", "filename": "art2.md"},
    ]

    # Run 1: empty state -> all added
    added, updated, skipped = detect_delta(scraped, current_state={})
    assert len(added) == 2
    assert len(updated) == 0
    assert len(skipped) == 0

    # Save state
    state = update_sync_state_records({}, added)

    # Run 2: identical files -> all skipped
    added2, updated2, skipped2 = detect_delta(scraped, current_state=state)
    assert len(added2) == 0
    assert len(updated2) == 0
    assert len(skipped2) == 2

    # Run 3: modify file 1 -> file 1 updated, file 2 skipped
    file1.write_text("MODIFIED content of article 1", encoding="utf-8")
    added3, updated3, skipped3 = detect_delta(scraped, current_state=state)
    assert len(added3) == 0
    assert len(updated3) == 1
    assert updated3[0]["id"] == 1
    assert len(skipped3) == 1
    assert skipped3[0]["id"] == 2
