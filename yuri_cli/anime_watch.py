import shutil
import subprocess
import sys
from typing import List

from yuri_cli.lock import filter_kind
from yuri_cli.models import Chapter, SearchResult
from yuri_cli.reader import pick
from yuri_cli.sources import allanime


def _player() -> str:
    player = shutil.which("mpv")
    if not player:
        sys.exit("mpv is required to watch anime.")
    return player


def _play(stream: allanime.Stream, title: str, episode: str) -> None:
    command = [
        _player(),
        f"--force-media-title={title} episode {episode}",
    ]
    if stream.referer:
        command.append(f"--referrer={stream.referer}")
    if stream.subtitle_url:
        command.append(f"--sub-file={stream.subtitle_url}")
    command.append(stream.url)
    subprocess.run(command, check=False)


def run(name: str) -> None:
    print(f"searching allanime for '{name}'...")
    try:
        results: List[SearchResult] = allanime.search(name)
    except Exception as exc:
        sys.exit(f"search failed: {exc}")
    results = filter_kind(results, "anime")

    if not results:
        sys.exit("no yuri/gl anime results found.")

    labels = [f"{r.title}  [{', '.join(r.tags[:3])}]" for r in results]
    idx = pick(labels, "select anime")
    if idx is None:
        sys.exit("cancelled.")
    chosen = results[idx]

    print(f"\n{chosen.title}")
    print("fetching episodes...")
    try:
        episodes: List[Chapter] = allanime.episodes(chosen.id)
    except PermissionError as exc:
        sys.exit(str(exc))
    except Exception as exc:
        sys.exit(f"could not fetch episodes: {exc}")

    if not episodes:
        sys.exit("no subbed episodes found.")

    ep_labels = [ep.title for ep in episodes]
    ep_idx = pick(ep_labels, "select episode")
    if ep_idx is None:
        sys.exit("cancelled.")
    episode = episodes[ep_idx]

    print(f"\n{episode.title}")
    print("fetching streams...")
    try:
        streams = allanime.streams(chosen.id, episode.id)
    except PermissionError as exc:
        sys.exit(str(exc))
    except Exception as exc:
        sys.exit(f"could not fetch streams: {exc}")

    if not streams:
        sys.exit("no playable streams found.")

    stream_labels = [
        f"{stream.quality}  {stream.source}"
        for stream in streams
    ]
    stream_idx = pick(stream_labels, "select quality")
    stream = streams[0] if stream_idx is None else streams[stream_idx]

    _play(stream, chosen.title, episode.id)
