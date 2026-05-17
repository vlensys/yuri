from __future__ import annotations

import re
import urllib.parse
from html.parser import HTMLParser
from typing import List, Tuple

from yuri_cli.http import get_json
from yuri_cli.models import Chapter, SearchResult

BASE = "https://www.baka-tsuki.org"
API  = f"{BASE}/project/api.php"


def _api(**params) -> dict:
    params["format"] = "json"
    return get_json(f"{API}?{urllib.parse.urlencode(params)}")


def _query_variants(query: str) -> List[str]:
    variants = [query]
    normalized = re.sub(r"\s+", " ", query).strip()
    if normalized and normalized != query:
        variants.append(normalized)
    swapped = re.sub(r"\band\b", "to", normalized, flags=re.IGNORECASE)
    if swapped and swapped not in variants:
        variants.append(swapped)
    compact = re.sub(r"\b(and|to)\b", " ", normalized, flags=re.IGNORECASE)
    compact = re.sub(r"\s+", " ", compact).strip()
    if compact and compact not in variants:
        variants.append(compact)
    return variants


class _TextExtractor(HTMLParser):
    _BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "br", "div"}

    def __init__(self) -> None:
        super().__init__()
        self.segments: List[Tuple[str, str]] = []
        self._buf         = ""
        self._depth_skip  = 0

    def _flush(self) -> None:
        text = re.sub(r"\n{3,}", "\n\n", self._buf).strip()
        if text:
            self.segments.append(("text", text))
        self._buf = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        a   = dict(attrs)
        cls = a.get("class", "")
        if tag in ("table", "script", "style") or "toc" in cls or "editsection" in cls:
            self._depth_skip += 1
            return
        if self._depth_skip:
            return
        if tag == "img":
            src = a.get("src", "")
            m   = re.search(r"/images(?:/thumb)?/[^/]+/[^/]+/([^/]+?)(?:/\d+px-.+)?$", src)
            if m:
                self._flush()
                self.segments.append(("image", m.group(1)))
        if tag in self._BLOCK_TAGS:
            self._buf += "\n"

    def handle_endtag(self, tag: str) -> None:
        if self._depth_skip:
            if tag in ("table", "script", "style"):
                self._depth_skip -= 1
            return
        if tag in self._BLOCK_TAGS:
            self._buf += "\n"

    def handle_data(self, data: str) -> None:
        if not self._depth_skip:
            self._buf += data

    def result(self) -> List[Tuple[str, str]]:
        self._flush()
        return self.segments


def search(query: str, limit: int = 20) -> List[SearchResult]:
    results = []
    seen: set[str] = set()
    for variant in _query_variants(query):
        data = _api(action="query", list="search", srsearch=variant, srnamespace=0, srlimit=limit)
        hits = data.get("query", {}).get("search", [])
        for hit in hits:
            title = hit["title"]
            if "/" in title or title in seen:
                continue
            seen.add(title)
            results.append(SearchResult(
                source = "baka_tsuki",
                id     = title,
                title  = title,
                kind   = "novel",
                tags   = ["yuri"],
            ))
            if len(results) >= limit:
                return results
        if results:
            break
    return results


def chapters(page_title: str) -> List[Chapter]:
    data     = _api(action="parse", page=page_title, prop="wikitext")
    wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
    pattern  = re.compile(r"\[\[(" + re.escape(page_title) + r"/[^\]|#]+)")
    seen: dict[str, bool] = {}
    result: List[Chapter] = []
    number = 1.0
    for m in pattern.finditer(wikitext):
        subpage = m.group(1).strip()
        if subpage in seen:
            continue
        seen[subpage] = True
        short = subpage[len(page_title) + 1:]
        result.append(Chapter(
            id     = subpage,
            title  = short.replace("_", " "),
            number = number,
            source = "baka_tsuki",
        ))
        number += 1.0
    return result


def chapter_content(page_title: str) -> List[Tuple[str, str]]:
    data = _api(action="parse", page=page_title, prop="text")
    html = data.get("parse", {}).get("text", {}).get("*", "")
    extractor = _TextExtractor()
    extractor.feed(html)
    resolved = []
    for kind, value in extractor.result():
        if kind == "image":
            url = _image_url(value)
            if url:
                resolved.append(("image", url))
        else:
            resolved.append((kind, value))
    return resolved


def _image_url(filename: str) -> str:
    try:
        data  = _api(action="query", titles=f"File:{filename}", prop="imageinfo", iiprop="url")
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            info = page.get("imageinfo", [])
            if info:
                return info[0]["url"]
    except Exception:
        pass
    return ""
