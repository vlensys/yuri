import shutil
import subprocess
import sys
import time
from typing import List, Optional

from yuri_cli.lock import filter_kind, filter_yuri
from yuri_cli.models import Chapter, SearchResult
from yuri_cli.progress import get_last, set_last
from yuri_cli.reader import pick
from yuri_cli.sources import allanime, animenexus


_WATCH_SOURCES = (("allanime", allanime),)


def _player() -> str:
    player = shutil.which("mpv")
    if not player:
        sys.exit("mpv is required to watch anime.")
    return player


def _stop_player(player: Optional[subprocess.Popen]) -> None:
    if player is None or player.poll() is not None:
        return
    player.terminate()
    try:
        player.wait(timeout=3)
    except subprocess.TimeoutExpired:
        player.kill()
        player.wait()


def _play(stream, title: str, episode: str) -> Optional[subprocess.Popen]:
    command = [
        _player(),
        "--really-quiet",
        "--no-terminal",
        f"--force-media-title={title} episode {episode}",
    ]
    if stream.referer:
        command.append(f"--referrer={stream.referer}")
    if stream.subtitle_url:
        command.append(f"--sub-file={stream.subtitle_url}")
    command.append(stream.url)
    try:
        player = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except KeyboardInterrupt:
        return None
    time.sleep(0.5)
    if player.poll() is not None:
        return None
    return player


def _search_all(name: str) -> List[SearchResult]:
    results: List[SearchResult] = []
    for source_name, source in _WATCH_SOURCES:
        try:
            results.extend(source.search(name))
        except Exception as exc:
            print(f"search failed for {source_name}: {exc}")
    return results


def _episodes(chosen: SearchResult, mode: str) -> List[Chapter]:
    if chosen.source == "allanime":
        return allanime.episodes(chosen.id, mode)
    return animenexus.episodes(chosen.id, mode)


def _streams(chosen: SearchResult, episode: Chapter, mode: str):
    if chosen.source == "allanime":
        return allanime.streams(chosen.id, episode.id, mode)
    return animenexus.streams(chosen.id, episode.id, mode)


def _episode_choices(episodes: List[Chapter], chosen: SearchResult) -> tuple[List[str], List[int]]:
    last_id = get_last(chosen.source, chosen.id)
    labels: List[str] = []
    indexes: List[int] = []
    if last_id:
        last_index = next((idx for idx, ep in enumerate(episodes) if ep.id == last_id), None)
        if last_index is not None:
            labels.append(f"last viewed  {episodes[last_index].title}")
            indexes.append(last_index)
    labels.extend(ep.title for ep in episodes)
    indexes.extend(range(len(episodes)))
    return labels, indexes


def _pick_episode(episodes: List[Chapter], chosen: SearchResult) -> Optional[int]:
    ep_labels, indexes = _episode_choices(episodes, chosen)
    picked = pick(ep_labels, "select episode")
    if picked is None:
        return None
    return indexes[picked]


def _play_episode(
    chosen: SearchResult,
    episode: Chapter,
    mode: str,
) -> Optional[subprocess.Popen]:
    print(f"\n{chosen.title} - {episode.title} [{mode}]")
    print("loading stream...")
    try:
        streams = _streams(chosen, episode, mode)
    except PermissionError as exc:
        sys.exit(str(exc))
    except Exception as exc:
        print(f"could not fetch streams: {exc}")
        return None

    if not streams:
        print("no playable streams found.")
        return None

    for stream in streams:
        player = _play(stream, chosen.title, episode.id)
        if player is not None:
            print(f"playing episode {episode.id} [{mode}]")
            return player
    print("all streams failed.")
    return None


def _next_action(mode: str) -> str:
    toggle_label = "toggle dub" if mode == "sub" else "toggle sub"
    try:
        raw = input(
            f"\n[{mode}] enter next  p previous  r replay  e episode  d {toggle_label}  q quit > "
        )
    except (EOFError, KeyboardInterrupt):
        return "q"
    return raw.strip().lower() or "n"


def run(name: str) -> None:
    print(f"searching for '{name}'...")
    results = _search_all(name)
    results = filter_kind(results, "anime")
    results = filter_yuri(results)

    if not results:
        sys.exit("no yuri/gl anime results found.")

    labels = [f"[{r.source}]  {r.title}  [{', '.join(r.tags[:3])}]" for r in results]
    idx = pick(labels, "select anime")
    if idx is None:
        sys.exit("cancelled.")
    chosen = results[idx]

    print(f"\n{chosen.title}")
    mode = "sub"
    print(f"fetching {mode} episodes...")
    try:
        raw_episodes: List[Chapter] = _episodes(chosen, mode)
    except PermissionError as exc:
        sys.exit(str(exc))
    except Exception as exc:
        sys.exit(f"could not fetch episodes: {exc}")

    if not raw_episodes:
        sys.exit("no subbed episodes found.")

    episodes = raw_episodes

    ep_idx = _pick_episode(episodes, chosen)
    if ep_idx is None:
        sys.exit("cancelled.")

    player: Optional[subprocess.Popen] = None
    try:
        while True:
            _stop_player(player)
            set_last(chosen.source, chosen.id, episodes[ep_idx].id)
            player = _play_episode(chosen, episodes[ep_idx], mode)
            action = _next_action(mode)

            if action == "q":
                break
            if action == "p":
                ep_idx = max(0, ep_idx - 1)
            elif action == "r":
                pass
            elif action == "e":
                picked = _pick_episode(episodes, chosen)
                if picked is not None:
                    ep_idx = picked
            elif action == "d":
                new_mode = "dub" if mode == "sub" else "sub"
                print(f"fetching {new_mode} episodes...")
                try:
                    new_episodes = _episodes(chosen, new_mode)
                except Exception as exc:
                    print(f"could not fetch {new_mode} episodes: {exc}")
                    continue
                if not new_episodes:
                    print(f"no {new_mode} episodes found.")
                    continue
                current_number = episodes[ep_idx].number
                mode = new_mode
                episodes = new_episodes
                ep_idx = min(
                    range(len(episodes)),
                    key=lambda index: abs(episodes[index].number - current_number),
                )
            else:
                if ep_idx >= len(episodes) - 1:
                    print("last episode.")
                else:
                    ep_idx += 1
    finally:
        _stop_player(player)
