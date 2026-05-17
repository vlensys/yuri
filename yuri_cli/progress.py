import json
import os
from pathlib import Path
from typing import Optional

_PROGRESS_FILE = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "yuri" / "progress.json"


def _load() -> dict:
    if not _PROGRESS_FILE.exists():
        return {}
    try:
        return json.loads(_PROGRESS_FILE.read_text())
    except Exception:
        return {}


def _save(data: dict) -> None:
    _PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PROGRESS_FILE.write_text(json.dumps(data, indent=2))


def _key(source: str, show_id: str) -> str:
    return f"{source}:{show_id}"


def get_last(source: str, show_id: str) -> Optional[str]:
    return _load().get(_key(source, show_id))


def set_last(source: str, show_id: str, episode_or_chapter_id: str) -> None:
    data = _load()
    data[_key(source, show_id)] = episode_or_chapter_id
    _save(data)
