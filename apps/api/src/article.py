"""Article extraction for the in-app news reader.

Two-stage pipeline:
  1. Fetch HTML using `requests` with a real browser User-Agent (trafilatura's
     built-in fetch is blocked by Yahoo Finance, WSJ, FT, etc.).
  2. Extract content via trafilatura on the HTML body.
  3. Fallback: BeautifulSoup-based "biggest text block" extraction if trafilatura
     returns nothing.

In-memory LRU cache (bounded) keyed by URL.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import requests
import trafilatura


CACHE_MAX = 256

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)
# NOTE: Brotli (`br`) is intentionally omitted from Accept-Encoding. `requests`
# only decompresses brotli responses when the `brotli` package is installed; a
# server that sees `br` in the header (e.g. 247wallst.com) will send brotli and
# we'd get back raw compressed bytes that trafilatura can't parse. Sticking to
# gzip + deflate keeps us safe regardless of the optional dep.
DEFAULT_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


@dataclass
class Article:
    url: str
    title: str | None
    site: str | None
    byline: str | None
    published: str | None
    content_html: str
    text: str
    fetched_at: str
    word_count: int


class ArticleCache:
    def __init__(self, capacity: int = CACHE_MAX) -> None:
        self._cap = capacity
        self._store: OrderedDict[str, Article] = OrderedDict()

    def get(self, url: str) -> Optional[Article]:
        if url in self._store:
            self._store.move_to_end(url)
            return self._store[url]
        return None

    def put(self, url: str, article: Article) -> None:
        self._store[url] = article
        self._store.move_to_end(url)
        while len(self._store) > self._cap:
            self._store.popitem(last=False)


_cache = ArticleCache()


def _hostname(url: str) -> str | None:
    try:
        return urlparse(url).hostname
    except Exception:
        return None


def _fetch_html(url: str, timeout: float = 15.0) -> str:
    """Fetch a URL with a browser-like User-Agent. Raises ValueError on failure."""
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        raise ValueError(f"network error: {e}") from e

    if resp.status_code >= 400:
        raise ValueError(f"HTTP {resp.status_code} from {_hostname(url)}")
    body = resp.text
    if not body or len(body) < 200:
        raise ValueError(f"empty response body from {_hostname(url)}")
    return body


def _fallback_extract(html: str) -> tuple[str, str]:
    """Crude extractor: strip tags from the biggest <article> / <main> block.

    Used only when trafilatura returns nothing. Returns (html, text).
    """
    # Strip script/style first
    cleaned = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Try to isolate the main article container
    for pat in (
        r"<article[^>]*>(.*?)</article>",
        r"<main[^>]*>(.*?)</main>",
        r'<div[^>]*class="[^"]*(?:article|content|story)[^"]*"[^>]*>(.*?)</div>',
    ):
        m = re.search(pat, cleaned, flags=re.DOTALL | re.IGNORECASE)
        if m:
            block = m.group(1)
            text = re.sub(r"<[^>]+>", " ", block)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 200:
                # Wrap in a single <p> per paragraph break
                paragraphs = re.split(r"(?:\n\s*\n|\.\s{2,})", text)
                html_out = "".join(f"<p>{p.strip()}.</p>" for p in paragraphs if len(p.strip()) > 30)
                return html_out, text
    return "", ""


def _extract_title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.DOTALL | re.IGNORECASE)
    if m:
        t = re.sub(r"\s+", " ", m.group(1)).strip()
        return t or None
    return None


def fetch_article(url: str, force: bool = False) -> Article:
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must be http(s)")

    if not force:
        cached = _cache.get(url)
        if cached is not None:
            return cached

    # Stage 1: fetch with a real browser UA so Yahoo/WSJ/FT don't block.
    html = _fetch_html(url)

    # Stage 2: trafilatura extract on the HTML body
    extracted_html = trafilatura.extract(
        html,
        output_format="html",
        include_links=True,
        include_images=False,
        include_tables=True,
        with_metadata=False,
        favor_recall=True,
    )
    text = trafilatura.extract(html, output_format="txt", favor_recall=True) or ""
    metadata = trafilatura.extract_metadata(html)

    # Stage 3: fallback if trafilatura found nothing
    if not extracted_html or len(text) < 80:
        fb_html, fb_text = _fallback_extract(html)
        if fb_html:
            extracted_html = fb_html
            text = fb_text

    title = (getattr(metadata, "title", None) if metadata else None) or _extract_title(html)

    if not extracted_html:
        # Page fetched OK but extraction yielded nothing (landing page, JS-heavy,
        # or auth-wall). Return a minimal "view original" card instead of 502-ing.
        extracted_html = (
            f'<p>This page could not be extracted automatically — it may require JavaScript or login.</p>'
            f'<p><a href="{url}" target="_blank" rel="noopener">View original on {_hostname(url)}</a></p>'
        )
        text = f"View original: {url}"

    article = Article(
        url=url,
        title=title,
        site=(getattr(metadata, "sitename", None) if metadata else None) or _hostname(url),
        byline=getattr(metadata, "author", None) if metadata else None,
        published=getattr(metadata, "date", None) if metadata else None,
        content_html=extracted_html,
        text=text,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        word_count=len(text.split()) if text else 0,
    )
    _cache.put(url, article)
    return article
