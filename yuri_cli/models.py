from dataclasses import dataclass, field


@dataclass
class SearchResult:
    source: str
    id: str
    title: str
    kind: str
    tags: list[str] = field(default_factory=list)
    description: str = ""
    cover_url: str = ""


@dataclass
class Chapter:
    id: str
    title: str
    number: float
    source: str
    volume: str = ""


@dataclass
class Page:
    url: str
    index: int
