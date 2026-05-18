import sys
from typing import List

from yuri_cli.lock import filter_kind
from yuri_cli.models import Chapter, SearchResult
from yuri_cli.reader import pick, read_pages
from yuri_cli.sources import dynasty


def run(name: str) -> None:
    print(f"searching for '{name}'...")
    try:
        results: List[SearchResult] = dynasty.search(name)
    except Exception as exc:
        sys.exit(f"search failed: {exc}")
    results = filter_kind(results, "novel")

    if not results:
        sys.exit("no results found.")

    labels = [f"{r.title} [Dynasty]  [{', '.join(r.tags[:3])}]" for r in results]
    idx    = pick(labels, "select novel")
    if idx is None:
        sys.exit("cancelled.")
    chosen = results[idx]

    print(f"\n{chosen.title} [Dynasty]")
    print("fetching chapters...")
    try:
        chs: List[Chapter] = dynasty.chapters(chosen.id)
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
    print("fetching pages...")
    try:
        page_urls = dynasty.chapter_pages(chapter.id)
    except Exception as exc:
        sys.exit(f"could not fetch chapter: {exc}")

    if not page_urls:
        sys.exit("no pages found.")

    read_pages(page_urls, chosen, chapter, kind="novel")
