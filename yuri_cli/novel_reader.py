from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from pathlib import Path

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


def _wrap(text: str, width: int, indent: int = 4) -> list[str]:
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
    def __init__(self, lines: list[str], title: str, ch_title: str) -> None:
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


def read_novel(segments: list[tuple[str, str]],
               result: SearchResult, chapter: Chapter) -> None:
    cols, _  = shutil.get_terminal_size((80, 24))
    viewer   = _find_viewer()
    text_buf: list[str] = []

    with tempfile.TemporaryDirectory(prefix="yuri_novel_") as tmpdir:
        img_index = 0

        def flush_text() -> None:
            if not text_buf:
                return
            lines = _wrap("\n\n".join(text_buf), cols)
            _Pager(lines, result.title, chapter.title).run()
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


class _HtmlStripper(HTMLParser):
    _BLOCK = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "br", "div", "li", "tr", "td"}
    _SKIP  = {"script", "style", "head"}

    def __init__(self) -> None:
        super().__init__()
        self._buf  = ""
        self._skip = 0

    def _flush(self, out: list[str]) -> None:
        text = re.sub(r"\n{3,}", "\n\n", self._buf).strip()
        if text:
            out.append(text)
        self._buf = ""

    def strip(self, html_text: str) -> str:
        out: list[str] = []
        self._buf  = ""
        self._skip = 0
        self.feed(html_text)
        out_inner: list[str] = []
        self._flush(out_inner)
        return "\n\n".join(out_inner)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in self._BLOCK:
            self._buf += "\n"

    def handle_endtag(self, tag: str) -> None:
        if self._skip:
            if tag in self._SKIP:
                self._skip -= 1
            return
        if tag in self._BLOCK:
            self._buf += "\n"

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._buf += data


def _epub_item_path(opf_dir: str, href: str) -> str:
    if opf_dir in (".", ""):
        return href
    return f"{opf_dir}/{href}"


def _epub_segments(path: Path) -> list[tuple[str, str]]:
    try:
        with zipfile.ZipFile(path) as zf:
            container = ET.fromstring(zf.read("META-INF/container.xml"))
            ns_c      = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
            opf_path  = container.find(".//c:rootfile", ns_c).get("full-path")
            opf_dir   = str(Path(opf_path).parent)
            opf       = ET.fromstring(zf.read(opf_path))
            ns_o      = {"opf": "http://www.idpf.org/2007/opf"}

            manifest = {
                item.get("id"): item.get("href", "")
                for item in opf.findall(".//opf:manifest/opf:item", ns_o)
            }
            spine = [
                item.get("idref")
                for item in opf.findall(".//opf:spine/opf:itemref", ns_o)
            ]

            stripper  = _HtmlStripper()
            segments: list[tuple[str, str]] = []

            for idref in spine:
                href = manifest.get(idref or "", "")
                if not href:
                    continue
                full = _epub_item_path(opf_dir, href)
                try:
                    raw = zf.read(full).decode("utf-8", errors="replace")
                except KeyError:
                    try:
                        raw = zf.read(href).decode("utf-8", errors="replace")
                    except KeyError:
                        continue
                text = stripper.strip(raw)
                if text:
                    segments.append(("text", text))

            return segments
    except Exception as exc:
        return [("text", f"could not read epub: {exc}")]


def _pdf_segments(path: Path) -> list[tuple[str, str]]:
    if shutil.which("pdftotext"):
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and result.stdout.strip():
                return [("text", result.stdout.strip())]
        except Exception:
            pass
    return [("_pdf_images", str(path))]


def _read_pdf_as_images(path: Path, result: SearchResult, chapter: Chapter) -> None:
    if not shutil.which("pdftoppm"):
        print("install poppler to read pdfs in the terminal.")
        return
    viewer = _find_viewer()
    with tempfile.TemporaryDirectory(prefix="yuri_pdf_") as tmpdir:
        subprocess.run(
            ["pdftoppm", "-r", "150", str(path), f"{tmpdir}/page"],
            capture_output=True,
        )
        pages = sorted(Path(tmpdir).glob("page-*.ppm"))
        if not pages:
            pages = sorted(Path(tmpdir).glob("page*.ppm"))
        total    = len(pages)
        page_num = 1
        while page_num <= total:
            _clear()
            _hud(result.title, chapter.title, page_num, total)
            _display_image(viewer, str(pages[page_num - 1]))
            if page_num >= total:
                break
            try:
                print("\n  enter  next    q  quit", end="  ", flush=True)
                key = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                break
            if key == "q":
                break
            page_num += 1


def read_file(path: Path, result: SearchResult, chapter: Chapter) -> None:
    suffix = path.suffix.lower()
    if suffix == ".epub":
        segments = _epub_segments(path)
    elif suffix == ".pdf":
        segments = _pdf_segments(path)
        if segments and segments[0][0] == "_pdf_images":
            _read_pdf_as_images(path, result, chapter)
            return
    else:
        print(f"unsupported format: {suffix}")
        return
    if not segments:
        print("file appears to be empty.")
        return
    read_novel(segments, result, chapter)
