"""Gemini File Search Store upload helper."""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

from google import genai


DEFAULT_CHUNK_SIZE = 2000
DEFAULT_CHUNK_OVERLAP = 200
DEFAULT_UPLOAD_POLL_SECONDS = 5
DEFAULT_UPLOAD_TIMEOUT_SECONDS = 0

MIME_TYPES_BY_SUFFIX: dict[str, str] = {
    ".md": "text/plain",
    ".markdown": "text/plain",
    ".txt": "text/plain",
    ".html": "text/html",
    ".htm": "text/html",
    ".json": "application/json",
    ".pdf": "application/pdf",
}

logger = logging.getLogger("ingest.gemini")


def resolve_mime_type(filepath: Path) -> str:
    """Resolve a MIME type the Gemini SDK cannot always infer from extension."""
    mime_type = MIME_TYPES_BY_SUFFIX.get(filepath.suffix.lower())
    if mime_type:
        return mime_type
    raise ValueError(f"Unsupported file type for upload: {filepath.suffix!r}")


def resolve_api_key() -> str:
    """Resolve API key from API_KEY or GEMINI_API_KEY."""
    api_key = os.getenv("API_KEY") or os.getenv("GEMINI_API_KEY") or ""
    if not api_key.strip():
        raise ValueError("Set API_KEY or GEMINI_API_KEY in the environment.")
    return api_key.strip()


def is_upload_complete(operation: object) -> bool:
    """Return True when the upload LRO finished or already returned a document."""
    if getattr(operation, "done", None) is True:
        return True
    response = getattr(operation, "response", None)
    if response is None:
        return False
    if isinstance(response, dict):
        return bool(response.get("document_name") or response.get("documentName"))
    return bool(getattr(response, "document_name", None))


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split text with a sliding window, preferring Markdown heading boundaries."""
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            window = text[start:end]
            heading_matches = list(re.finditer(r"\n#{1,6}\s", window))
            if heading_matches:
                last_heading = heading_matches[-1].start()
                if last_heading > chunk_size // 2:
                    end = start + last_heading
        chunks.append(text[start:end])
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks


class GeminiStoreManager:
    """Uploads Markdown files to a Gemini File Search Store."""

    def __init__(
        self,
        api_key: str | None = None,
        store_name: str | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        self.api_key = api_key or resolve_api_key()
        self.store_name = store_name or os.getenv("GEMINI_FILE_SEARCH_STORE_NAME")
        if not self.store_name:
            raise ValueError("Set GEMINI_FILE_SEARCH_STORE_NAME in the environment.")
        self.chunk_size = chunk_size or int(os.getenv("CHUNK_SIZE", str(DEFAULT_CHUNK_SIZE)))
        self.chunk_overlap = chunk_overlap or int(
            os.getenv("CHUNK_OVERLAP", str(DEFAULT_CHUNK_OVERLAP))
        )
        self.client = genai.Client(api_key=self.api_key)

    def count_chunks(self, text: str) -> int:
        """Return how many chunks would be produced for logging."""
        return len(chunk_text(text, self.chunk_size, self.chunk_overlap))

    def upload_file(self, filepath: Path, display_name: str | None = None) -> object:
        """Upload a file; optionally poll until Gemini reports the LRO complete."""
        poll_seconds = int(os.getenv("UPLOAD_POLL_SECONDS", str(DEFAULT_UPLOAD_POLL_SECONDS)))
        timeout_seconds = int(
            os.getenv("UPLOAD_TIMEOUT_SECONDS", str(DEFAULT_UPLOAD_TIMEOUT_SECONDS))
        )
        operation = self.client.file_search_stores.upload_to_file_search_store(
            file=str(filepath),
            file_search_store_name=self.store_name,
            config={
                "display_name": display_name or filepath.name,
                "mime_type": resolve_mime_type(filepath),
            },
        )
        # Gemini often accepts the file bytes but never sets operation.done.
        # Default is skip waiting so the Job can finish all articles.
        if timeout_seconds <= 0 or is_upload_complete(operation):
            if getattr(operation, "error", None):
                raise RuntimeError(f"Upload failed for {filepath}: {operation.error}")
            logger.info("Uploaded %s", filepath.name)
            return operation
        deadline = time.monotonic() + timeout_seconds
        poll_count = 0
        while not is_upload_complete(operation):
            if time.monotonic() >= deadline:
                logger.warning(
                    "Upload status for %s never reported done=%s after %ss; "
                    "bytes were accepted, continuing to next file (operation=%s)",
                    filepath.name,
                    getattr(operation, "done", None),
                    timeout_seconds,
                    getattr(operation, "name", None),
                )
                return operation
            time.sleep(poll_seconds)
            operation = self.client.operations.get(operation)
            poll_count += 1
            if poll_count % 6 == 0:
                logger.info(
                    "Still indexing %s (polls=%s done=%s)",
                    filepath.name,
                    poll_count,
                    getattr(operation, "done", None),
                )
        if getattr(operation, "error", None):
            raise RuntimeError(f"Upload failed for {filepath}: {operation.error}")
        logger.info("Uploaded %s", filepath.name)
        return operation
