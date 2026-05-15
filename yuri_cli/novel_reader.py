from __future__ import annotations

import os
import shutil
import sys
import tempfile
import textwrap
import urllib.request
from pathlib import Path
from typing import List, Tuple

from yuri_cli.models import SearchResult, Chapter

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Referer":    "https://www.baka-tsuki.org/",
}


def _find_viewer() -> str:
    for cmd in ("kitty", "chafa", "tiv"):
        if shutil.which(cmd):
            return cmd
    return "chafa"


def _display_image(viewer: str, path: str) -> None:
    cols, rows = shutil.get_terminal_size((80, 24))
    if viewer == "kitty":
        os.system(f"kitty +kitten icat --clear --scale-up --place={cols}x{rows - 4}@0x0 {path!r}")
    elif viewer == "chafa":
        os.system(f"chafa --size={cols}x{rows - 4} --animate=off {path!r}")
    elif viewer == "tiv":
        os.system(f"tiv -w {cols} -h {rows - 4} {path!r}")


def _fetch_image(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp, open(dest, "wb") as f:
            f.write(resp.read())
        return True
    except Exception as e:
        print(f"  illustration failed: {e}")
        return False


def _clear() -> None:
    os.system("clear")


def _wrap(text: str, width: int, indent: int = 4) -> List[str]:
    lines = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            lines.append("")
            continue
        wrapped = textwrap.fill(
            para, width=width - indent,
            initial_indent=" " * indent,
            subsequent_indent=" " * indent,
        )
        lines.extend(wrapped.split("\n"))
        lines.append("")
    return lines


def _hud(title: str, ch_title: str, line: int, total_lines: int) -> None:
    cols, _ = shutil.get_terminal_size((80, 24))
    pct   = int(100 * line / total_lines) if total_lines else 0
    left  = f"  [novel] {title} · {ch_title}"
    right = f"{pct}%  "
    gap   = cols - len(left) - len(right)
    print(left + " " * max(gap, 1) + right)
    print("─" * cols)


class _Pager:
    def __init__(self, lines: List[str], title: str, ch_title: str) -> None:
        self._lines    = lines
        self._title    = title
        self._ch_title = ch_title

    def run(self) -> None:
        pos   = 0
        total = len(self._lines)

        while pos < total:
            cols, rows = shutil.get_terminal_size((80, 40))
            page_size  = rows - 4
            _clear()
            _hud(self._title, self._ch_title, pos, total)
            print("\n".join(self._lines[pos: pos + page_size]))

            if pos + page_size >= total:
                print("\n  end of chapter")
                input("  enter to continue  ")
                return

            try:
                print("\n  enter  next    b  back    q  quit", end="  ", flush=True)
                key = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                return

            if key == "q":
                sys.exit(0)
            elif key == "b":
                pos = max(0, pos - page_size)
            else:
                pos += page_size


def read_novel(segments: List[Tuple[str, str]],
               result: SearchResult, chapter: Chapter) -> None:
    cols, _  = shutil.get_terminal_size((80, 24))
    viewer   = _find_viewer()
    text_buf: List[str] = []

    with tempfile.TemporaryDirectory(prefix="yuri_novel_") as tmpdir:
        img_index = 0

        def flush_text() -> None:
            if not text_buf:
                return
            lines  = _wrap("\n\n".join(text_buf), cols)
            pager  = _Pager(lines, result.title, chapter.title)
            pager.run()
            text_buf.clear()

        for kind, value in segments:
            if kind == "text":
                text_buf.append(value)
            elif kind == "image":
                flush_text()
                dest = Path(tmpdir) / f"illus_{img_index:03d}.jpg"
                img_index += 1
                _clear()
                cols2, _ = shutil.get_terminal_size((80, 24))
                print("  illustration")
                print("─" * cols2)
                if _fetch_image(value, dest):
                    _display_image(viewer, str(dest))
                try:
                    input("\n  enter to continue  ")
                except (EOFError, KeyboardInterrupt):
                    return

        flush_text()
