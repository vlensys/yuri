import sys
from typing import List

from yuri_cli.lock import filter_kind
from yuri_cli.models import Chapter, SearchResult
from yuri_cli.reader import pick, read_pages
from yuri_cli.sources import mangadex


def run(name: str) -> None:
    print(f"searching mangadex for '{name}'...")
    try:
        results: List[SearchResult] = mangadex.search(name)
    except Exception as exc:
        sys.exit(f"search failed: {exc}")
    results = filter_kind(results, "manga")

    if not results:
        sys.exit("no manga results found.")

    labels = [f"{r.title}  [{', '.join(r.tags[:3])}]" for r in results]
    idx = pick(labels, "select manga")
    if idx is None:
        sys.exit("cancelled.")
    chosen = results[idx]

    print(f"\n{chosen.title}")
    print("fetching chapters...")
    try:
        chs: List[Chapter] = mangadex.chapters(chosen.id)
    except PermissionError as exc:
        sys.exit(str(exc))
    except Exception as exc:
        sys.exit(f"could not fetch chapters: {exc}")

    if not chs:
        sys.exit("no english chapters found.")

    ch_labels = [f"ch.{ch.number:g}  {ch.title}" for ch in chs]
    ch_idx = pick(ch_labels, "select chapter")
    if ch_idx is None:
        sys.exit("cancelled.")
    chapter = chs[ch_idx]

    print(f"\n{chapter.title}")
    print("fetching pages...")
    try:
        page_urls = mangadex.chapter_pages(chapter.id)
    except Exception as exc:
        sys.exit(f"could not fetch pages: {exc}")

    if not page_urls:
        sys.exit("no pages found.")

    read_pages(page_urls, chosen, chapter, kind="manga")
