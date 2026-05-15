from typing import List
from yuri_cli.models import SearchResult

YURI_TERMS = {
    "yuri", "girls' love", "girls love", "shoujo-ai", "shoujoai",
    "gl", "lesbian", "yuri manga", "yuri anime", "josei romance", "百合",
}


def looks_yuri(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in YURI_TERMS)


def filter_yuri(results: List[SearchResult]) -> List[SearchResult]:
    return [r for r in results if any(looks_yuri(tag) for tag in r.tags)]
