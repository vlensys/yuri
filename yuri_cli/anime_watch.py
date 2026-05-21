from __future__ import annotations

import http.server
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse

from yuri_cli.lock import filter_kind, filter_yuri
from yuri_cli.models import Chapter, SearchResult
from yuri_cli.progress import get_last, set_last
from yuri_cli.reader import pick
from yuri_cli.sources import allanime, anixplay


_WATCH_SOURCES = (("allanime", allanime), ("anixplay", anixplay))
_CF_DOMAINS = ("fxpy7.watching.onl", "cinewave2.site", "cloudvideo.lat", "watching.onl")


def _needs_proxy(url: str) -> bool:
    return any(d in url for d in _CF_DOMAINS)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _curl_fetch(url: str, referer: str) -> tuple[int, bytes, str]:
    result = subprocess.run(
        [
            "curl", "-s", "-L",
            "--max-time", "20",
            "-H", f"Referer: {referer}",
            "-w", "\n__STATUS__%{http_code}",
            url,
        ],
        capture_output=True,
        timeout=25,
    )
    raw = result.stdout
    marker = b"\n__STATUS__"
    idx = raw.rfind(marker)
    if idx == -1:
        return 0, raw, "application/octet-stream"
    body = raw[:idx]
    status = int(raw[idx + len(marker):].strip() or b"0")
    return status, body, "application/octet-stream"


def _rewrite_m3u8(content: bytes, proxy_base: str, cdn_base: str, referer: str) -> bytes:
    text = content.decode(errors="replace")
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            lines.append(line)
            continue
        if not stripped:
            lines.append(line)
            continue
        if stripped.startswith("http://") or stripped.startswith("https://"):
            encoded = urllib.parse.quote(stripped, safe="")
            ref_encoded = urllib.parse.quote(referer, safe="")
            lines.append(f"{proxy_base}/p?u={encoded}&r={ref_encoded}")
        else:
            full = cdn_base.rstrip("/") + "/" + stripped.lstrip("/")
            encoded = urllib.parse.quote(full, safe="")
            ref_encoded = urllib.parse.quote(referer, safe="")
            lines.append(f"{proxy_base}/p?u={encoded}&r={ref_encoded}")
    return "\n".join(lines).encode()


def _make_proxy_handler(cdn_base: str, referer: str, proxy_base: str):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            if parsed.path == "/p":
                target_url = urllib.parse.unquote(params.get("u", [""])[0])
                ref = urllib.parse.unquote(params.get("r", [referer])[0])
            else:
                path = parsed.path.lstrip("/")
                target_url = cdn_base.rstrip("/") + "/" + path
                ref = referer

            status, body, _ = _curl_fetch(target_url, ref)
            if status == 0:
                status = 502

            ct = "application/octet-stream"
            if target_url.endswith(".m3u8") or b"#EXTM3U" in body[:20]:
                ct = "application/vnd.apple.mpegurl"
                body = _rewrite_m3u8(body, proxy_base, target_url.rsplit("/", 1)[0], ref)

            self.send_response(status)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:
            pass

    return Handler


def _start_hls_proxy(stream_url: str, referer: str) -> str:
    port = _free_port()
    proxy_base = f"http://127.0.0.1:{port}"

    parsed = urllib.parse.urlparse(stream_url)
    cdn_base = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rsplit('/', 1)[0]}"

    handler = _make_proxy_handler(cdn_base, referer, proxy_base)
    server = http.server.HTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    filename = stream_url.rsplit("/", 1)[-1]
    return f"{proxy_base}/{filename}"


_SOURCE_BY_NAME = dict(_WATCH_SOURCES)


def _player() -> str:
    player = shutil.which("mpv")
    if not player:
        sys.exit("mpv is required to watch anime.")
    return player


def _stop_player(player: subprocess.Popen | None) -> None:
    if player is None or player.poll() is not None:
        return
    player.terminate()
    try:
        player.wait(timeout=3)
    except subprocess.TimeoutExpired:
        player.kill()
        player.wait()


def _play(stream, title: str, episode: str) -> subprocess.Popen | None:
    url = stream.url
    if _needs_proxy(url):
        url = _start_hls_proxy(url, stream.referer or "")

    command = [
        _player(),
        "--really-quiet",
        "--no-terminal",
        f"--force-media-title={title} episode {episode}",
    ]
    if stream.referer and not _needs_proxy(stream.url):
        command.append(f"--referrer={stream.referer}")
    if stream.subtitle_url:
        command.append(f"--sub-file={stream.subtitle_url}")
    command.append(url)
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
    poll_delay = 3.0 if _needs_proxy(stream.url) else 0.5
    time.sleep(poll_delay)
    if player.poll() is not None:
        return None
    return player


def _search_all(name: str) -> list[SearchResult]:
    results: list[SearchResult] = []
    for source_name, source in _WATCH_SOURCES:
        try:
            results.extend(source.search(name))
        except Exception as exc:
            print(f"search failed for {source_name}: {exc}")
    return results


def _episodes(chosen: SearchResult, mode: str) -> list[Chapter]:
    return _SOURCE_BY_NAME[chosen.source].episodes(chosen.id, mode)


def _streams(chosen: SearchResult, episode: Chapter, mode: str):
    return _SOURCE_BY_NAME[chosen.source].streams(chosen.id, episode.id, mode)


def _episode_choices(episodes: list[Chapter], chosen: SearchResult) -> tuple[list[str], list[int]]:
    last_id = get_last(chosen.source, chosen.id)
    labels: list[str] = []
    indexes: list[int] = []
    if last_id:
        last_index = next((idx for idx, ep in enumerate(episodes) if ep.id == last_id), None)
        if last_index is not None:
            labels.append(f"last viewed  {episodes[last_index].title}")
            indexes.append(last_index)
    labels.extend(ep.title for ep in episodes)
    indexes.extend(range(len(episodes)))
    return labels, indexes


def _pick_episode(episodes: list[Chapter], chosen: SearchResult) -> int | None:
    ep_labels, indexes = _episode_choices(episodes, chosen)
    picked = pick(ep_labels, "select episode")
    if picked is None:
        return None
    return indexes[picked]


def _play_episode(
    chosen: SearchResult,
    episode: Chapter,
    mode: str,
) -> subprocess.Popen | None:
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
        sys.exit("no results found.")

    labels = [f"[{r.source}]  {r.title}  [{', '.join(r.tags[:3])}]" for r in results]
    idx = pick(labels, "select anime")
    if idx is None:
        sys.exit("cancelled.")
    chosen = results[idx]

    print(f"\n{chosen.title}")
    mode = "sub"
    print(f"fetching {mode} episodes...")
    try:
        episodes: list[Chapter] = _episodes(chosen, mode)
    except PermissionError as exc:
        sys.exit(str(exc))
    except Exception as exc:
        sys.exit(f"could not fetch episodes: {exc}")

    if not episodes:
        sys.exit("no subbed episodes found.")

    ep_idx = _pick_episode(episodes, chosen)
    if ep_idx is None:
        sys.exit("cancelled.")

    player: subprocess.Popen | None = None
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
