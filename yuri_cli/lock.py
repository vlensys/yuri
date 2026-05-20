from yuri_cli.models import SearchResult

YURI_TERMS = {
    "yuri", "girls' love", "girls love", "shoujo-ai", "shoujoai",
    "gl", "lesbian", "yuri manga", "yuri anime", "josei romance", "百合",
}


def looks_yuri(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in YURI_TERMS)


def filter_yuri(results: list[SearchResult]) -> list[SearchResult]:
    return [
        r for r in results
        if looks_yuri(r.title) or any(looks_yuri(tag) for tag in r.tags)
    ]


def filter_kind(results: list[SearchResult], kind: str) -> list[SearchResult]:
    return [r for r in results if r.kind == kind]
