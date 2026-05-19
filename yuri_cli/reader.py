from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

from yuri_cli.models import Chapter, SearchResult

PRELOAD_AHEAD = 5
_DL_WORKERS   = 4

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def _find_viewer() -> str:
    for cmd in ("kitty", "chafa", "tiv"):
        if shutil.which(cmd):
            return cmd
    return "chafa"


def _display_image(viewer: str, path: str) -> None:
    cols, rows = shutil.get_terminal_size((80, 24))
    if viewer == "kitty":
        os.system(
            f"kitty +kitten icat --clear --scale-up "
            f"--place={cols}x{rows - 4}@0x0 {path!r}"
        )
    elif viewer == "chafa":
        os.system(f"chafa --size={cols}x{rows - 4} --animate=off {path!r}")
    elif viewer == "tiv":
        os.system(f"tiv -w {cols} -h {rows - 4} {path!r}")
    else:
        print(f"no viewer found — install chafa. page at: {path}")


def _referer_for(url: str) -> str:
    if "dynasty-scans.com" in url:
        return "https://dynasty-scans.com/"
    return "https://mangadex.org/"


def _download_page(url: str, dest: Path) -> None:
    headers = {"User-Agent": _UA, "Referer": _referer_for(url)}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as f:
        f.write(resp.read())


class PageBuffer:
    def __init__(self, urls: List[str], tmpdir: Path,
                 ahead: int = PRELOAD_AHEAD, workers: int = _DL_WORKERS) -> None:
        self._urls    = urls
        self._tmpdir  = tmpdir
        self._ahead   = ahead
        self._pool    = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="preload")
        self._futures: Dict[int, Future] = {}
        self._errors:  Dict[int, Exception] = {}
        self._lock     = threading.Lock()
        self._schedule_window(0)

    def get(self, index: int) -> Optional[Path]:
        self._schedule_window(index)
        with self._lock:
            fut = self._futures.get(index)
        if fut is None:
            return None
        fut.result()
        if index in self._errors:
            return None
        return self._page_path(index)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def preloaded_count(self, current: int) -> int:
        ready = 0
        for i in range(current + 1, min(current + 1 + self._ahead, len(self._urls))):
            with self._lock:
                fut = self._futures.get(i)
            if fut is not None and fut.done() and i not in self._errors:
                ready += 1
        return ready

    def _page_path(self, index: int) -> Path:
        url = self._urls[index]
        ext = Path(url.split("?")[0]).suffix or ".jpg"
        return self._tmpdir / f"page_{index:04d}{ext}"

    def _schedule_window(self, from_index: int) -> None:
        end = min(from_index + self._ahead + 1, len(self._urls))
        with self._lock:
            for i in range(from_index, end):
                if i not in self._futures:
                    self._futures[i] = self._pool.submit(self._do_download, i)

    def _do_download(self, index: int) -> None:
        dest = self._page_path(index)
        if dest.exists():
            return
        try:
            _download_page(self._urls[index], dest)
        except Exception as exc:
            with self._lock:
                self._errors[index] = exc


def _pick_fzf(items: List[str], prompt: str) -> tuple[bool, Optional[int]]:
    import subprocess
    input_text = "\n".join(f"{i}\t{label}" for i, label in enumerate(items))
    try:
        result = subprocess.run(
            ["fzf", "--with-nth=2..", "--delimiter=\t", f"--prompt={prompt}> "],
            input=input_text, capture_output=True, text=True,
        )
        if result.returncode != 0:
            return True, None
        return True, int(result.stdout.strip().split("\t")[0])
    except FileNotFoundError:
        return False, None


def pick(items: List[str], prompt: str) -> Optional[int]:
    used_fzf, idx = _pick_fzf(items, prompt)
    if idx is not None:
        return idx
    if used_fzf:
        return None
    print(f"\n{prompt}:")
    for i, label in enumerate(items):
        print(f"  [{i + 1}] {label}")
    try:
        raw = input("select (0 to cancel): ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    try:
        n = int(raw)
        return None if n == 0 else n - 1
    except ValueError:
        return None


def _clear() -> None:
    os.system("clear")


def _hud(kind: str, title: str, ch_title: str,
         page: int, total: int, preloaded: int, viewer: str) -> None:
    cols, _ = shutil.get_terminal_size((80, 24))
    filled = min(preloaded, PRELOAD_AHEAD)
    bar    = "█" * filled + "░" * (PRELOAD_AHEAD - filled)
    left   = f"  [{kind}] {title} · {ch_title}"
    right  = f"[{bar}]  {page}/{total}  "
    gap    = cols - len(left) - len(right)
    print(left + " " * max(gap, 1) + right)
    print("─" * cols)


def read_pages(page_urls: List[str], result: SearchResult,
               chapter: Chapter, kind: str = "manga") -> None:
    total  = len(page_urls)
    viewer = _find_viewer()

    print(f"{total} pages  •  {viewer}")

    with tempfile.TemporaryDirectory(prefix="yuri_") as _tmpdir:
        tmpdir = Path(_tmpdir)
        buf    = PageBuffer(page_urls, tmpdir)

        try:
            page_num = 1
            while page_num <= total:
                path = buf.get(page_num - 1)
                _clear()
                _hud(kind, result.title, chapter.title,
                     page_num, total, buf.preloaded_count(page_num - 1), viewer)

                if path is None:
                    print(f"  page {page_num} failed to download")
                else:
                    _display_image(viewer, str(path))

                if page_num >= total:
                    break

                try:
                    print("\n  enter  next    q  quit", end="  ", flush=True)
                    key = input().strip().lower()
                except (EOFError, KeyboardInterrupt):
                    break

                if key == "q":
                    break
                else:
                    page_num += 1
        finally:
            buf.shutdown()

    print("done.")
