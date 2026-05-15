import sys
from typing import List

from yuri_cli.models import Chapter, SearchResult
from yuri_cli.reader import pick, read_pages
from yuri_cli.novel_reader import read_novel
from yuri_cli.sources import baka_tsuki, dynasty


def run(name: str) -> None:
    print(f"searching baka-tsuki for '{name}'...")
    bt_results: List[SearchResult] = []
    try:
        bt_results = baka_tsuki.search(name)
    except Exception as exc:
        print(f"baka-tsuki unavailable: {exc}")

    if bt_results:
        labels = [r.title for r in bt_results]
        idx    = pick(labels, "select novel")
        if idx is not None:
            chosen = bt_results[idx]
            print(f"\n{chosen.title}  [baka-tsuki]")
            print("fetching chapters...")
            try:
                chs = baka_tsuki.chapters(chosen.id)
            except Exception as exc:
                sys.exit(f"could not fetch chapters: {exc}")

            if not chs:
                print("not found on baka-tsuki, trying dynasty scans...")
                bt_results = []
            else:
                ch_labels = [f"ch.{int(ch.number)}  {ch.title}" for ch in chs]
                ch_idx    = pick(ch_labels, "select chapter")
                if ch_idx is None:
                    sys.exit("cancelled.")
                chapter = chs[ch_idx]
                print(f"\n{chapter.title}")
                print("fetching text...")
                try:
                    segments = baka_tsuki.chapter_content(chapter.id)
                except Exception as exc:
                    sys.exit(f"could not fetch chapter: {exc}")
                if not segments:
                    sys.exit("chapter is empty.")
                read_novel(segments, chosen, chapter)
                return

    print(f"searching dynasty scans for '{name}'...")
    try:
        results: List[SearchResult] = dynasty.search(name)
    except Exception as exc:
        sys.exit(f"search failed: {exc}")

    if not results:
        sys.exit("no results found.")

    labels = [r.title for r in results]
    idx    = pick(labels, "select novel")
    if idx is None:
        sys.exit("cancelled.")
    chosen = results[idx]
    print(f"\n{chosen.title}  [dynasty scans]")
    print("fetching chapters...")
    try:
        chs = dynasty.chapters(chosen.id)
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
        sys.exit(f"could not fetch pages: {exc}")

    if not page_urls:
        sys.exit("no pages found.")

    read_pages(page_urls, chosen, chapter, kind="novel")
