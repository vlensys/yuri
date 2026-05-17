from __future__ import annotations

from typing import List

from yuri_cli.http import post_json
from yuri_cli.lock import looks_yuri

BASE = "https://api.allanime.day/api"


def is_yuri_media(show: dict) -> bool:
    text = " ".join([
        str(show.get("name", "")),
        str(show.get("description", "")),
        " ".join(str(tag) for tag in show.get("genres", [])),
        " ".join(str(tag) for tag in show.get("tags", [])),
    ])
    return looks_yuri(text)


def episodes(show_id: str) -> List[int]:
    payload = {
        "variables": {"_id": show_id},
        "query": "query ($id: String) { show(_id: $id) { name description genres tags availableEpisodesDetail } }",
    }
    data = post_json(BASE, payload)
    show = data.get("data", {}).get("show") or {}
    if not is_yuri_media(show):
        raise PermissionError("blocked: anime does not look like yuri.")

    detail = show.get("availableEpisodesDetail") or {}
    return list(detail.get("sub") or detail.get("dub") or [])
