import urllib.parse
from dataclasses import dataclass
from typing import List, Optional

from yuri_cli.http import get_json
from yuri_cli.models import Chapter, SearchResult

_BASE = "https://anixplay.buzz"
_REFERER = "https://anizen.tr/"


@dataclass
class Stream:
    url: str
    referer: Optional[str] = None
    subtitle_url: Optional[str] = None
    source: str = "anixplay"


def _build_url(path: str, params: dict) -> str:
    return f"{_BASE}{path}?{urllib.parse.urlencode(params)}"


def _unwrap_results(data: dict):
    return data.get("results") or {}


def _info(show_id: str) -> dict:
    data = get_json(_build_url("/api/info", {"id": show_id}))
    return (_unwrap_results(data).get("data") or {})


def _tags_from_info(info: dict) -> List[str]:
    anime_info = info.get("animeInfo") or {}
    tags = []
    for key in ("Genres", "Studios", "Producers"):
        raw = anime_info.get(key) or []
        if isinstance(raw, list):
            tags.extend(str(item) for item in raw if item)
    return tags


def _search_queries(query: str) -> List[str]:
    queries = [query]
    replacements = {
        "villainness": "villainess",
        "girlfriend": "lover",
        "i'll": "ill",
        "i'm": "im",
    }
    normalized = query.lower()
    for old, new in replacements.items():
        if old in normalized:
            queries.append(normalized.replace(old, new))
    if "freaking way" in normalized:
        queries.append("watanare")
    if "villain" in normalized:
        queries.append("villainess")
        queries.append("watashi no oshi")
    return list(dict.fromkeys(q for q in queries if q.strip()))


def search(query: str) -> List[SearchResult]:
    seen = set()
    results: List[SearchResult] = []
    for search_query in _search_queries(query):
        data = get_json(_build_url("/api/search", {"keyword": search_query}))
        items = (_unwrap_results(data).get("data") or [])
        for item in items:
            show_id = str(item.get("id") or "")
            title = item.get("title") or item.get("jname") or ""
            if not show_id or not title or show_id in seen:
                continue
            seen.add(show_id)

            tags = []
            try:
                tags = _tags_from_info(_info(show_id))
            except Exception:
                pass

            tv_info = item.get("tvInfo") or {}
            results.append(
                SearchResult(
                    source="anixplay",
                    id=show_id,
                    title=title,
                    kind="anime",
                    tags=tags,
                    description=item.get("jname") or "",
                    cover_url=item.get("poster") or "",
                )
            )
            show_type = str(tv_info.get("showType") or "").strip()
            if show_type:
                results[-1].tags.append(show_type)
    return results


def episodes(show_id: str, mode: str) -> List[Chapter]:
    info = _info(show_id)
    raw_episodes = ((info.get("episodes") or {}).get("episodes") or [])
    chapters: List[Chapter] = []
    for ep in raw_episodes:
        if mode == "dub" and not ep.get("hasDub"):
            continue
        if mode == "sub" and not ep.get("hasSub"):
            continue
        number_raw = ep.get("episode_no") or 0
        try:
            number = float(number_raw)
        except (TypeError, ValueError):
            number = 0.0
        title = ep.get("title") or f"episode {number_raw}"
        chapters.append(
            Chapter(
                source="anixplay",
                id=str(int(number) if number == int(number) else number),
                title=title,
                number=number,
            )
        )
    return chapters


def streams(show_id: str, episode_id: str, mode: str) -> List[Stream]:
    data = get_json(
        _build_url(
            "/api/stream",
            {"id": f"{show_id}?ep={episode_id}", "type": mode},
        )
    )
    results = _unwrap_results(data)
    streams_out: List[Stream] = []

    streaming_link = results.get("streamingLink") or {}
    link = streaming_link.get("link") or {}
    url = link.get("file") or streaming_link.get("iframe") or ""
    if url:
        streams_out.append(Stream(url=url, referer=_REFERER, source=streaming_link.get("server") or "anixplay"))

    for server in results.get("servers") or []:
        embed = server.get("embed") or ""
        if not embed or any(stream.url == embed for stream in streams_out):
            continue
        streams_out.append(
            Stream(
                url=embed,
                referer=_REFERER,
                source=server.get("serverName") or "anixplay",
            )
        )
    return streams_out
