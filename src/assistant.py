"""AI Assistant module adhering to strict OptiBot customer support rules."""

import re
import logging
from typing import Dict, Any, Optional
from openai import OpenAI

from src.config import (
    SYSTEM_PROMPT,
    SANITY_PROMPT,
    OPENAI_MODEL,
)
from src.vector_store import get_openai_client, get_or_create_vector_store

logger = logging.getLogger(__name__)


def ask_optibot(
    query: str = SANITY_PROMPT,
    vector_store_id: Optional[str] = None,
    client: Optional[OpenAI] = None,
    model: str = OPENAI_MODEL,
) -> Dict[str, Any]:
    """
    Query OptiBot using the Responses API grounded on the knowledge base vector store.
    """
    client = client or get_openai_client()
    vector_store_id = vector_store_id or get_or_create_vector_store(client)

    logger.info(f"Asking OptiBot (Model: {model}, VS: {vector_store_id}): '{query}'")

    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=query,
        tools=[{
            "type": "file_search",
            "vector_store_ids": [vector_store_id],
        }],
    )

    answer_text = response.output_text.strip()
    validation = validate_optibot_response(answer_text)

    return {
        "query": query,
        "response": answer_text,
        "vector_store_id": vector_store_id,
        "model": model,
        "validation": validation,
    }


def validate_optibot_response(response_text: str) -> Dict[str, Any]:
    """
    Verify response compliance against OptiBot system rules:
    1. Max 5 bullet points.
    2. Cites up to 3 'Article URL:' lines per reply.
    """
    # Count bullet points (- , * , 1. , etc.)
    bullet_matches = re.findall(r"^(?:\s*[-*•]|\s*\d+\.)\s+", response_text, re.MULTILINE)
    bullet_count = len(bullet_matches)

    # Check for Article URL citations or links
    has_article_url = "Article URL:" in response_text or bool(re.search(r"https?://support\.optisigns\.com/hc/", response_text))
    url_citations = re.findall(r"(?:Article URL:\s*)?(https?://[^\s\)]+)", response_text)

    is_compliant = (bullet_count <= 5) and (len(url_citations) <= 3)

    return {
        "is_compliant": is_compliant,
        "bullet_count": bullet_count,
        "bullets_ok": bullet_count <= 5,
        "citations_count": len(url_citations),
        "citations_ok": len(url_citations) <= 3,
        "has_support_url": has_article_url,
        "detected_urls": url_citations[:3],
    }
