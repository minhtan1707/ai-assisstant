# Knowledge Ingest Job

Python batch job that scrapes help-center articles, converts them to clean Markdown, and uploads only new or changed documents to a knowledge store. **Default provider is Gemini (free tier).** OpenAI is optional via `INGEST_PROVIDER=openai`.

## What it does

1. Fetches articles from a Zendesk Help Center API.
2. Writes clean Markdown to `articles/<slug>.md`.
3. Classifies each article as **added**, **updated**, or **skipped** via content hash.
4. Uploads only the delta to Gemini File Search (default) or OpenAI Vector Store.
5. Logs file counts, chunk counts, and added/updated/skipped totals.

## Provider switch

| `INGEST_PROVIDER` | Target | Typical use |
| --- | --- | --- |
| `gemini` (default) | Gemini File Search Store | Free demo / AI Studio |
| `openai` | OpenAI Vector Store | Playground file_search (needs credits) |

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
```

Required for **Gemini** (default):

| Variable | Purpose |
| --- | --- |
| `API_KEY` or `GEMINI_API_KEY` | Gemini API key (raw key only) |
| `GEMINI_FILE_SEARCH_STORE_NAME` | `fileSearchStores/...` |
| `HELP_CENTER_BASE_URL` | Help center origin |

Optional for **OpenAI** (`INGEST_PROVIDER=openai`):

| Variable | Purpose |
| --- | --- |
| `OPEN_AI_API_KEY` | OpenAI API key |
| `OPENAI_VECTOR_STORE_ID` | `vs_...` |

## Run locally

```bash
# Gemini (default)
python main.py

# OpenAI
INGEST_PROVIDER=openai python main.py
```

## Cloud Build

Default substitution `_INGEST_PROVIDER: gemini`. To deploy OpenAI instead, set the trigger substitution `_INGEST_PROVIDER=openai`.

## Smoke test (Gemini)

In Google AI Studio, attach the same File Search Store and ask:

> How do I add a YouTube video?
