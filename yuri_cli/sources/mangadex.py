from __future__ import annotations

import urllib.parse
from typing import List

from yuri_cli.http import get_json
from yuri_cli.models import Chapter, Page, SearchResult

_YURI_TAG = "423e2eae-a7a2-4a8b-ac03-a8351462d71d"
_BASE      = "https://api.mangadex.org"


def search(query: str, limit: int = 20) -> List[SearchResult]:
    params = urllib.parse.urlencode([
        ("title",            query),
        ("includedTags[]",   _YURI_TAG),
        ("limit",            limit),
        ("contentRating[]",  "safe"),
        ("contentRating[]",  "suggestive"),
        ("contentRating[]",  "erotica"),
        ("includes[]",       "cover_art"),
        ("order[relevance]", "desc"),
    ])
    data = get_json(f"{_BASE}/manga?{params}")
    results = []
    for item in data.get("data", []):
        attr     = item["attributes"]
        manga_id = item["id"]
        title = (
            attr["title"].get("en")
            or attr["title"].get("ja-ro")
            or next(iter(attr["title"].values()), "unknown")
        )
        tags = [t["attributes"]["name"].get("en", "") for t in attr.get("tags", [])]
        cover_url = ""
        for rel in item.get("relationships", []):
            if rel["type"] == "cover_art":
                fname = rel.get("attributes", {}).get("fileName", "")
                if fname:
                    cover_url = f"https://uploads.mangadex.org/covers/{manga_id}/{fname}.256.jpg"
                break
        results.append(SearchResult(
            source      = "mangadex",
            id          = manga_id,
            title       = title,
            kind        = "manga",
            tags        = tags,
            description = (attr.get("description") or {}).get("en", ""),
            cover_url   = cover_url,
        ))
    return results


def chapters(manga_id: str, lang: str = "en") -> List[Chapter]:
    collected = []
    offset    = 0
    limit     = 100
    while True:
        params = urllib.parse.urlencode([
            ("translatedLanguage[]", lang),
            ("order[chapter]",       "asc"),
            ("limit",                limit),
            ("offset",               offset),
            ("contentRating[]",      "safe"),
            ("contentRating[]",      "suggestive"),
            ("contentRating[]",      "erotica"),
            ("includes[]",           "scanlation_group"),
        ])
        data  = get_json(f"{_BASE}/manga/{manga_id}/feed?{params}")
        items = data.get("data", [])
        for item in items:
            attr = item["attributes"]
            if attr.get("externalUrl"):
                continue
            raw_num = attr.get("chapter") or "0"
            try:
                num = float(raw_num)
            except ValueError:
                num = 0.0
            collected.append(Chapter(
                id     = item["id"],
                title  = attr.get("title") or f"chapter {raw_num}",
                number = num,
                source = "mangadex",
            ))
        total   = data.get("total", 0)
        offset += limit
        if offset >= total:
            break
    seen: set[float] = set()
    unique = []
    for ch in collected:
        if ch.number not in seen:
            seen.add(ch.number)
            unique.append(ch)
    return unique


def chapter_pages(chapter_id: str) -> List[str]:
    data      = get_json(f"{_BASE}/at-home/server/{chapter_id}")
    base_url  = data["baseUrl"]
    ch        = data["chapter"]
    return [f"{base_url}/data/{ch['hash']}/{fname}" for fname in ch["data"]]
