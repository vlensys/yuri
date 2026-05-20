from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from html import unescape
from html.parser import HTMLParser

from yuri_cli.lock import looks_yuri
from yuri_cli.models import Chapter, SearchResult

_BASE = "https://dynasty-scans.com"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
}


def _fetch(path: str) -> str:
    url = path if path.startswith("http") else _BASE + path
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _source_id(path: str) -> str:
    return path if path.startswith("/") else "/" + path


def _source_url(path: str) -> str:
    return path if path.startswith("http") else _BASE + path


def _kind_from_tags(title: str, tags: list[str]) -> str:
    text = " ".join([title, *tags]).lower()
    if "light/web novel" in text or "lightweb novel" in text or "text" in text:
        return "novel"
    return "manga"


class _SearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[SearchResult] = []
        self._in_dd = False
        self._in_name = False
        self._in_tag = False
        self._cur_href = ""
        self._cur_title = ""
        self._cur_tags: list[str] = []
        self._tag_buf = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        cls = a.get("class", "")
        if tag == "dd":
            self._in_dd = True
            self._cur_href = ""
            self._cur_title = ""
            self._cur_tags = []
            return
        if not self._in_dd:
            return
        if tag == "a" and "name" in cls and not self._cur_href:
            href = a.get("href", "")
            if href.startswith(("/series/", "/chapters/", "/anthologies/", "/doujins/")):
                self._cur_href = href
                self._in_name = True
            return
        if tag == "a" and "label" in cls:
            self._in_tag = True
            self._tag_buf = ""

    def handle_endtag(self, tag: str) -> None:
        if self._in_name and tag == "a":
            self._in_name = False
            return
        if self._in_tag and tag == "a":
            tag_text = unescape(self._tag_buf).strip()
            if tag_text:
                self._cur_tags.append(tag_text)
            self._in_tag = False
            return
        if self._in_dd and tag == "dd":
            self._finish()

    def handle_data(self, data: str) -> None:
        if self._in_name:
            self._cur_title += data
        elif self._in_tag:
            self._tag_buf += data

    def _finish(self) -> None:
        title = unescape(self._cur_title).strip()
        if self._cur_href and title and any(looks_yuri(tag) for tag in self._cur_tags):
            self.results.append(SearchResult(
                source="dynasty",
                id=_source_id(self._cur_href),
                title=title,
                kind=_kind_from_tags(title, self._cur_tags),
                tags=list(self._cur_tags),
            ))
        self._in_dd = False
        self._in_name = False
        self._in_tag = False


class _ChapterParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.chapters: list[Chapter] = []
        self._in_name = False
        self._cur_href = ""
        self._cur_title = ""
        self._index = 0
        self._cur_volume = ""
        self._in_dt = False
        self._dt_buf = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        if tag == "dt":
            self._in_dt = True
            self._dt_buf = ""
            return
        if tag == "a" and "name" in a.get("class", "") and not self._in_dt:
            href = a.get("href", "")
            if href.startswith("/chapters/"):
                self._cur_href = href
                self._cur_title = ""
                self._in_name = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "dt":
            vol = unescape(self._dt_buf).strip()
            if vol:
                self._cur_volume = vol
            self._in_dt = False
            return
        if self._in_name and tag == "a":
            title = unescape(self._cur_title).strip()
            if self._cur_href and title:
                self._index += 1
                self.chapters.append(Chapter(
                    id=_source_id(self._cur_href),
                    title=title,
                    number=float(self._index),
                    source="dynasty",
                    volume=self._cur_volume,
                ))
            self._in_name = False

    def handle_data(self, data: str) -> None:
        if self._in_name:
            self._cur_title += data
        elif self._in_dt:
            self._dt_buf += data


def search(query: str, limit: int = 20) -> list[SearchResult]:
    params = urllib.parse.urlencode({"q": query})
    html = _fetch(f"/search?{params}")
    parser = _SearchParser()
    parser.feed(html)
    seen_ids: set[str] = set()
    seen_novel_series: set[str] = set()
    results: list[SearchResult] = []
    for result in parser.results:
        if result.id in seen_ids:
            continue
        if result.kind == "novel" and result.id.startswith("/chapters/"):
            key = _novel_series_key(result.title)
            if key in seen_novel_series:
                continue
            seen_novel_series.add(key)
            result = SearchResult(
                source=result.source,
                id=result.id,
                title=key,
                kind=result.kind,
                tags=result.tags,
            )
        seen_ids.add(result.id)
        results.append(result)
        if len(results) >= limit:
            break
    return results


def chapters(path: str) -> list[Chapter]:
    if path.startswith("/chapters/"):
        html = _fetch(path)
        series_path = _series_from_chapter(html)
        if series_path:
            return chapters(series_path)
        title = _chapter_title(html) or path.rsplit("/", 1)[-1].replace("_", " ")
        return [Chapter(id=_source_id(path), title=title, number=1.0, source="dynasty")]
    html = _fetch(path)
    parser = _ChapterParser()
    parser.feed(html)
    return parser.chapters


def chapter_pages(path: str) -> list[str]:
    html = _fetch(path)
    match = re.search(r"var\s+pages\s*=\s*(\[.*?\]);", html, re.DOTALL)
    if not match:
        return []
    pages = json.loads(match.group(1))
    urls: list[str] = []
    for page in pages:
        image = page.get("image", "")
        if image:
            urls.append(_source_url(image))
    return urls


def _chapter_title(html: str) -> str:
    match = re.search(r"<h3[^>]*id=['\"]chapter-title['\"][^>]*>\s*<b>(.*?)</b>", html, re.DOTALL)
    if not match:
        return ""
    text = re.sub(r"<[^>]+>", "", match.group(1))
    return unescape(text).strip()


def _series_from_chapter(html: str) -> str:
    match = re.search(r'<h3[^>]*id=["\']chapter-title["\'].*?<a\s+href="(/series/[^"]+)"', html, re.DOTALL)
    return match.group(1) if match else ""


def _novel_series_key(title: str) -> str:
    return re.sub(r"\s+ch\d+.*$", "", title, flags=re.IGNORECASE).strip()
