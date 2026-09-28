"""One-shot scrape → delta → OpenAI Vector Store upload job."""

from __future__ import annotations

import logging
import sys
from collections import Counter

from dotenv import load_dotenv

from openai_store import OpenAIStoreManager
from scraper import scrape_help_center
from state import ArticleStateStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logger = logging.getLogger("ingest")


def execute_ingest() -> int:
    """Run the full ingest pipeline and return a process exit code."""
    load_dotenv()
    logger.info("--- STARTING HELP-CENTER INGEST ---")
    articles = scrape_help_center()
    if not articles:
        logger.error("No articles scraped; check HELP_CENTER_BASE_URL and network access.")
        return 1
    logger.info("Scraped %s articles to Markdown", len(articles))
    state = ArticleStateStore()
    store = OpenAIStoreManager()
    counts: Counter[str] = Counter()
    files_uploaded = 0
    chunks_embedded = 0
    for article in articles:
        change = state.classify(article.article_id, article.content_hash)
        counts[change] += 1
        if change == "skipped":
            logger.info("[SKIP] %s (%s)", article.slug, article.html_url)
            continue
        chunk_count = store.count_chunks(article.markdown)
        logger.info(
            "[%s] file=%s chars=%s chunks=%s url=%s",
            change.upper(),
            article.filepath.name,
            article.char_count,
            chunk_count,
            article.html_url,
        )
        try:
            store.upload_file(article.filepath, display_name=article.filepath.name)
            state.mark(article.article_id, article.content_hash, article.slug)
            files_uploaded += 1
            chunks_embedded += chunk_count
        except Exception as exc:
            logger.exception("[ERROR] Failed upload for %s: %s", article.slug, exc)
            counts["failed"] += 1
    state.save()
    logger.info("--- INGEST SUMMARY ---")
    logger.info("Total scraped: %s", len(articles))
    logger.info("Added: %s", counts["added"])
    logger.info("Updated: %s", counts["updated"])
    logger.info("Skipped: %s", counts["skipped"])
    logger.info("Failed: %s", counts["failed"])
    logger.info("Files uploaded: %s", files_uploaded)
    logger.info("Chunks embedded: %s", chunks_embedded)
    logger.info("----------------------")
    return 1 if counts["failed"] else 0


def main() -> None:
    """CLI entrypoint."""
    exit_code = execute_ingest()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
