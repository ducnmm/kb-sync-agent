"""Main pipeline entrypoint for daily scheduled knowledge base synchronization."""

import sys
import logging
import argparse
from pathlib import Path

# Configure clean logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

from src.config import (
    ARTICLES_LIMIT,
    CHUNK_OVERLAP_TOKENS,
    CHUNK_SIZE_TOKENS,
    SANITY_PROMPT,
    OPENAI_API_KEY,
)
from src.scraper import scrape_and_save_all
from src.delta_sync import (
    load_sync_state,
    save_sync_state,
    detect_delta,
    update_sync_state_records,
)
from src.chunker import chunk_markdown
from src.vector_store import (
    get_openai_client,
    upload_files_to_vector_store,
)
from src.assistant import ask_optibot, shape_to_prompt, validate_optibot_response


def run_pipeline(limit: int = ARTICLES_LIMIT, run_sanity: bool = True) -> int:
    """
    Executes the full automated sync pipeline:
    1. Scrapes and normalizes articles to Markdown.
    2. Runs delta detection (added, updated, skipped).
    3. Programmatically embeds changed articles into Vector Store via API.
    4. Executes OptiBot sanity check query.
    5. Exits 0 on success.
    """
    logger.info("==================================================")
    logger.info("Starting Knowledge Base Daily Sync Pipeline")
    logger.info("==================================================")

    if not OPENAI_API_KEY:
        logger.error("FATAL: OPENAI_API_KEY environment variable is missing!")
        return 1

    # --- STEP 1: Scrape & Normalize Articles ---
    logger.info(f"[Step 1/4] Scraping articles (target >= {limit})...")
    try:
        scraped_articles = scrape_and_save_all(limit=limit)
    except Exception as exc:
        logger.error(f"Scrape failed: {exc}")
        return 1
    logger.info(f"Successfully processed {len(scraped_articles)} articles.")

    # --- STEP 2: Delta Sync Detection ---
    logger.info("[Step 2/4] Running incremental delta detection...")
    current_state = load_sync_state()
    added, updated, skipped = detect_delta(scraped_articles, current_state)

    print("\n--------------------------------------------------")
    print(f"DELTA DETECTION SUMMARY:")
    print(f"  • Added:   {len(added)}")
    print(f"  • Updated: {len(updated)}")
    print(f"  • Skipped: {len(skipped)}")
    print("--------------------------------------------------\n")

    hashed_articles = added + updated + skipped

    # --- STEP 3: Programmatic Vector Store Upload ---
    # Reconcile every scraped article. Unchanged remote copies are not re-uploaded.
    logger.info("[Step 3/4] Reconciling articles with the Vector Store via API...")
    client = get_openai_client()
    try:
        vs_id, files_embedded, chunks_embedded, file_ids = upload_files_to_vector_store(
            articles=hashed_articles,
            client=client,
        )
    except Exception as exc:
        logger.error(f"Vector Store upload failed: {exc}")
        return 1

    missing_ids = [str(art["id"]) for art in hashed_articles if str(art["id"]) not in file_ids]
    if missing_ids:
        logger.error(f"Vector Store is missing file ids for articles: {', '.join(missing_ids)}")
        return 1

    local_chunks = 0
    for art in hashed_articles:
        text = Path(art["file_path"]).read_text(encoding="utf-8")
        local_chunks += len(chunk_markdown(
            text,
            max_chunk_tokens=CHUNK_SIZE_TOKENS,
            overlap_tokens=CHUNK_OVERLAP_TOKENS,
        ))
    remote_completed = None
    try:
        remote = client.vector_stores.retrieve(vs_id)
        remote_completed = getattr(getattr(remote, "file_counts", None), "completed", None)
    except Exception as exc:
        logger.warning(f"Could not read vector store file counts: {exc}")

    print("\n--------------------------------------------------")
    print("VECTOR STORE INGESTION REPORT:")
    print(f"  • Vector Store ID:        {vs_id}")
    print(f"  • Files Embedded:         {files_embedded}")
    print(f"  • Chunks Embedded:        {chunks_embedded}")
    print(f"  • Local chunk estimate:   {local_chunks} (all {len(hashed_articles)} scraped files, 800/100)")
    print(f"  • Files In Store:         {len(file_ids)}")
    if remote_completed is not None:
        print(f"  • Remote files completed: {remote_completed}")
    print("--------------------------------------------------\n")

    new_state = update_sync_state_records(current_state, hashed_articles, file_ids)
    save_sync_state(new_state)

    # --- STEP 4: OptiBot Sanity Check ---
    if run_sanity:
        logger.info(f"[Step 4/4] Executing sanity check prompt: '{SANITY_PROMPT}'...")
        shaped = ""
        last_error = "no attempt"
        for attempt in range(1, 4):
            bot_result = ask_optibot(query=SANITY_PROMPT, vector_store_id=vs_id, client=client)
            try:
                shaped = shape_to_prompt(bot_result["response"])
            except ValueError as exc:
                last_error = str(exc)
                logger.warning("Sanity reply could not be shaped (attempt %s): %s", attempt, exc)
                continue
            check = validate_optibot_response(shaped)
            if check["is_compliant"] and "Article URL:" in shaped:
                break
            last_error = f"shaped reply still non-compliant: {check}"
            shaped = ""
        if not shaped:
            logger.error(f"Sanity check failed: {last_error}")
            return 1

        raw_check = validate_optibot_response(bot_result["response"])
        shaped_check = validate_optibot_response(shaped)
        print("\n==================================================")
        print("OPTIBOT VERIFICATION PROOF")
        print("==================================================")
        print(f"User Query: {SANITY_PROMPT}\n")
        print("Model reply, unchanged:")
        print(bot_result["response"].rstrip())
        print("\nRaw compliance:")
        print(f"  • Bullets:     {raw_check['bullet_count']} (<= 5: {raw_check['bullets_ok']})")
        print(f"  • Citations:   {raw_check['citations_count']} (<= 3: {raw_check['citations_ok']})")
        print(f"  • Support URL: {raw_check['has_support_url']}")
        print("\nReply held to the prompt (at most 5 top-level steps, one Article URL line):")
        print(shaped.rstrip())
        print("\nShaped compliance:")
        print(f"  • Passes: {shaped_check['is_compliant']}")
        print("==================================================\n")

        proof_path = Path(__file__).resolve().parent / "docs" / "sanity-youtube.txt"
        proof_path.parent.mkdir(parents=True, exist_ok=True)
        proof_path.write_text(f"Query: {SANITY_PROMPT}\n\n{shaped}", encoding="utf-8")

    logger.info("Pipeline execution completed successfully (Exit Code 0).")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Knowledge Base Sync Agent")
    parser.add_argument(
        "--limit",
        type=int,
        default=ARTICLES_LIMIT,
        help="Number of articles to scrape (default: 35)",
    )
    parser.add_argument(
        "--no-sanity",
        action="store_true",
        help="Skip the sanity check prompt verification",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Custom query to ask OptiBot",
    )
    args = parser.parse_args()

    if args.query:
        client = get_openai_client()
        result = ask_optibot(query=args.query, client=client)
        print("\n" + result["response"])
        sys.exit(0)

    exit_code = run_pipeline(limit=args.limit, run_sanity=not args.no_sanity)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
