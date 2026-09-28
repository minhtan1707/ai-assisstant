"""Zendesk Help Center scraper and Markdown conversion."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_markdown

DEFAULT_BASE_URL = "https://support.optisigns.com"
DEFAULT_LOCALE = "en-us"
DEFAULT_MIN_ARTICLES = 30
DEFAULT_ARTICLES_DIR = "articles"


@dataclass(frozen=True)
class ScrapedArticle:
    """Normalized article ready for hashing and upload."""

    article_id: str
    slug: str
    title: str
    html_url: str
    updated_at: str
    markdown: str
    content_hash: str
    filepath: Path
    char_count: int


def build_slug(title: str, article_id: str) -> str:
    """Build a filesystem-safe slug from the title and article id."""
    normalized = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not normalized:
        normalized = "article"
    return f"{normalized[:80]}-{article_id}"


def html_body_to_markdown(body_html: str, base_url: str) -> str:
    """Convert Zendesk article HTML into clean Markdown."""
    soup = BeautifulSoup(body_html or "", "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "aside", "iframe"]):
        tag.decompose()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if href.startswith("/") or href.startswith("./") or href.startswith("../"):
            anchor["href"] = urljoin(base_url.rstrip("/") + "/", href)
    markdown = html_to_markdown(str(soup), heading_style="ATX", bullets="-")
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    return markdown


def build_markdown_document(title: str, html_url: str, body_markdown: str) -> str:
    """Assemble the final Markdown file contents with citation URL."""
    sections = [
        f"# {title}",
        "",
        f"Article URL: {html_url}",
        "",
        body_markdown,
        "",
    ]
    return "\n".join(sections)


def compute_content_hash(markdown: str) -> str:
    """Return SHA256 hex digest of Markdown content."""
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


def fetch_articles(
    base_url: str,
    locale: str,
    min_articles: int,
    client: httpx.Client,
) -> list[dict]:
    """Paginate the Zendesk Help Center articles API until min_articles."""
    articles: list[dict] = []
    page = 1
    while len(articles) < min_articles:
        endpoint = f"{base_url.rstrip('/')}/api/v2/help_center/{locale}/articles.json"
        response = client.get(endpoint, params={"page": page, "per_page": 30})
        response.raise_for_status()
        payload = response.json()
        batch = payload.get("articles") or []
        if not batch:
            break
        for article in batch:
            if article.get("draft"):
                continue
            articles.append(article)
            if len(articles) >= min_articles:
                break
        if not payload.get("next_page"):
            break
        page += 1
    return articles


def scrape_help_center(
    base_url: str | None = None,
    locale: str | None = None,
    min_articles: int | None = None,
    articles_dir: str | Path | None = None,
) -> list[ScrapedArticle]:
    """Scrape help-center articles and write Markdown files to disk."""
    resolved_base = (base_url or os.getenv("HELP_CENTER_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    resolved_locale = locale or os.getenv("HELP_CENTER_LOCALE") or DEFAULT_LOCALE
    resolved_min = min_articles
    if resolved_min is None:
        resolved_min = int(os.getenv("MIN_ARTICLES", str(DEFAULT_MIN_ARTICLES)))
    output_dir = Path(articles_dir or os.getenv("ARTICLES_DIR") or DEFAULT_ARTICLES_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    scraped: list[ScrapedArticle] = []
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        raw_articles = fetch_articles(resolved_base, resolved_locale, resolved_min, client)
        for article in raw_articles:
            article_id = str(article["id"])
            title = (article.get("title") or article.get("name") or f"article-{article_id}").strip()
            html_url = article.get("html_url") or f"{resolved_base}/hc/{resolved_locale}/articles/{article_id}"
            updated_at = article.get("updated_at") or ""
            body_markdown = html_body_to_markdown(article.get("body") or "", resolved_base)
            markdown = build_markdown_document(title, html_url, body_markdown)
            slug = build_slug(title, article_id)
            filepath = output_dir / f"{slug}.md"
            filepath.write_text(markdown, encoding="utf-8")
            scraped.append(
                ScrapedArticle(
                    article_id=article_id,
                    slug=slug,
                    title=title,
                    html_url=html_url,
                    updated_at=updated_at,
                    markdown=markdown,
                    content_hash=compute_content_hash(markdown),
                    filepath=filepath,
                    char_count=len(markdown),
                )
            )
    return scraped
