from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

from yuri_cli.http import get_json
from yuri_cli.models import Chapter, SearchResult

_BASE = "https://anixplay.buzz"
_REFERER = "https://anizen.tr/"


@dataclass
class Stream:
    url: str
    referer: str | None = None
    subtitle_url: str | None = None
    source: str = "anixplay"


def _build_url(path: str, params: dict) -> str:
    return f"{_BASE}{path}?{urllib.parse.urlencode(params)}"


def _unwrap_results(data: dict):
    return data.get("results") or {}


def _info(show_id: str) -> dict:
    data = get_json(_build_url("/api/info", {"id": show_id}))
    return (_unwrap_results(data).get("data") or {})


def _tags_from_info(info: dict) -> list[str]:
    anime_info = info.get("animeInfo") or {}
    tags = []
    for key in ("Genres", "Studios", "Producers"):
        raw = anime_info.get(key) or []
        if isinstance(raw, list):
            tags.extend(str(item) for item in raw if item)
    return tags


def _search_queries(query: str) -> list[str]:
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


def search(query: str) -> list[SearchResult]:
    seen = set()
    results: list[SearchResult] = []
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


def episodes(show_id: str, mode: str) -> list[Chapter]:
    info = _info(show_id)
    raw_episodes = ((info.get("episodes") or {}).get("episodes") or [])
    chapters: list[Chapter] = []
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


def _resolve_player(player_url: str) -> Stream | None:
    try:
        resolve_req = urllib.request.Request(
            player_url + "/resolve",
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Referer": player_url,
                "X-Requested-With": "ZenPlayer",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(resolve_req, timeout=10) as resp:
            resolved = json.loads(resp.read())
        vidwish_url = resolved.get("url") or ""
        if not vidwish_url:
            return None

        page_req = urllib.request.Request(
            vidwish_url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Referer": _REFERER,
            },
        )
        with urllib.request.urlopen(page_req, timeout=10) as resp:
            html = resp.read().decode(errors="replace")

        data_id_match = re.search(r'data-id="(\d+)"', html)
        if not data_id_match:
            return None
        data_id = data_id_match.group(1)

        parsed_host = urllib.parse.urlparse(vidwish_url)
        get_sources_url = f"{parsed_host.scheme}://{parsed_host.netloc}/stream/getSources?id={data_id}"

        src_req = urllib.request.Request(
            get_sources_url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Referer": vidwish_url,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(src_req, timeout=10) as resp:
            sources_data = json.loads(resp.read())

        hls_url = (sources_data.get("sources") or {}).get("file") or ""
        if not hls_url:
            return None

        subtitle_url = ""
        for track in sources_data.get("tracks") or []:
            if track.get("kind") == "captions" and track.get("label") == "English":
                subtitle_url = track.get("file") or ""
                break

        return Stream(url=hls_url, referer=vidwish_url, subtitle_url=subtitle_url, source="vidwish")
    except Exception:
        return None


def streams(show_id: str, episode_id: str, mode: str) -> list[Stream]:
    data = get_json(
        _build_url(
            "/api/stream",
            {"id": f"{show_id}?ep={episode_id}", "type": mode},
        )
    )
    results = _unwrap_results(data)

    player_urls: list[tuple[str, str]] = []
    streaming_link = results.get("streamingLink") or {}
    link = streaming_link.get("link") or {}
    primary_url = link.get("file") or ""
    if primary_url and "aniapi.anizen.tr/player/" in primary_url:
        player_urls.append((primary_url, streaming_link.get("server") or "anixplay"))

    for server in results.get("servers") or []:
        embed = server.get("embed") or ""
        if embed and "aniapi.anizen.tr/player/" in embed and embed not in [u for u, _ in player_urls]:
            player_urls.append((embed, server.get("serverName") or "anixplay"))

    seen_urls: set[str] = set()
    streams_out: list[Stream] = []
    for player_url, source in player_urls:
        stream = _resolve_player(player_url)
        if stream is not None and stream.url not in seen_urls:
            seen_urls.add(stream.url)
            stream.source = source
            streams_out.append(stream)

    return streams_out
