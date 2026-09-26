"""Programmatic Vector Store Management module."""

import json
import logging
import os
import time
from pathlib import Path
from typing import Callable, List, Dict, Any, Tuple, TypeVar
from openai import APIConnectionError, APIStatusError, OpenAI

from src.config import (
    OPENAI_API_KEY,
    VECTOR_STORE_NAME,
    VECTOR_STORE_STATE_FILE,
    CHUNK_SIZE_TOKENS,
    CHUNK_OVERLAP_TOKENS,
)
from src.chunker import chunk_markdown

logger = logging.getLogger(__name__)

T = TypeVar("T")
# 429 is the rate limit. 5xx is OpenAI being down. Both are worth a short wait.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _call(action: Callable[[], T]) -> T:
    """Run one OpenAI call. Back off when the API is rate-limiting or unavailable."""
    delay = 1.0
    for attempt in range(5):
        try:
            return action()
        except APIConnectionError as exc:
            if attempt == 4:
                raise
            logger.warning("OpenAI connection failed (%s). Retrying in %.0fs.", exc, delay)
        except APIStatusError as exc:
            if exc.status_code not in RETRYABLE_STATUS or attempt == 4:
                raise
            logger.warning("OpenAI returned %s. Retrying in %.0fs.", exc.status_code, delay)
        time.sleep(delay)
        delay = min(delay * 2, 16)
    raise RuntimeError("OpenAI retry loop exited without a result")


def get_openai_client() -> OpenAI:
    """Instantiate and return OpenAI client with configured API key."""
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not set. Please set it in .env or environment.")
    return OpenAI(api_key=OPENAI_API_KEY)


