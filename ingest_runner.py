"""Shared scrape → delta → upload runner with progress logging."""

from __future__ import annotations

import logging
import os
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol

from scraper import scrape_help_center
from state import ArticleStateStore

logger = logging.getLogger("ingest")

SUPPORTED_PROVIDERS = frozenset({"gemini", "openai"})
ProgressCallback = Callable[["IngestStatus"], None]


class KnowledgeStore(Protocol):
    """Minimal store contract used by the ingest loop."""

    def count_chunks(self, text: str) -> int:
        """Return estimated chunk count for logging."""

    def upload_file(self, filepath: object, display_name: str | None = None) -> object:
        """Upload one article file to the configured provider store."""


@dataclass
class IngestStatus:
    """Mutable snapshot of an ingest run for API status polling."""

    run_id: str
    status: str = "idle"
    provider: str = "openai"
    started_at: str | None = None
    finished_at: str | None = None
    added: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    files_uploaded: int = 0
    chunks_embedded: int = 0
    total_scraped: int = 0
    current_file: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize status using snake_case keys."""
        return asdict(self)


def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


def resolve_provider(provider: str | None = None) -> str:
    """Resolve ingest provider from argument or INGEST_PROVIDER env."""
    resolved = (provider or os.getenv("INGEST_PROVIDER") or "openai").strip().lower()
    if resolved not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported INGEST_PROVIDER={resolved!r}. Use one of: {sorted(SUPPORTED_PROVIDERS)}"
        )
    return resolved


def create_store(provider: str) -> KnowledgeStore:
    """Build the knowledge store for the selected provider."""
    if provider == "openai":
        from openai_store import OpenAIStoreManager

        return OpenAIStoreManager()
    from gemini_store import GeminiStoreManager

    return GeminiStoreManager()


def execute_ingest(
    provider: str | None = None,
    run_id: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> IngestStatus:
    """Run scrape + delta upload and return the final status snapshot."""
    resolved_provider = resolve_provider(provider)
    status = IngestStatus(
        run_id=run_id or uuid.uuid4().hex[:12],
        status="running",
        provider=resolved_provider,
        started_at=utc_now_iso(),
        message="ingest_started",
    )

    def publish() -> None:
        if on_progress is not None:
            on_progress(status)

    publish()
    logger.info(
        "INGEST_STARTED run_id=%s provider=%s",
        status.run_id,
        status.provider,
    )
    try:
        articles = scrape_help_center()
        if not articles:
            status.status = "failed"
            status.finished_at = utc_now_iso()
            status.message = "no_articles_scraped"
            logger.error("INGEST_FINISHED run_id=%s status=failed reason=no_articles", status.run_id)
            publish()
            return status
        status.total_scraped = len(articles)
        logger.info("INGEST_SCRAPE_DONE total=%s run_id=%s", len(articles), status.run_id)
        publish()
        state = ArticleStateStore()
        store = create_store(resolved_provider)
        counts: Counter[str] = Counter()
        for article in articles:
            change = state.classify(article.article_id, article.content_hash)
            counts[change] += 1
            status.added = counts["added"]
            status.updated = counts["updated"]
            status.skipped = counts["skipped"]
            status.failed = counts["failed"]
            status.current_file = article.filepath.name
            logger.info(
                "INGEST_ARTICLE status=%s file=%s chars=%s url=%s",
                change,
                article.filepath.name,
                article.char_count,
                article.html_url,
            )
            publish()
            if change == "skipped":
                continue
            chunk_count = store.count_chunks(article.markdown)
            logger.info(
                "INGEST_UPLOAD_START file=%s chunks=%s",
                article.filepath.name,
                chunk_count,
            )
            publish()
            try:
                store.upload_file(article.filepath, display_name=article.filepath.name)
                state.mark(article.article_id, article.content_hash, article.slug)
                status.files_uploaded += 1
                status.chunks_embedded += chunk_count
                logger.info("INGEST_UPLOAD_DONE file=%s", article.filepath.name)
            except Exception as exc:
                counts["failed"] += 1
                status.failed = counts["failed"]
                logger.exception(
                    "INGEST_ARTICLE status=failed file=%s error=%s",
                    article.slug,
                    exc,
                )
            publish()
        state.save()
        status.added = counts["added"]
        status.updated = counts["updated"]
        status.skipped = counts["skipped"]
        status.failed = counts["failed"]
        status.current_file = None
        status.status = "failed" if counts["failed"] else "success"
        status.finished_at = utc_now_iso()
        status.message = "ingest_finished"
        logger.info(
            "INGEST_SUMMARY added=%s updated=%s skipped=%s failed=%s files_uploaded=%s",
            status.added,
            status.updated,
            status.skipped,
            status.failed,
            status.files_uploaded,
        )
        logger.info(
            "INGEST_FINISHED run_id=%s status=%s",
            status.run_id,
            status.status,
        )
        publish()
        return status
    except Exception as exc:
        status.status = "failed"
        status.finished_at = utc_now_iso()
        status.message = str(exc)
        status.current_file = None
        logger.exception("INGEST_FINISHED run_id=%s status=failed error=%s", status.run_id, exc)
        publish()
        return status
