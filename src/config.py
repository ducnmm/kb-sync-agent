"""Configuration and constants for KB Sync Agent."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
ARTICLES_DIR = DATA_DIR / "articles"
STATE_DIR = DATA_DIR / "state"

ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)

# State Files
SYNC_STATE_FILE = STATE_DIR / "sync_state.json"
VECTOR_STORE_STATE_FILE = STATE_DIR / "vector_store.json"

# API & Model Configuration
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY") or "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

# Scraper Settings
ZENDESK_API_URL = "https://support.optisigns.com/api/v2/help_center/en-us/articles.json"
ZENDESK_SEARCH_URL = "https://support.optisigns.com/api/v2/help_center/articles/search.json"
ARTICLES_LIMIT = int(os.getenv("ARTICLES_LIMIT", "35"))

# Chunking Strategy Configuration
CHUNK_SIZE_TOKENS = int(os.getenv("CHUNK_SIZE_TOKENS", "800"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", "100"))
VECTOR_STORE_NAME = os.getenv("VECTOR_STORE_NAME", "kb-optibot-knowledge-base")

# Verbatim System Prompt required by the assessment specification
SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""

# Sanity Verification Prompt
SANITY_PROMPT = "How do I add a YouTube video?"
