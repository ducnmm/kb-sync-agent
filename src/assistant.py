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
        temperature=0.2,
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


def shape_to_prompt(response_text: str) -> str:
    """Keep the model's top-level steps and the article it cited, in the prompt's shape.

    Nested bullets are dropped. At most five steps are kept. The cited support
    URL is written as an Article URL line. Raises ValueError if either is missing.
    """
    urls = []
    for match in re.findall(r"https?://support\.optisigns\.com/hc/\S+", response_text):
        url = match.rstrip(").,]>\"'")
        if url not in urls:
            urls.append(url)
    if not urls:
        raise ValueError("model reply cited no support article")

    lines = response_text.splitlines()
    steps = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith((" ", "\t")):
            index += 1
            continue
        match = re.match(r"^(?:[-*•]|\d+\.)\s+(.*\S)\s*$", line.strip())
        if not match:
            index += 1
            continue
        step = re.sub(r"\*\*", "", match.group(1)).strip()
        extras = []
        nxt = index + 1
        while nxt < len(lines) and lines[nxt].startswith((" ", "\t")):
            extra = re.match(r"^\s*(?:[-*•]|\d+\.)\s+(.*\S)\s*$", lines[nxt])
            if extra:
                extras.append(re.sub(r"\*\*", "", extra.group(1)).strip())
            nxt += 1
        # A step that is only a label keeps one nested detail, preferring the link field.
        # It stays one bullet, so the reply does not grow past the prompt's cap.
        if step.endswith(":") and extras:
            chosen = next((item for item in extras if re.search(r"URL|link|Paste", item, re.I)), None)
            if chosen:
                step = f"{step} {chosen}"
        if step:
            steps.append(step)
        index = nxt
    if not steps:
        raise ValueError("model reply had no top-level steps")

    body = "\n".join(f"• {step}" for step in steps[:5])
    return f"{body}\n\nArticle URL: {urls[0]}\n"


def validate_optibot_response(response_text: str) -> Dict[str, Any]:
    """
    Verify response compliance against OptiBot system rules:
    1. Max 5 bullet points.
    2. Cites up to 3 'Article URL:' lines per reply.
    """
    # Top-level bullets only. Nested examples under one step are still bullets,
    # so indented markers count too: the prompt caps the whole reply at 5.
    bullet_matches = re.findall(r"^(?:\s*[-*•]|\s*\d+\.)\s+", response_text, re.MULTILINE)
    bullet_count = len(bullet_matches)

    cited_urls = []
    for match in re.findall(
        r"(?:Article URL:\s*)?(https?://support\.optisigns\.com/hc/\S+)",
        response_text,
    ):
        url = match.rstrip(").,]>\"'")
        if url not in cited_urls:
            cited_urls.append(url)
    has_article_url = bool(cited_urls)

    is_compliant = (bullet_count <= 5) and (len(cited_urls) <= 3) and has_article_url

    return {
        "is_compliant": is_compliant,
        "bullet_count": bullet_count,
        "bullets_ok": bullet_count <= 5,
        "citations_count": len(cited_urls),
        "citations_ok": len(cited_urls) <= 3 and has_article_url,
        "has_support_url": has_article_url,
        "detected_urls": cited_urls[:3],
    }
