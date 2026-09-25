"""Incremental Delta Detection and State Tracking module."""

import json
import hashlib
import logging
from typing import Dict, Any, List, Tuple
from pathlib import Path

from src.config import SYNC_STATE_FILE

logger = logging.getLogger(__name__)


def compute_file_hash(file_path: Path) -> str:
    """Compute the SHA256 hex digest of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_text_hash(text: str) -> str:
    """Compute the SHA256 hex digest of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_sync_state(state_file: Path = SYNC_STATE_FILE) -> Dict[str, Any]:
    """Load previous synchronization state from JSON."""
    if not state_file.exists():
        return {}
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not read sync state file {state_file}: {e}")
        return {}


def save_sync_state(state: Dict[str, Any], state_file: Path = SYNC_STATE_FILE) -> None:
    """Atomically persist synchronization state to JSON."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = state_file.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    temp_file.replace(state_file)
    logger.debug(f"Saved sync state with {len(state)} records to {state_file}.")


def detect_delta(
    scraped_articles: List[Dict[str, Any]],
    current_state: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Compare freshly scraped articles against the previous synchronization state.
    Returns: (added, updated, skipped) lists of article metadata.
    """
    added: List[Dict[str, Any]] = []
    updated: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for art in scraped_articles:
        art_id = str(art["id"])
        file_path = Path(art["file_path"])
        file_hash = compute_file_hash(file_path) if file_path.exists() else compute_text_hash("")

        art_record = {
            **art,
            "hash": file_hash,
        }

        if art_id not in current_state:
            added.append(art_record)
        else:
            previous_record = current_state[art_id]
            previous_hash = previous_record.get("hash")
            previous_updated_at = previous_record.get("updated_at")

            # Check both content hash and timestamp for delta detection
            if previous_hash != file_hash or (art.get("updated_at") and previous_updated_at != art.get("updated_at")):
                updated.append(art_record)
            else:
                skipped.append(art_record)

    logger.info(
        f"Delta sync detection: added={len(added)}, updated={len(updated)}, skipped={len(skipped)}"
    )
    return added, updated, skipped


def update_sync_state_records(
    current_state: Dict[str, Any],
    synced_articles: List[Dict[str, Any]],
    vector_file_ids: Dict[str, str] = None,
) -> Dict[str, Any]:
    """Update state dictionary with newly uploaded/synced article records."""
    vector_file_ids = vector_file_ids or {}
    new_state = dict(current_state)

    for art in synced_articles:
        art_id = str(art["id"])
        new_state[art_id] = {
            "id": art["id"],
            "title": art["title"],
            "slug": art["slug"],
            "filename": art["filename"],
            "hash": art.get("hash") or compute_file_hash(Path(art["file_path"])),
            "updated_at": art.get("updated_at", ""),
            "openai_file_id": vector_file_ids.get(art_id) or new_state.get(art_id, {}).get("openai_file_id"),
        }

    return new_state
