"""FastAPI Cloud Run service: async ingest + file-search chat."""

from __future__ import annotations

import logging
import os
import threading
import uuid
from typing import Annotated, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from chat_service import execute_chat
from env_loader import load_app_env
from ingest_runner import IngestStatus, execute_ingest, resolve_provider

load_app_env()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logger = logging.getLogger("api")

app = FastAPI(title="OptiSigns Knowledge API", version="1.0.0")

_status_lock = threading.Lock()
_ingest_status = IngestStatus(run_id="", status="idle", message="no_runs_yet")


class IngestRequest(BaseModel):
    """Optional provider override for an ingest run."""

    provider: Literal["gemini", "openai"] | None = None


class IngestAcceptedResponse(BaseModel):
    """Immediate response after accepting a background ingest."""

    status: str
    run_id: str
    provider: str
    message: str


class ChatRequest(BaseModel):
    """Chat request body (snake_case)."""

    message: str = Field(min_length=1)
    provider: Literal["gemini", "openai"] | None = None


class ChatResponse(BaseModel):
    """Chat response body (snake_case)."""

    answer: str
    provider: str
    citations: list[dict[str, str]]


def resolve_service_api_key() -> str:
    """Load the shared service API key from the environment."""
    return (os.getenv("SERVICE_API_KEY") or "").strip()


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Validate X-API-Key against SERVICE_API_KEY."""
    expected = resolve_service_api_key()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SERVICE_API_KEY is not configured",
        )
    if not x_api_key or x_api_key.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_api_key",
        )


def get_ingest_status_snapshot() -> dict[str, object]:
    """Return a copy of the latest ingest status."""
    with _status_lock:
        return _ingest_status.to_dict()


def set_ingest_status(snapshot: IngestStatus) -> None:
    """Replace the in-memory ingest status."""
    global _ingest_status
    with _status_lock:
        _ingest_status = snapshot


def is_ingest_running() -> bool:
    """Return True when a background ingest is in progress."""
    with _status_lock:
        return _ingest_status.status == "running"


def run_ingest_job(run_id: str, provider: str) -> None:
    """Background worker entrypoint for scrape + upload."""
    logger.info("BACKGROUND_INGEST_DISPATCH run_id=%s provider=%s", run_id, provider)
    result = execute_ingest(
        provider=provider,
        run_id=run_id,
        on_progress=set_ingest_status,
    )
    set_ingest_status(result)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for Cloud Run (unauthenticated)."""
    return {"status": "ok"}


@app.post(
    "/api/v1/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestAcceptedResponse,
    dependencies=[Depends(require_api_key)],
)
def start_ingest(
    background_tasks: BackgroundTasks,
    body: IngestRequest | None = None,
) -> IngestAcceptedResponse:
    """Accept an ingest run and execute it asynchronously."""
    if is_ingest_running():
        current = get_ingest_status_snapshot()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "ingest_already_running",
                "run_id": current.get("run_id"),
            },
        )
    try:
        provider = resolve_provider(None if body is None else body.provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    run_id = uuid.uuid4().hex[:12]
    pending = IngestStatus(
        run_id=run_id,
        status="running",
        provider=provider,
        message="ingest_queued",
    )
    set_ingest_status(pending)
    background_tasks.add_task(run_ingest_job, run_id, provider)
    logger.info("INGEST_ACCEPTED run_id=%s provider=%s", run_id, provider)
    return IngestAcceptedResponse(
        status="accepted",
        run_id=run_id,
        provider=provider,
        message="ingest_started",
    )


@app.get("/api/v1/ingest/status", dependencies=[Depends(require_api_key)])
def ingest_status() -> dict[str, object]:
    """Return current or last ingest run status."""
    return get_ingest_status_snapshot()


@app.post(
    "/api/v1/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_api_key)],
)
def chat(body: ChatRequest) -> ChatResponse:
    """Answer a question using the configured file-search knowledge store."""
    try:
        result = execute_chat(body.message, provider=body.provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("CHAT_FAILED error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="chat_provider_error",
        ) from exc
    return ChatResponse(
        answer=str(result.get("answer") or ""),
        provider=str(result.get("provider") or ""),
        citations=list(result.get("citations") or []),  # type: ignore[arg-type]
    )
