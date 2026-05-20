from __future__ import annotations

import sys

from yuri_cli.models import Chapter, SearchResult
from yuri_cli.progress import get_last, set_last
from yuri_cli.reader import pick, read_pages
from yuri_cli.sources import dynasty, mangadex


_SOURCE_LABELS = {
    "dynasty": "Dynasty",
    "mangadex": "MangaDex",
}


def _source_label(source: str) -> str:
    return _SOURCE_LABELS.get(source, source)


def _search_all(name: str) -> list[SearchResult]:
    results: list[SearchResult] = []
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


def _chapters(result: SearchResult) -> list[Chapter]:
    if result.source == "dynasty":
        return dynasty.chapters(result.id)
    return mangadex.chapters(result.id)


def _chapter_pages(chapter: Chapter) -> List[str]:
    if chapter.source == "dynasty":
        return dynasty.chapter_pages(chapter.id)
    return mangadex.chapter_pages(chapter.id)


def _unique_volumes(chapters: list[Chapter]) -> list[str]:
    return list(dict.fromkeys(ch.volume for ch in chapters if ch.volume))


def _chapter_choices(chapters: list[Chapter], last_id: str | None) -> list[Chapter]:
    if not last_id:
        return chapters
    last = next((ch for ch in chapters if ch.id == last_id), None)
    if last is None:
        return chapters
    return [last] + chapters


def run(name: str) -> None:
    print(f"searching for '{name}'...")
    try:
        results: list[SearchResult] = _search_all(name)
    except Exception as exc:
        sys.exit(f"search failed: {exc}")
    results = [r for r in results if r.kind in ("manga", "novel")]

    if not results:
        sys.exit("no results found.")

    labels = [
        f"{r.title} [{_source_label(r.source)}]  [{r.kind}]  [{', '.join(r.tags[:3])}]"
        for r in results
    ]
    idx = pick(labels, "select title")
    if idx is None:
        sys.exit("cancelled.")
    chosen = results[idx]

    print(f"\n{chosen.title} [{_source_label(chosen.source)}]")
    print("fetching chapters...")
    try:
        raw_chs: list[Chapter] = _chapters(chosen)
    except PermissionError as exc:
        sys.exit(str(exc))
    except Exception as exc:
        sys.exit(f"could not fetch chapters: {exc}")

    if not raw_chs:
        sys.exit("no english chapters found.")

    if chosen.kind == "novel":
        volumes = _unique_volumes(raw_chs)
        if len(volumes) > 1:
            vol_idx = pick(volumes, "select volume")
            if vol_idx is None:
                sys.exit("cancelled.")
            raw_chs = [ch for ch in raw_chs if ch.volume == volumes[vol_idx]]

    last_id = get_last(chosen.source, chosen.id)
    chs = _chapter_choices(raw_chs, last_id)

    ch_labels = [
        f"{'last viewed  ' if idx == 0 and ch.id == last_id else ''}"
        f"ch.{ch.number:g}  {ch.title}"
        for idx, ch in enumerate(chs)
    ]
    ch_idx = pick(ch_labels, "select chapter")
    if ch_idx is None:
        sys.exit("cancelled.")
    chapter = chs[ch_idx]

    set_last(chosen.source, chosen.id, chapter.id)

    print(f"\n{chapter.title}")
    print("fetching pages...")
    try:
        page_urls = _chapter_pages(chapter)
    except Exception as exc:
        sys.exit(f"could not fetch pages: {exc}")

    if not page_urls:
        sys.exit("no pages found.")

    read_pages(page_urls, chosen, chapter, kind=chosen.kind)
