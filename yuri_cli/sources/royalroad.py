import re
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from typing import List, Tuple

from yuri_cli.models import SearchResult, Chapter

_BASE    = "https://www.royalroad.com"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
}


def _fetch(path: str) -> str:
    url = path if path.startswith("http") else _BASE + path
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _unescape(text: str) -> str:
    return (
        text.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&nbsp;", " ")
    )


class _SearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: List[SearchResult] = []
        self._in_row     = False
        self._in_title   = False
        self._in_tags    = False
        self._in_desc    = False
        self._cur_id     = ""
        self._cur_title  = ""
        self._cur_tags:  List[str] = []
        self._cur_desc   = ""
        self._depth      = 0
        self._tag_depth  = 0
        self._desc_depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "")

        if tag == "div" and "fiction-list-item" in cls:
            self._in_row    = True
            self._cur_tags  = []
            self._cur_desc  = ""
            self._cur_id    = ""
            self._cur_title = ""
            return

        if not self._in_row:
            return

        if tag == "a" and "a-title" in cls:
            href = a.get("href", "")
            m = re.search(r"/fiction/(\d+)", href)
            if m:
                self._cur_id = m.group(1)
            self._in_title = True
            return

        if tag == "span" and "tags" in cls:
            self._in_tags  = True
            self._tag_depth = self._depth
            return

        if self._in_tags and tag == "a":
            self._collecting_tag = True
            self._tag_buf = ""
            return

        if tag == "div" and "fiction-description" in cls:
            self._in_desc  = True
            self._desc_depth = self._depth
            return

        self._depth += 1

    def handle_endtag(self, tag):
        self._depth -= 1

        if self._in_title and tag == "a":
            self._in_title = False
            return

        if self._in_tags and tag == "a":
            if hasattr(self, "_tag_buf"):
                t = _unescape(self._tag_buf).strip()
                if t:
                    self._cur_tags.append(t)
            self._collecting_tag = False
            return

        if self._in_tags and tag == "span" and self._depth <= self._tag_depth:
            self._in_tags = False
            return

        if self._in_desc and tag == "div" and self._depth <= self._desc_depth:
            self._in_desc = False
            return

        if self._in_row and tag == "div" and not self._in_title and not self._in_tags:
            if self._cur_id and self._cur_title:
                self.results.append(SearchResult(
                    source="royalroad",
                    id=self._cur_id,
                    title=_unescape(self._cur_title).strip(),
                    kind="novel",
                    tags=list(self._cur_tags),
                    description=_unescape(self._cur_desc).strip(),
                ))
                self._in_row    = False
                self._cur_id    = ""
                self._cur_title = ""

    def handle_data(self, data):
        if self._in_title:
            self._cur_title += data
            return
        if self._in_tags and hasattr(self, "_collecting_tag") and self._collecting_tag:
            self._tag_buf += data
            return
        if self._in_desc:
            self._cur_desc += data


class _ChapterListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.chapters: List[Chapter] = []
        self._in_row   = False
        self._in_title = False
        self._cur_href = ""
        self._cur_name = ""
        self._index    = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr" and "chapter-row" in a.get("class", ""):
            self._in_row   = True
            self._cur_href = ""
            self._cur_name = ""
            return
        if not self._in_row:
            return
        if tag == "a" and a.get("href", "").startswith("/fiction/"):
            self._cur_href = a["href"]
            self._in_title = True

    def handle_endtag(self, tag):
        if self._in_title and tag == "a":
            self._in_title = False
        if self._in_row and tag == "tr":
            if self._cur_href and self._cur_name.strip():
                self._index += 1
                cid = self._cur_href.split("/")[4] if len(self._cur_href.split("/")) >= 5 else self._cur_href
                self.chapters.append(Chapter(
                    id=self._cur_href,
                    title=_unescape(self._cur_name).strip(),
                    number=float(self._index),
                    source="royalroad",
                ))
            self._in_row = False

    def handle_data(self, data):
        if self._in_title:
            self._cur_name += data


class _ChapterContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_content = False
        self._depth      = 0
        self._start_depth = 0
        self._buf        = ""
        self.paragraphs: List[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div" and "chapter-content" in a.get("class", ""):
            self._in_content  = True
            self._start_depth = self._depth
        if self._in_content:
            if tag in ("p", "br"):
                if self._buf.strip():
                    self.paragraphs.append(_unescape(self._buf).strip())
                    self._buf = ""
        self._depth += 1

    def handle_endtag(self, tag):
        self._depth -= 1
        if self._in_content:
            if tag in ("p",):
                if self._buf.strip():
                    self.paragraphs.append(_unescape(self._buf).strip())
                    self._buf = ""
            if tag == "div" and self._depth <= self._start_depth:
                if self._buf.strip():
                    self.paragraphs.append(_unescape(self._buf).strip())
                self._in_content = False

    def handle_data(self, data):
        if self._in_content:
            self._buf += data


def search(query: str) -> List[SearchResult]:
    q   = urllib.parse.quote_plus(query)
    url = f"{_BASE}/fictions/search?title={q}&tagsAdd=Female+Lead&tagsAdd=Yuri"
    html = _fetch(url)

    parser = _SearchParser()
    parser.feed(html)
    results = parser.results

    if not results:
        url2 = f"{_BASE}/fictions/search?title={q}"
        parser2 = _SearchParser()
        parser2.feed(_fetch(url2))
        results = parser2.results

    return results


def chapters(fiction_id: str) -> List[Chapter]:
    html   = _fetch(f"/fiction/{fiction_id}")
    parser = _ChapterListParser()
    parser.feed(html)
    return parser.chapters


def chapter_content(chapter_path: str) -> List[Tuple[str, str]]:
    html   = _fetch(chapter_path)
    parser = _ChapterContentParser()
    parser.feed(html)
    segments: List[Tuple[str, str]] = []
    for para in parser.paragraphs:
        if para:
            segments.append(("text", para))
    return segments
