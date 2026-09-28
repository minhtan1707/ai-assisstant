"""One-shot scrape → delta → Gemini or OpenAI upload job."""

from __future__ import annotations

import logging
import os
import sys
from collections import Counter
from typing import Protocol

from dotenv import load_dotenv

from scraper import scrape_help_center
from state import ArticleStateStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logger = logging.getLogger("ingest")

SUPPORTED_PROVIDERS = frozenset({"gemini", "openai"})


class KnowledgeStore(Protocol):
    """Minimal store contract used by the ingest loop."""

    def count_chunks(self, text: str) -> int:
        """Return estimated chunk count for logging."""

    def upload_file(self, filepath: object, display_name: str | None = None) -> object:
        """Upload one article file to the configured provider store."""


def resolve_provider() -> str:
    """Resolve ingest provider from INGEST_PROVIDER (gemini|openai)."""
    provider = (os.getenv("INGEST_PROVIDER") or "gemini").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported INGEST_PROVIDER={provider!r}. Use one of: {sorted(SUPPORTED_PROVIDERS)}"
        )
    return provider


def create_store(provider: str) -> KnowledgeStore:
    """Build the knowledge store for the selected provider."""
    if provider == "openai":
        from openai_store import OpenAIStoreManager

        return OpenAIStoreManager()
    from gemini_store import GeminiStoreManager

    return GeminiStoreManager()


def execute_ingest() -> int:
    """Run the full ingest pipeline and return a process exit code."""
    load_dotenv()
    provider = resolve_provider()
    logger.info("--- STARTING HELP-CENTER INGEST (provider=%s) ---", provider)
    articles = scrape_help_center()
    if not articles:
        logger.error("No articles scraped; check HELP_CENTER_BASE_URL and network access.")
        return 1
    logger.info("Scraped %s articles to Markdown", len(articles))
    state = ArticleStateStore()
    store = create_store(provider)
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
    logger.info("Provider: %s", provider)
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
