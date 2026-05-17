import sys
from typing import List

from yuri_cli.lock import filter_kind
from yuri_cli.models import Chapter, SearchResult
from yuri_cli.reader import pick, read_pages
from yuri_cli.sources import dynasty, mangadex


_SOURCE_LABELS = {
    "dynasty": "Dynasty",
    "mangadex": "MangaDex",
}


def _source_label(source: str) -> str:
    return _SOURCE_LABELS.get(source, source)


def _search_all(name: str) -> List[SearchResult]:
    results: List[SearchResult] = []
    errors: List[str] = []
    for source_name, search_fn in (
        ("mangadex", mangadex.search),
        ("dynasty", dynasty.search),
    ):
        try:
            results.extend(search_fn(name))
        except Exception as exc:
            errors.append(f"{_source_label(source_name)}: {exc}")
    if not results and errors:
        raise RuntimeError("; ".join(errors))
    return results


def _chapters(result: SearchResult) -> List[Chapter]:
    if result.source == "dynasty":
        return dynasty.chapters(result.id)
    return mangadex.chapters(result.id)


def _chapter_pages(chapter: Chapter) -> List[str]:
    if chapter.source == "dynasty":
        return dynasty.chapter_pages(chapter.id)
    return mangadex.chapter_pages(chapter.id)


def run(name: str) -> None:
    print(f"searching manga sources for '{name}'...")
    try:
        results: List[SearchResult] = _search_all(name)
    except Exception as exc:
        sys.exit(f"search failed: {exc}")
    results = filter_kind(results, "manga")

    if not results:
        sys.exit("no manga results found.")

    labels = [
        f"{r.title} [{_source_label(r.source)}]  [{', '.join(r.tags[:3])}]"
        for r in results
    ]
    idx = pick(labels, "select manga")
    if idx is None:
        sys.exit("cancelled.")
    chosen = results[idx]

    print(f"\n{chosen.title} [{_source_label(chosen.source)}]")
    print("fetching chapters...")
    try:
        chs: List[Chapter] = _chapters(chosen)
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
        page_urls = _chapter_pages(chapter)
    except Exception as exc:
        sys.exit(f"could not fetch pages: {exc}")

    if not page_urls:
        sys.exit("no pages found.")

    read_pages(page_urls, chosen, chapter, kind="manga")
