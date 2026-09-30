# OptiSigns AI Assistant

Help-center ingest + grounded chat for OptiSigns support articles.

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
# Set API_KEY (Gemini) and/or OPEN_AI_API_KEY, plus store IDs — see .env.sample
```

## Run locally

```bash
# One-shot ingest (scrape help center → vector/file search store), then exit
python main.py

# Optional: API server for chat / HTTP ingest
uvicorn app:app --reload --port 8080
```

Chat example (server running):

```bash
curl -X POST "http://localhost:8080/api/v1/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SERVICE_API_KEY" \
  -d '{"message":"How do I add a YouTube video?"}'
```

## Docker (one-shot job)

Default image command is `python main.py` (runs once, exits `0` on success):

```bash
docker build -t ai-assistant .
docker run --rm \
  -e API_KEY=your_gemini_key \
  -e INGEST_PROVIDER=gemini \
  -e GEMINI_FILE_SEARCH_STORE_NAME=fileSearchStores/... \
  -e HELP_CENTER_BASE_URL=https://support.optisigns.com \
  ai-assistant
```

## Daily job logs

Cloud Scheduler triggers daily ingest on Cloud Run service `ai-assisstant` (`asia-southeast1`).

- [Cloud Run logs — ai-assisstant](https://console.cloud.google.com/run/detail/asia-southeast1/ai-assisstant/logs)
- Look for: `INGEST_STARTED`, `INGEST_SUMMARY`, `INGEST_FINISHED`

## Sample assistant answer

Question: *How do I add a YouTube video?*

![Assistant answering a sample question](docs/screenshots/assistant-sample.jpg)
