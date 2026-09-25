"""Unit tests for scraper and markdown normalization."""

import pytest
from src.scraper import slugify, clean_html_to_markdown


def test_slugify():
    assert slugify("How to Use YouTube with OptiSigns!") == "how-to-use-youtube-with-optisigns"
    assert slugify("  Extra   Spaces  and Symbols @#$% ") == "extra-spaces-and-symbols"
    assert slugify("Bảng Điều Khiển Digital Signage") == "bang-dieu-khien-digital-signage"
    assert slugify("") == "untitled"


def test_clean_html_to_markdown_removes_scripts_and_styles():
    html = """
    <div>
        <script>alert('malicious')</script>
        <style>body { color: red; }</style>
        <h2>Heading Two</h2>
        <p>This is a normal paragraph with a <a href="https://example.com">link</a>.</p>
    </div>
    """
    md = clean_html_to_markdown(html, title="Test Article", html_url="https://example.com/art-1")

    assert "# Test Article" in md
    assert "Article URL: https://example.com/art-1" in md
    assert "alert('malicious')" not in md
    assert "color: red" not in md
    assert "## Heading Two" in md
    assert "[link](https://example.com)" in md


def test_clean_html_to_markdown_preserves_lists_and_formatting():
    html = """
    <h3>Steps to Configure</h3>
    <ul>
        <li>Step 1: Open Settings</li>
        <li>Step 2: Enter <code>API_KEY</code></li>
    </ul>
    """
    md = clean_html_to_markdown(html, title="Steps", html_url="https://example.com/steps")
    assert "### Steps to Configure" in md
    assert "Step 1: Open Settings" in md
    assert "`API_KEY`" in md
