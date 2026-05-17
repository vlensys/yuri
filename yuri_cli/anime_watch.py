import shutil
import subprocess
import sys
import time
from typing import List, Optional

from yuri_cli.lock import filter_kind
from yuri_cli.models import Chapter, SearchResult
from yuri_cli.reader import pick
from yuri_cli.sources import allanime


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


def _play(stream: allanime.Stream, title: str, episode: str) -> Optional[subprocess.Popen]:
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


def _episodes(show_id: str, mode: str) -> List[Chapter]:
    return allanime.episodes(show_id, mode)


def _pick_episode(episodes: List[Chapter]) -> Optional[int]:
    ep_labels = [ep.title for ep in episodes]
    return pick(ep_labels, "select episode")


def _play_episode(
    chosen: SearchResult,
    episode: Chapter,
    mode: str,
) -> Optional[subprocess.Popen]:
    print(f"\n{chosen.title} - {episode.title} [{mode}]")
    print("loading stream...")
    try:
        streams = allanime.streams(chosen.id, episode.id, mode)
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
    mode = "sub"
    print(f"fetching {mode} episodes...")
    try:
        episodes: List[Chapter] = _episodes(chosen.id, mode)
    except PermissionError as exc:
        sys.exit(str(exc))
    except Exception as exc:
        sys.exit(f"could not fetch episodes: {exc}")

    if not episodes:
        sys.exit("no subbed episodes found.")

    ep_idx = _pick_episode(episodes)
    if ep_idx is None:
        sys.exit("cancelled.")

    player: Optional[subprocess.Popen] = None
    try:
        while True:
            _stop_player(player)
            player = _play_episode(chosen, episodes[ep_idx], mode)
            action = _next_action(mode)

            if action == "q":
                break
            if action == "p":
                ep_idx = max(0, ep_idx - 1)
            elif action == "r":
                pass
            elif action == "e":
                picked = _pick_episode(episodes)
                if picked is not None:
                    ep_idx = picked
            elif action == "d":
                new_mode = "dub" if mode == "sub" else "sub"
                print(f"fetching {new_mode} episodes...")
                try:
                    new_episodes = _episodes(chosen.id, new_mode)
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
