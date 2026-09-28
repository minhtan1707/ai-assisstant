# Knowledge Ingest Job

Python batch job that scrapes help-center articles, converts them to clean Markdown, and uploads only new or changed documents to an OpenAI Vector Store (for Playground `file_search`). Runs once per invocation and exits `0`—ready for a daily schedule.

## What it does

1. Fetches articles from a Zendesk Help Center API.
2. Writes clean Markdown to `articles/<slug>.md` (headings, code blocks, and links kept; site chrome removed).
3. Classifies each article as **added**, **updated**, or **skipped** via content hash.
4. Uploads only the delta to an OpenAI Vector Store.
5. Logs file counts, chunk counts, and added/updated/skipped totals.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
```

Required env vars (see `.env.sample`):

| Variable | Purpose |
| --- | --- |
| `OPEN_AI_API_KEY` | OpenAI API key (raw key only in Secret Manager) |
| `OPENAI_VECTOR_STORE_ID` | Vector Store id (`vs_...`) |
| `HELP_CENTER_BASE_URL` | Help center origin (no trailing path) |

Create a Vector Store in [OpenAI Platform](https://platform.openai.com/storage/vector_stores), then attach it in Playground with **file_search**.

## Run locally

```bash
python main.py
```

## Run with Docker

```bash
docker build -t knowledge-ingest .
docker run --rm \
  -e OPEN_AI_API_KEY \
  -e OPENAI_VECTOR_STORE_ID \
  -e HELP_CENTER_BASE_URL \
  knowledge-ingest
```

## Daily job & logs

Schedule the Cloud Run Job once per day (e.g. Cloud Scheduler). After deploy, paste the log URL here:

- **Job logs:** _(add after deploy)_

## Smoke test

In OpenAI Playground, enable file_search on the same Vector Store and ask:

> How do I add a YouTube video?

## Chunking

~2000 character windows with ~200 overlap (logged locally). OpenAI Vector Store applies its own chunking when indexing.
