"""Scraper and HTML to clean Markdown normalization module."""

import re
import unicodedata
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from src.config import (
    ZENDESK_API_URL,
    ZENDESK_SEARCH_URL,
    ARTICLES_LIMIT,
    ARTICLES_DIR,
)

logger = logging.getLogger(__name__)

# Essential articles that must be present for required verification questions
ESSENTIAL_ARTICLE_IDS = [
    360051014713,  # How to Use YouTube with OptiSigns
]


def slugify(text: str) -> str:
    """Normalize and convert text into a clean filesystem-friendly slug."""
    text = text.replace("đ", "d").replace("Đ", "d")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    slug = re.sub(r"[-\s]+", "-", text)
    return slug or "untitled"


def clean_html_to_markdown(html_content: str, title: str, html_url: str) -> str:
    """Normalize HTML and convert to clean Markdown preserving headings, links, and code."""
    if not html_content:
        return f"# {title}\n\nArticle URL: {html_url}\n\n*No content available.*"

    soup = BeautifulSoup(html_content, "html.parser")

    # Remove script, style, iframe, form, and comment tags
    for tag in soup(["script", "style", "iframe", "form", "noscript"]):
        tag.decompose()

    # Remove Zendesk UI boilerplate or metadata classes if present
    for bad_class in ["article-author", "article-votes", "article-comments", "sidenav", "breadcrumbs"]:
        for el in soup.find_all(class_=re.compile(bad_class, re.I)):
            el.decompose()

    # Convert to Markdown with preserved headings and lists
    markdown_body = md(
        str(soup),
        heading_style="ATX",  # Uses #, ##, ###
        bullets="-",
        strip=["meta"],
    )

    # Clean redundant whitespace while preserving paragraph breaks
    markdown_body = re.sub(r"\n{3,}", "\n\n", markdown_body).strip()

    # Structured Markdown header with Title and canonical Article URL
    full_markdown = f"# {title}\n\nArticle URL: {html_url}\n\n{markdown_body}\n"
    return full_markdown


def fetch_article_by_id(article_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single article by ID from Zendesk Help Center API."""
    url = f"https://support.optisigns.com/api/v2/help_center/en-us/articles/{article_id}.json"
    headers = {"User-Agent": "kb-sync-agent/1.0"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json().get("article")
        logger.warning(f"Failed to fetch article {article_id}: status {response.status_code}")
    except Exception as e:
        logger.warning(f"Error fetching article {article_id}: {e}")
    return None


def fetch_articles(limit: int = ARTICLES_LIMIT) -> List[Dict[str, Any]]:
    """
    Fetch >= limit articles from the Zendesk Help Center API.
    Guarantees inclusion of required verification articles (e.g. YouTube).
    """
    headers = {"User-Agent": "kb-sync-agent/1.0"}
    articles: List[Dict[str, Any]] = []
    seen_ids = set()

    # 1. Fetch essential articles first
    for art_id in ESSENTIAL_ARTICLE_IDS:
        art = fetch_article_by_id(art_id)
        if art and art.get("body"):
            articles.append(art)
            seen_ids.add(art["id"])

    # 2. Paginate through Zendesk API to reach the desired limit
    page = 1
    per_page = 30
    while len(articles) < limit:
        url = f"{ZENDESK_API_URL}?page={page}&per_page={per_page}&sort_by=position&sort_order=asc"
        try:
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code != 200:
                logger.error(f"Zendesk API returned status {response.status_code}")
                break

            data = response.json()
            page_articles = data.get("articles", [])
            if not page_articles:
                break

            for art in page_articles:
                if art["id"] not in seen_ids and art.get("body"):
                    articles.append(art)
                    seen_ids.add(art["id"])
                    if len(articles) >= limit:
                        break

            if not data.get("next_page"):
                break

            page += 1
        except Exception as e:
            logger.error(f"Error requesting Zendesk articles on page {page}: {e}")
            break

    logger.info(f"Fetched {len(articles)} total articles from Zendesk API.")
    return articles


def save_article_as_markdown(article: Dict[str, Any], output_dir: Path = ARTICLES_DIR) -> Dict[str, Any]:
    """Normalize and persist a single article to <slug>.md, returning article metadata."""
    title = article.get("title") or article.get("name") or f"article-{article['id']}"
    html_url = article.get("html_url") or f"https://support.optisigns.com/hc/en-us/articles/{article['id']}"
    body_html = article.get("body", "")

    slug = slugify(title)
    filename = f"{slug}.md"
    file_path = output_dir / filename

    content_md = clean_html_to_markdown(body_html, title, html_url)
    file_path.write_text(content_md, encoding="utf-8")

    return {
        "id": article["id"],
        "title": title,
        "slug": slug,
        "html_url": html_url,
        "updated_at": article.get("updated_at", ""),
        "filename": filename,
        "file_path": str(file_path),
        "content_length": len(content_md),
    }


def ensure_article_count(articles: List[Dict[str, Any]], limit: int) -> None:
    """Refuse a short scrape. The brief asks for at least `limit` articles."""
    if len(articles) < limit:
        raise RuntimeError(f"Need at least {limit} articles, got {len(articles)}")
    found = {article.get("id") for article in articles}
    missing = [article_id for article_id in ESSENTIAL_ARTICLE_IDS if article_id not in found]
    if missing:
        raise RuntimeError(f"Missing required articles: {missing}")


def scrape_and_save_all(limit: int = ARTICLES_LIMIT) -> List[Dict[str, Any]]:
    """End-to-end scraper execution: fetches, normalizes, and saves Markdown articles."""
    articles = fetch_articles(limit=limit)
    ensure_article_count(articles, limit)
    saved_metadata = []
    for art in articles:
        meta = save_article_as_markdown(art)
        saved_metadata.append(meta)
    logger.info(f"Saved {len(saved_metadata)} clean markdown articles to {ARTICLES_DIR}.")
    return saved_metadata
