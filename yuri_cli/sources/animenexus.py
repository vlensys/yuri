import urllib.parse
from dataclasses import dataclass
from typing import List, Optional

from yuri_cli.http import get_json
from yuri_cli.models import Chapter, SearchResult

_BASE = "https://api.anime.nexus"

_HEADERS = {
    "Referer": "https://anime.nexus/",
    "Origin": "https://anime.nexus",
}

_SEARCH_INCLUDES = ["poster", "genres"]
_EPISODE_INCLUDES = ["videos"]


@dataclass
class Stream:
    url: str
    referer: Optional[str] = None
    subtitle_url: Optional[str] = None


def _build_url(path: str, params: dict) -> str:
    return f"{_BASE}{path}?{urllib.parse.urlencode(params, doseq=True)}"


def _extract_tags(item: dict) -> List[str]:
    tags = []
    for g in item.get("genres") or []:
        if isinstance(g, dict):
            label = g.get("name") or g.get("slug") or ""
            tags.append(label)
        elif isinstance(g, str):
            tags.append(g)
    return [t for t in tags if t]


def search(query: str) -> List[SearchResult]:
    params = {
        "search": query,
        "sortBy": "name asc",
        "page": 1,
        "includes[]": _SEARCH_INCLUDES,
        "hasVideos": 1,
    }
    data = get_json(_build_url("/api/anime/shows", params), headers=_HEADERS)
    results = []
    for item in data.get("data") or []:
        show_id = str(item.get("id") or item.get("slug") or "")
        title = item.get("name") or item.get("title") or ""
        tags = _extract_tags(item)
        kind = _map_kind(item.get("type") or item.get("kind") or "anime")
        results.append(
            SearchResult(
                source="animenexus",
                id=show_id,
                title=title,
                tags=tags,
                kind=kind,
            )
        )
    return results


def episodes(show_id: str, mode: str) -> List[Chapter]:
    params = {
        "includes[]": _EPISODE_INCLUDES,
        "lang": mode,
    }
    data = get_json(
        _build_url(f"/api/anime/shows/{show_id}/episodes", params),
        headers=_HEADERS,
    )
    items = data.get("data") or data.get("episodes") or []
    chapters = []
    for ep in items:
        ep_id = str(ep.get("id") or ep.get("episode_id") or ep.get("number") or "")
        number_raw = ep.get("number") or ep.get("episode_number") or 0
        try:
            number = float(number_raw)
        except (TypeError, ValueError):
            number = 0.0
        title_str = (
            ep.get("title")
            or ep.get("name")
            or f"Episode {number_raw}"
        )
        chapters.append(Chapter(source="animenexus", id=ep_id, title=title_str, number=number))
    return chapters


def streams(show_id: str, episode_id: str, mode: str) -> List[Stream]:
    data = get_json(
        _build_url(f"/api/anime/shows/{show_id}/episodes/{episode_id}/streams", {"lang": mode}),
        headers=_HEADERS,
    )
    raw_streams = data.get("streams") or data.get("sources") or data.get("data") or []
    result = []
    for s in raw_streams:
        url = s.get("url") or s.get("src") or ""
        if not url:
            continue
        referer = s.get("referer") or s.get("headers", {}).get("Referer") or ""
        subtitle_url = None
        subs = s.get("subtitles") or s.get("tracks") or []
        for sub in subs:
            lang = (sub.get("lang") or sub.get("label") or "").lower()
            if "eng" in lang or lang == "en":
                subtitle_url = sub.get("url") or sub.get("file") or ""
                break
        if not subtitle_url and subs:
            subtitle_url = subs[0].get("url") or subs[0].get("file") or ""
        result.append(
            Stream(
                url=url,
                referer=referer or None,
                subtitle_url=subtitle_url or None,
            )
        )
    return result


def _map_kind(raw: str) -> str:
    raw = raw.lower()
    if raw in ("manga", "manhwa", "manhua", "comic"):
        return "manga"
    return "anime"
