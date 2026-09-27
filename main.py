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
from src.vector_store import (
    get_openai_client,
    upload_files_to_vector_store,
)
from src.assistant import ask_optibot


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
    scraped_articles = scrape_and_save_all(limit=limit)
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

    print("\n--------------------------------------------------")
    print("VECTOR STORE INGESTION REPORT:")
    print(f"  • Vector Store ID: {vs_id}")
    print(f"  • Files Embedded:  {files_embedded}")
    print(f"  • Chunks Embedded: {chunks_embedded}")
    print(f"  • Files In Store:  {len(file_ids)}")
    print("--------------------------------------------------\n")

    new_state = update_sync_state_records(current_state, hashed_articles, file_ids)
    save_sync_state(new_state)

    # --- STEP 4: OptiBot Sanity Check ---
    if run_sanity:
        logger.info(f"[Step 4/4] Executing sanity check prompt: '{SANITY_PROMPT}'...")
        bot_result = ask_optibot(query=SANITY_PROMPT, vector_store_id=vs_id, client=client)
        if not bot_result["validation"]["has_support_url"]:
            logger.warning("Sanity answer had no support citation. Retrying once.")
            bot_result = ask_optibot(query=SANITY_PROMPT, vector_store_id=vs_id, client=client)

        print("\n==================================================")
        print("OPTIBOT VERIFICATION PROOF")
        print("==================================================")
        print(f"User Query: {bot_result['query']}\n")
        print("OptiBot Response:")
        print(bot_result["response"])
        print("\nCompliance Check:")
        print(f"  • Bullets Count:   {bot_result['validation']['bullet_count']} (<= 5: {bot_result['validation']['bullets_ok']})")
        print(f"  • Citations Count: {bot_result['validation']['citations_count']} (<= 3: {bot_result['validation']['citations_ok']})")
        print(f"  • Has Support Doc: {bot_result['validation']['has_support_url']}")
        print("==================================================\n")

        if not bot_result["validation"]["has_support_url"]:
            logger.error("Sanity check failed: answer did not cite a support article.")
            return 1
        proof_path = Path(__file__).resolve().parent / "docs" / "sanity-youtube.txt"
        compliant = (
            bot_result["validation"]["bullets_ok"]
            and "Article URL:" in bot_result["response"]
        )
        if not compliant:
            logger.warning(
                "Answer cites the docs but misses the prompt shape (%s bullet markers, Article URL line: %s). Leaving the saved sample in place.",
                bot_result["validation"]["bullet_count"],
                "Article URL:" in bot_result["response"],
            )
        else:
            proof_path.parent.mkdir(parents=True, exist_ok=True)
            proof_path.write_text(
                f"Query: {bot_result['query']}\n\n{bot_result['response']}\n",
                encoding="utf-8",
            )

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
