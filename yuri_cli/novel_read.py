import sys
from typing import List

from yuri_cli.lock import filter_kind
from yuri_cli.models import Chapter, SearchResult
from yuri_cli.reader import pick
from yuri_cli.novel_reader import read_novel
from yuri_cli.sources import royalroad


def run(name: str) -> None:
    print(f"searching royalroad for '{name}'...")
    try:
        results: List[SearchResult] = royalroad.search(name)
    except Exception as exc:
        sys.exit(f"search failed: {exc}")
    results = filter_kind(results, "novel")

    if not results:
        sys.exit("no results found.")

    labels = [f"{r.title}  [{', '.join(r.tags[:3])}]" for r in results]
    idx    = pick(labels, "select novel")
    if idx is None:
        sys.exit("cancelled.")
    chosen = results[idx]

    print(f"\n{chosen.title}")
    print("fetching chapters...")
    try:
        chs: List[Chapter] = royalroad.chapters(chosen.id)
    except Exception as exc:
        sys.exit(f"could not fetch chapters: {exc}")

    if not chs:
        sys.exit("no chapters found.")

    ch_labels = [f"ch.{int(ch.number)}  {ch.title}" for ch in chs]
    ch_idx    = pick(ch_labels, "select chapter")
    if ch_idx is None:
        sys.exit("cancelled.")
    chapter = chs[ch_idx]

    print(f"\n{chapter.title}")
    print("fetching text...")
    try:
        segments = royalroad.chapter_content(chapter.id)
    except Exception as exc:
        sys.exit(f"could not fetch chapter: {exc}")

    if not segments:
        sys.exit("chapter is empty.")

    read_novel(segments, chosen, chapter)
