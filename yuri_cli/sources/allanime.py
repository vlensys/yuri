from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from yuri_cli.http import get_json, post_json, request
from yuri_cli.models import Chapter, SearchResult

_API = "https://api.allanime.day/api"
_BASE = "allanime.day"
_REFERER = "https://allanime.day/"
_ORIGIN = "https://allanime.day"
_YURI_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:yuri|gl|girls?\s+love|girls?'?\s+love)(?![a-z0-9])",
    re.IGNORECASE,
)
_PROVIDERS = ("Default", "Yt-mp4", "S-mp4", "Luf-Mp4", "Fm-mp4")
_TOBEPARSED_KEY = hashlib.sha256(b"Xot36i3lK3:v1").hexdigest()
_EPISODE_HASH = "d405d0edd690624b66baba3068e0edc3ac90f1597d898a1ec8db4e5c43c00fec"


@dataclass
class Stream:
    url: str
    quality: str = "unknown"
    source: str = "allanime"
    referer: str = ""
    subtitle_url: str = ""


def _allanime_headers() -> dict:
    return {
        "Origin": _ORIGIN,
        "Referer": _REFERER,
    }


def _graphql(query: str, variables: dict) -> Any:
    return post_json(_API, {"query": query, "variables": variables}, headers=_allanime_headers())


def _show_text(show: dict) -> str:
    parts = [
        show.get("name", ""),
        show.get("description", ""),
        " ".join(str(tag) for tag in show.get("genres") or []),
        " ".join(str(tag) for tag in show.get("tags") or []),
    ]
    return " ".join(str(part) for part in parts if part)


def is_yuri_media(show: dict) -> bool:
    return bool(_YURI_PATTERN.search(_show_text(show)))


def search(query: str, limit: int = 20) -> List[SearchResult]:
    gql = """
    query (
      $search: SearchInput
      $limit: Int
      $page: Int
      $translationType: VaildTranslationTypeEnumType
      $countryOrigin: VaildCountryOriginEnumType
    ) {
      shows(
        search: $search
        limit: $limit
        page: $page
        translationType: $translationType
        countryOrigin: $countryOrigin
      ) {
        edges {
          _id
          name
          description
          genres
          tags
          thumbnail
          availableEpisodes
        }
      }
    }
    """
    data = _graphql(gql, {
        "search": {"allowAdult": False, "allowUnknown": False, "query": query},
        "limit": limit,
        "page": 1,
        "translationType": "sub",
        "countryOrigin": "ALL",
    })
    results: List[SearchResult] = []
    for show in data.get("data", {}).get("shows", {}).get("edges", []) or []:
        if not is_yuri_media(show):
            continue
        tags = [str(tag) for tag in (show.get("genres") or []) + (show.get("tags") or [])]
        results.append(SearchResult(
            source="allanime",
            id=show["_id"],
            title=show.get("name") or "unknown",
            kind="anime",
            tags=tags,
            description=show.get("description") or "",
            cover_url=show.get("thumbnail") or "",
        ))
    return results


def show(show_id: str) -> dict:
    gql = """
    query ($showId: String!) {
      show(_id: $showId) {
        _id
        name
        description
        genres
        tags
        thumbnail
        availableEpisodesDetail
      }
    }
    """
    data = _graphql(gql, {"showId": show_id})
    found = data.get("data", {}).get("show") or {}
    if not is_yuri_media(found):
        raise PermissionError("blocked: anime does not look like yuri/gl/girl love.")
    return found


def episodes(show_id: str) -> List[Chapter]:
    found = show(show_id)
    detail = found.get("availableEpisodesDetail") or {}
    values = detail.get("sub") or detail.get("dub") or []
    chapters: List[Chapter] = []
    for raw in values:
        label = str(raw)
        try:
            number = float(label)
        except ValueError:
            number = 0.0
        chapters.append(Chapter(
            id=label,
            title=f"episode {label}",
            number=number,
            source="allanime",
        ))
    return sorted(chapters, key=lambda chapter: chapter.number)


def _decode_source_path(value: str) -> str:
    if not value.startswith("--"):
        return value
    encoded = value[2:]
    chars = []
    for index in range(0, len(encoded), 2):
        pair = encoded[index:index + 2]
        if len(pair) == 2:
            chars.append(chr(int(pair, 16) ^ 0x38))
    return "".join(chars).replace("/clock", "/clock.json")


