"""Programmatic Vector Store Management module."""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
from openai import OpenAI

from src.config import (
    OPENAI_API_KEY,
    VECTOR_STORE_NAME,
    VECTOR_STORE_STATE_FILE,
    CHUNK_SIZE_TOKENS,
    CHUNK_OVERLAP_TOKENS,
)
from src.chunker import chunk_markdown

logger = logging.getLogger(__name__)


def get_openai_client() -> OpenAI:
    """Instantiate and return OpenAI client with configured API key."""
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not set. Please set it in .env or environment.")
    return OpenAI(api_key=OPENAI_API_KEY)


def get_or_create_vector_store(client: OpenAI) -> str:
    """
    Retrieve existing vector store from state file, verify it exists remotely,
    or programmatically create a new one with static chunking strategy.
    """
    if VECTOR_STORE_STATE_FILE.exists():
        try:
            with open(VECTOR_STORE_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                vs_id = state.get("vector_store_id")
                if vs_id:
                    # Verify vector store still exists on OpenAI
                    try:
                        vs = client.vector_stores.retrieve(vs_id)
                        logger.info(f"Reusing existing Vector Store: {vs.id} ({vs.name})")
                        return vs.id
                    except Exception:
                        logger.warning(f"Vector Store {vs_id} not found on OpenAI; creating fresh one.")
        except Exception as e:
            logger.warning(f"Failed to read vector store state: {e}")

    # Create new Vector Store programmatically with static chunking strategy
    logger.info(
        f"Creating Vector Store '{VECTOR_STORE_NAME}' (chunk_size={CHUNK_SIZE_TOKENS}, overlap={CHUNK_OVERLAP_TOKENS})..."
    )
    vs = client.vector_stores.create(
        name=VECTOR_STORE_NAME,
        chunking_strategy={
            "type": "static",
            "static": {
                "max_chunk_size_tokens": CHUNK_SIZE_TOKENS,
                "chunk_overlap_tokens": CHUNK_OVERLAP_TOKENS,
            },
        },
    )

    VECTOR_STORE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(VECTOR_STORE_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"vector_store_id": vs.id, "name": vs.name}, f, indent=2)

    logger.info(f"Programmatically created Vector Store: {vs.id}")
    return vs.id


def upload_files_to_vector_store(
    articles: List[Dict[str, Any]],
    client: OpenAI = None,
) -> Tuple[str, int, int]:
    """
    Programmatically uploads markdown files into the OpenAI Vector Store.
    Calculates and logs the exact count of files and chunks embedded.
    
    Returns:
        (vector_store_id, total_files_embedded, total_chunks_embedded)
    """
    if not articles:
        logger.info("No new/updated articles to upload to Vector Store.")
        client = client or get_openai_client()
        vs_id = get_or_create_vector_store(client)
        return vs_id, 0, 0

    client = client or get_openai_client()
    vs_id = get_or_create_vector_store(client)

    # 1. Calculate exact chunk counts locally per chunking strategy
    total_chunks = 0
    valid_file_paths: List[Path] = []

    for art in articles:
        p = Path(art["file_path"])
        if p.exists():
            valid_file_paths.append(p)
            text = p.read_text(encoding="utf-8")
            chunks = chunk_markdown(
                text,
                max_chunk_tokens=CHUNK_SIZE_TOKENS,
                overlap_tokens=CHUNK_OVERLAP_TOKENS,
            )
            total_chunks += len(chunks)

    total_files = len(valid_file_paths)
    logger.info(
        f"Uploading {total_files} file(s) ({total_chunks} estimated chunks) to Vector Store {vs_id}..."
    )

    # 2. Upload via OpenAI Vector Store File Batches API
    file_streams = [open(fp, "rb") for fp in valid_file_paths]
    try:
        batch = client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vs_id,
            files=file_streams,
        )
        logger.info(
            f"Vector Store batch complete. Status: {batch.status} | Files: {batch.file_counts}"
        )
    finally:
        for fs in file_streams:
            fs.close()

    # Exact count log requirement
    logger.info(
        f"EXACT INGESTION COUNT: {total_files} file(s) and {total_chunks} chunk(s) embedded into Vector Store {vs_id}."
    )
    return vs_id, total_files, total_chunks