def _remember_vector_store(vs_id: str, name: str) -> None:
    VECTOR_STORE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(VECTOR_STORE_STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump({"vector_store_id": vs_id, "name": name}, handle, indent=2)


def _retrieve_vector_store(client: OpenAI, vs_id: str) -> str:
    vs = client.vector_stores.retrieve(vs_id)
    logger.info(f"Reusing existing Vector Store: {vs.id} ({vs.name})")
    _remember_vector_store(vs.id, vs.name)
    return vs.id


def _find_vector_store_by_name(client: OpenAI, name: str) -> str:
    """A clean container has no state file. Reuse the store with this name."""
    after = None
    while True:
        kwargs: Dict[str, Any] = {"limit": 100}
        if after:
            kwargs["after"] = after
        page = client.vector_stores.list(**kwargs)
        for vs in page.data:
            if vs.name == name:
                logger.info(f"Reusing Vector Store by name: {vs.id} ({vs.name})")
                _remember_vector_store(vs.id, vs.name)
                return vs.id
        if not page.has_more or not page.data:
            break
        after = page.data[-1].id
    raise LookupError(name)


def get_or_create_vector_store(client: OpenAI) -> str:
    """
    Reuse a vector store from the state file, VECTOR_STORE_ID, or its name.
    Create one only when none of those exist.
    """
    candidates = []
    if VECTOR_STORE_STATE_FILE.exists():
        try:
            with open(VECTOR_STORE_STATE_FILE, "r", encoding="utf-8") as handle:
                state_id = json.load(handle).get("vector_store_id")
            if state_id:
                candidates.append(state_id)
        except Exception as exc:
            logger.warning(f"Failed to read vector store state: {exc}")

    env_id = os.getenv("VECTOR_STORE_ID", "").strip()
    if env_id and env_id not in candidates:
        candidates.append(env_id)

    for vs_id in candidates:
        try:
            return _retrieve_vector_store(client, vs_id)
        except Exception:
            logger.warning(f"Vector Store {vs_id} not found on OpenAI.")

    try:
        return _find_vector_store_by_name(client, VECTOR_STORE_NAME)
    except LookupError:
        pass

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

    _remember_vector_store(vs.id, vs.name)
    logger.info(f"Programmatically created Vector Store: {vs.id}")
    return vs.id


CHUNKING_STRATEGY = {
    "type": "static",
    "static": {
        "max_chunk_size_tokens": CHUNK_SIZE_TOKENS,
        "chunk_overlap_tokens": CHUNK_OVERLAP_TOKENS,
    },
}


def _list_remote_files(client: OpenAI, vector_store_id: str) -> List[Any]:
    """Page through every file attached to a vector store."""
    remote = []
    after = None
    while True:
        kwargs: Dict[str, Any] = {"vector_store_id": vector_store_id, "limit": 100}
        if after:
            kwargs["after"] = after
        page = _call(lambda: client.vector_stores.files.list(**kwargs))
        remote.extend(page.data)
        if not page.has_more or not page.data:
            break
        after = page.data[-1].id
    return remote


def _index_remote_files(client: OpenAI, vector_store_id: str) -> Tuple[Dict[str, List[Any]], Dict[str, List[str]]]:
    """Index remote files by article_id. Only files missing that attribute need a filename lookup."""
    by_article: Dict[str, List[Any]] = {}
    by_name: Dict[str, List[str]] = {}
    for vs_file in _list_remote_files(client, vector_store_id):
        article_id = str((vs_file.attributes or {}).get("article_id") or "")
        if article_id:
            by_article.setdefault(article_id, []).append(vs_file)
            continue
        try:
            meta = _call(lambda: client.files.retrieve(vs_file.id))
        except Exception as exc:
            logger.warning(f"Could not read file metadata for {vs_file.id}: {exc}")
            continue
        if meta.filename:
            by_name.setdefault(meta.filename, []).append(vs_file.id)
    return by_article, by_name


def _delete_remote_file(client: OpenAI, vector_store_id: str, file_id: str) -> None:
    """Detach a file from the vector store and delete the underlying file object."""
    try:
        _call(lambda: client.vector_stores.files.delete(file_id=file_id, vector_store_id=vector_store_id))
    except Exception as exc:
        logger.warning(f"Could not detach {file_id} from {vector_store_id}: {exc}")
    try:
        _call(lambda: client.files.delete(file_id))
    except Exception as exc:
        logger.warning(f"Could not delete file object {file_id}: {exc}")


def upload_files_to_vector_store(
    articles: List[Dict[str, Any]],
    client: OpenAI = None,
) -> Tuple[str, int, int, Dict[str, str]]:
    """
    Upload changed Markdown files through the OpenAI API.

    Remote file attributes (article_id + content_hash) are the source of truth,
    so a fresh container or CI run does not upload the same article twice.

    Returns:
        (vector_store_id, files_embedded, chunks_embedded, article_id -> file_id)
    """
    client = client or get_openai_client()
    vs_id = get_or_create_vector_store(client)
    if not articles:
        logger.info("No articles to reconcile against the Vector Store.")
        return vs_id, 0, 0, {}

    by_article, by_name = _index_remote_files(client, vs_id)
    id_map: Dict[str, str] = {}
    pending: List[Dict[str, Any]] = []

    for art in articles:
        art_id = str(art["id"])
        path = Path(art["file_path"])
        if not path.exists():
            raise FileNotFoundError(f"Markdown file missing for article {art_id}: {path}")

        digest = art.get("hash") or ""
        group = by_article.get(art_id, [])
        match = next(
            (
                remote
                for remote in group
                if digest and str((remote.attributes or {}).get("content_hash") or "") == digest
            ),
            None,
        )
        if match:
            id_map[art_id] = match.id
            # A good copy is already in the store. Extra copies are safe to drop.
            for remote in group:
                if remote.id != match.id:
                    logger.info(f"Removing duplicate {remote.id} for article {art_id}")
                    _delete_remote_file(client, vs_id, remote.id)
            continue

        # Keep the old ids until the new batch has completed.
        stale_ids = [remote.id for remote in group]
        for file_id in by_name.get(path.name, []):
            if file_id not in stale_ids:
                stale_ids.append(file_id)

        text = path.read_text(encoding="utf-8")
        chunks = chunk_markdown(
            text,
            max_chunk_tokens=CHUNK_SIZE_TOKENS,
            overlap_tokens=CHUNK_OVERLAP_TOKENS,
        )
        pending.append({
            "id": art_id,
            "path": path,
            "hash": digest,
            "title": (art.get("title") or path.stem)[:200],
            "chunks": len(chunks),
            "stale_ids": stale_ids,
        })

    if not pending:
        logger.info(f"Vector Store {vs_id} already has current copies of {len(id_map)} article(s).")
        return vs_id, 0, 0, id_map

    total_chunks = sum(item["chunks"] for item in pending)
    logger.info(
        f"Uploading {len(pending)} file(s) ({total_chunks} estimated chunks) to Vector Store {vs_id}..."
    )

    created: List[Dict[str, Any]] = []
    try:
        for item in pending:
            path = item["path"]

            def send_file(path=path):
                # Re-open on every attempt. A retry must not send a stream already read to the end.
                with path.open("rb") as handle:
                    return client.files.create(file=(path.name, handle), purpose="assistants")

            uploaded = _call(send_file)
            created.append({**item, "file_id": uploaded.id})
    except Exception:
        for item in created:
            _delete_remote_file(client, vs_id, item["file_id"])
        raise

    try:
        batch = _call(
            lambda: client.vector_stores.file_batches.create_and_poll(
                vector_store_id=vs_id,
                files=[
                    {
                        "file_id": item["file_id"],
                        "attributes": {
                            "article_id": item["id"],
                            "content_hash": item["hash"],
                            "title": item["title"],
                        },
                        "chunking_strategy": CHUNKING_STRATEGY,
                    }
                    for item in created
                ],
                poll_interval_ms=1000,
            )
        )
    except Exception:
        for item in created:
            _delete_remote_file(client, vs_id, item["file_id"])
        raise
    failed = int(getattr(batch.file_counts, "failed", 0) or 0)
    logger.info(f"Vector Store batch {batch.id} status={batch.status} file_counts={batch.file_counts}")
    if batch.status != "completed" or failed:
        for item in created:
            _delete_remote_file(client, vs_id, item["file_id"])
        raise RuntimeError(
            f"Vector store batch {batch.id} status={batch.status} failed_files={failed}"
        )

    for item in created:
        id_map[item["id"]] = item["file_id"]
        for stale_id in item["stale_ids"]:
            if stale_id != item["file_id"]:
                logger.info(f"Removing replaced file {stale_id} for article {item['id']}")
                _delete_remote_file(client, vs_id, stale_id)

    logger.info(
        f"Uploaded {len(created)} file(s). Local chunk estimate: {total_chunks}. Vector Store {vs_id}."
    )
    return vs_id, len(created), total_chunks, id_map
