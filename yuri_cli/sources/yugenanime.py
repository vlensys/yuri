from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import List, Optional

from yuri_cli.lock import looks_yuri
from yuri_cli.models import Chapter, SearchResult

_BASE = "https://yugenanime.tv"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}


@dataclass
class Stream:
    url: str
    referer: Optional[str] = None
    subtitle_url: Optional[str] = None


def _fetch(path: str, headers: Optional[dict] = None) -> str:
    url = path if path.startswith("http") else _BASE + path
    req = urllib.request.Request(url, headers={**_HEADERS, **(headers or {})})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _fetch_json(path: str, headers: Optional[dict] = None):
    url = path if path.startswith("http") else _BASE + path
    req = urllib.request.Request(url, headers={**_HEADERS, "Accept": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


class _SearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: List[SearchResult] = []
        self._in_card = False
        self._cur_id = ""
        self._cur_title = ""
        self._cur_tags: List[str] = []
        self._in_title = False
        self._in_genre = False
        self._depth = 0
        self._card_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        cls = a.get("class", "")
        if "anime-meta" in cls or "anime-card" in cls:
            href = a.get("href", "")
            if href and "/anime/" in href:
                self._in_card = True
                self._cur_id = href.rstrip("/").rsplit("/", 1)[-1]
                self._cur_title = ""
                self._cur_tags = []
                self._card_depth = self._depth
        if self._in_card:
            if tag == "h3" or (tag == "p" and "anime-name" in cls):
                self._in_title = True
            if tag == "a" and "genre" in cls:
                self._in_genre = True
        self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        self._depth -= 1
        if self._in_title and tag in ("h3", "p"):
            self._in_title = False
        if self._in_genre and tag == "a":
            self._in_genre = False
        if self._in_card and self._depth <= self._card_depth:
            self._finish()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._cur_title += data
        elif self._in_genre:
            self._cur_tags.append(data.strip())

    def _finish(self) -> None:
        title = unescape(self._cur_title).strip()
        if self._cur_id and title:
            self.results.append(SearchResult(
                source="yugenanime",
                id=self._cur_id,
                title=title,
                kind="anime",
                tags=[t for t in self._cur_tags if t],
            ))
        self._in_card = False
        self._cur_id = ""
        self._cur_title = ""
        self._cur_tags = []


def _parse_episodes(html: str, show_id: str) -> List[Chapter]:
    matches = re.findall(r'href=["\'](?:/watch/[^"\']*?|/[^"\']*?episode[^"\']*?)["\']', html)
    ep_nums: List[float] = []
    seen: set = set()
    for m in re.finditer(r'/watch/([^/"\']+)/(\d+(?:\.\d+)?)', html):
        slug = m.group(1)
        if slug != show_id:
            continue
        try:
            n = float(m.group(2))
        except ValueError:
            continue
        if n not in seen:
            seen.add(n)
            ep_nums.append(n)

    if not ep_nums:
        for m in re.finditer(r'data-episode=["\'](\d+(?:\.\d+)?)["\']', html):
            try:
                n = float(m.group(1))
            except ValueError:
                continue
            if n not in seen:
                seen.add(n)
                ep_nums.append(n)

    ep_nums.sort()
    return [
        Chapter(
            id=str(int(n) if n == int(n) else n),
            title=f"episode {int(n) if n == int(n) else n}",
            number=n,
            source="yugenanime",
        )
        for n in ep_nums
    ]


def search(query: str) -> List[SearchResult]:
    params = urllib.parse.urlencode({"q": query})
    html = _fetch(f"/search/?{params}")
    parser = _SearchParser()
    parser.feed(html)
    return [r for r in parser.results if looks_yuri(r.title) or any(looks_yuri(t) for t in r.tags)]


def episodes(show_id: str, mode: str) -> List[Chapter]:
    html = _fetch(f"/anime/{show_id}/")
    chapters = _parse_episodes(html, show_id)
    if not chapters:
        try:
            data = _fetch_json(f"/api/anime/{show_id}/episodes/")
            items = data if isinstance(data, list) else data.get("episodes") or data.get("data") or []
            seen: set = set()
            for item in items:
                raw = item.get("number") or item.get("episode") or item.get("num") or ""
                try:
                    n = float(raw)
                except (TypeError, ValueError):
                    continue
                if n in seen:
                    continue
                seen.add(n)
                ep_id = str(int(n) if n == int(n) else n)
                chapters.append(Chapter(
                    id=ep_id,
                    title=f"episode {ep_id}",
                    number=n,
                    source="yugenanime",
                ))
            chapters.sort(key=lambda c: c.number)
        except Exception:
            pass
    return chapters


def streams(show_id: str, episode_id: str, mode: str) -> List[Stream]:
    html = _fetch(f"/watch/{show_id}/{episode_id}/")

    srcs: List[Stream] = []

    for m in re.finditer(r'file\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']', html):
        srcs.append(Stream(url=m.group(1), referer=f"{_BASE}/"))

    iframe_matches = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html)
    for iframe_url in iframe_matches:
        if any(skip in iframe_url for skip in ("google", "facebook", "disqus")):
            continue
        srcs.append(Stream(url=iframe_url, referer=f"{_BASE}/"))

    for m in re.finditer(r'["\']?(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)["\']?', html):
        url = m.group(1)
        if url not in [s.url for s in srcs]:
            srcs.append(Stream(url=url, referer=f"{_BASE}/"))

    try:
        data = _fetch_json(
            f"/api/anime/{show_id}/episode/{episode_id}/sources/",
            headers={"Referer": f"{_BASE}/watch/{show_id}/{episode_id}/"},
        )
        raw = data if isinstance(data, list) else data.get("sources") or data.get("streams") or []
        for item in raw:
            url = item.get("url") or item.get("file") or item.get("src") or ""
            if url and url not in [s.url for s in srcs]:
                srcs.append(Stream(
                    url=url,
                    referer=f"{_BASE}/",
                ))
    except Exception:
        pass

    return srcs