def _json_from_url(url: str, referer: str = _REFERER) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": referer,
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _provider_url(path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    return f"https://{_BASE}{path}"


def _variant_streams(master_url: str, referer: str) -> List[Stream]:
    text = request(master_url, headers={"Referer": referer}).decode(errors="replace")
    if "#EXTM3U" not in text:
        return [Stream(master_url, quality="hls", referer=referer)]
    streams: List[Stream] = []
    base_url = master_url.rsplit("/", 1)[0] + "/"
    last_quality = "hls"
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-STREAM-INF"):
            if "RESOLUTION=" in line:
                resolution = line.split("RESOLUTION=", 1)[1].split(",", 1)[0]
                last_quality = resolution.rsplit("x", 1)[-1] + "p"
        elif line and not line.startswith("#"):
            streams.append(Stream(
                url=urllib.parse.urljoin(base_url, line),
                quality=last_quality,
                referer=referer,
            ))
    return streams or [Stream(master_url, quality="hls", referer=referer)]


def _streams_from_provider(path: str, source: str) -> List[Stream]:
    if path.startswith(("http://", "https://")) and "/clock" not in path:
        return [Stream(url=path, quality=source, source=source, referer=_REFERER)]
    provider_url = _provider_url(path)
    data = _json_from_url(provider_url)
    referer = ""
    subtitles = ""
    if isinstance(data, dict):
        referer = str(data.get("Referer") or data.get("referer") or "")
        for sub in data.get("subtitles") or []:
            if sub.get("lang") == "en" or sub.get("label") == "English":
                subtitles = sub.get("src") or ""
                break
    raw_items = data if isinstance(data, list) else data.get("links") or data.get("sources") or []
    streams: List[Stream] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        url = item.get("link") or item.get("url") or item.get("file")
        if not url:
            continue
        quality = str(item.get("resolutionStr") or item.get("height") or item.get("quality") or "unknown")
        if quality.isdigit():
            quality += "p"
        item_referer = referer or _REFERER
        if "master.m3u8" in url or item.get("type") == "hls":
            streams.extend(_variant_streams(url, item_referer))
        else:
            streams.append(Stream(url=url, quality=quality, referer=item_referer))
    for stream in streams:
        stream.source = source
        stream.subtitle_url = subtitles
    return streams


def _decode_tobeparsed(blob: str) -> List[dict]:
    with tempfile.TemporaryDirectory(prefix="yuri_allanime_") as tmp:
        encrypted = Path(tmp) / "payload.bin"
        encrypted.write_bytes(base64.b64decode(blob))
        raw = encrypted.read_bytes()
        if len(raw) < 30:
            return []
        iv = raw[1:13].hex() + "00000002"
        cipher = raw[13:-16]
        cipher_path = Path(tmp) / "cipher.bin"
        cipher_path.write_bytes(cipher)
        if not shutil.which("openssl"):
            return []
        result = subprocess.run(
            [
                "openssl", "enc", "-d", "-aes-256-ctr",
                "-K", _TOBEPARSED_KEY,
                "-iv", iv,
                "-nosalt",
                "-nopad",
                "-in", str(cipher_path),
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return []
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        episode = parsed.get("episode") or {}
        urls = episode.get("sourceUrls") or []
        return [item for item in urls if isinstance(item, dict)]
    return []


def _source_urls(show_id: str, episode: str, translation_type: str) -> List[dict]:
    gql = """
    query (
      $showId: String!
      $translationType: VaildTranslationTypeEnumType!
      $episodeString: String!
    ) {
      episode(
        showId: $showId
        translationType: $translationType
        episodeString: $episodeString
      ) {
        episodeString
        sourceUrls
      }
    }
    """
    variables = {
        "showId": show_id,
        "translationType": translation_type,
        "episodeString": episode,
    }
    extensions = {
        "persistedQuery": {
            "version": 1,
            "sha256Hash": _EPISODE_HASH,
        },
    }
    query = urllib.parse.urlencode({
        "variables": json.dumps(variables, separators=(",", ":")),
        "extensions": json.dumps(extensions, separators=(",", ":")),
    })
    data = get_json(
        f"{_API}?{query}",
        headers={
            "Origin": "https://youtu-chan.com",
            "Referer": "https://youtu-chan.com/",
        },
    )
    if data.get("data", {}).get("tobeparsed"):
        return _decode_tobeparsed(data["data"]["tobeparsed"])
    if not data.get("data", {}).get("episode"):
        data = _graphql(gql, variables)
    episode_data = data.get("data", {}).get("episode") or {}
    urls = episode_data.get("sourceUrls") or []
    if isinstance(urls, dict) and "tobeparsed" in urls:
        return _decode_tobeparsed(urls["tobeparsed"])
    return [item for item in urls if isinstance(item, dict)]


def streams(show_id: str, episode: str, translation_type: str = "sub") -> List[Stream]:
    show(show_id)
    collected: List[Stream] = []
    provider_sources: List[tuple[str, str]] = []
    for source in _source_urls(show_id, episode, translation_type):
        source_name = source.get("sourceName") or ""
        source_url = _decode_source_path(source.get("sourceUrl") or "")
        if not source_url:
            continue
        if source_url.startswith(("http://", "https://")):
            try:
                collected.extend(_streams_from_provider(source_url, source_name))
            except Exception:
                continue
        elif source_name in _PROVIDERS:
            provider_sources.append((source_url, source_name))
    if collected:
        return sorted(collected, key=_stream_sort_key, reverse=True)
    for source_url, source_name in provider_sources:
        try:
            collected.extend(_streams_from_provider(source_url, source_name))
        except Exception:
            continue
    return sorted(collected, key=_stream_sort_key, reverse=True)


def _stream_sort_key(stream: Stream) -> tuple:
    digits = "".join(ch for ch in stream.quality if ch.isdigit())
    quality = int(digits) if digits else 0
    return quality, stream.source != "Fm-mp4"
