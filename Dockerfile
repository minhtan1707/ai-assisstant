FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# One-shot ingest job: scrape + upload, then exit 0 on success
# Example: docker run --rm -e API_KEY=... -e INGEST_PROVIDER=gemini <image>
CMD ["python", "main.py"]
