from __future__ import annotations

import urllib.parse
from html.parser import HTMLParser
from typing import List, Optional

from yuri_cli.http import get_json, request
from yuri_cli.models import Chapter, SearchResult

BASE = "https://dynasty-scans.com"


class _SearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: List[dict] = []
        self._in_link = False
        self._current: Optional[dict] = None

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        if tag == "a":
            href = a.get("href", "")
            if href.startswith("/series/"):
                self._current = {"slug": href[len("/series/"):], "title": "", "cover": ""}
                self._in_link = True
        if tag == "img" and self._current is not None:
            src = a.get("src", "")
            if src:
                self._current["cover"] = BASE + src if src.startswith("/") else src

    def handle_data(self, data: str) -> None:
        if self._in_link and self._current is not None:
            self._current["title"] += data.strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_link:
            self._in_link = False
            if self._current and self._current["title"]:
                self.results.append(self._current)
            self._current = None


def search(query: str, limit: int = 20) -> List[SearchResult]:
    params = urllib.parse.urlencode([("q", query), ("classes[]", "Series")])
    html   = request(f"{BASE}/search?{params}").decode("utf-8", errors="replace")
    parser = _SearchParser()
    parser.feed(html)
    results = []
    seen: set[str] = set()
    for item in parser.results:
        slug = item["slug"]
        if slug in seen:
            continue
        seen.add(slug)
        results.append(SearchResult(
            source    = "dynasty",
            id        = slug,
            title     = item["title"] or slug.replace("_", " ").title(),
            kind      = "novel",
            tags      = ["yuri"],
            cover_url = item["cover"],
        ))
        if len(results) >= limit:
            break
    return results


def chapters(series_slug: str) -> List[Chapter]:
    data     = get_json(f"{BASE}/series/{series_slug}.json")
    taggings = data.get("taggings", [])
    result   = []
    number   = 1.0
    for entry in taggings:
        if "permalink" not in entry or entry.get("header"):
            continue
        result.append(Chapter(
            id     = entry["permalink"],
            title  = entry.get("title") or f"chapter {int(number)}",
            number = number,
            source = "dynasty",
        ))
        number += 1.0
    return result


def chapter_pages(chapter_slug: str) -> List[str]:
    data = get_json(f"{BASE}/chapters/{chapter_slug}.json")
    urls = []
    for p in data.get("pages", []):
        url = p.get("url", "")
        if not url or p.get("type") == "transition":
            continue
        urls.append(url if url.startswith("http") else BASE + url)
    return urls
