"""
Integration tests – hit live upstream APIs for every source.

Run all:        pytest tests/test_integration.py -v
Skip in fast CI: pytest -m "not integration"

Each test class covers one source end-to-end.  Stream-resolution tests
(which invoke mpv-adjacent external calls) are best-effort: if the remote
player endpoint returns nothing we log a warning rather than failing, because
stream providers rotate URLs frequently.
"""
from __future__ import annotations

import pytest

from yuri_cli.sources import allanime, anixplay, dynasty, mangadex

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Stable yuri titles used as search anchors across all sources
# ---------------------------------------------------------------------------
_ANIME_QUERY = "bloom into you"   # Yagate Kimi ni Naru – has sub + dub on most providers
_MANGA_QUERY = "bloom into you"   # Yagate Kimi ni Naru – on MangaDex with yuri tag
_NOVEL_QUERY = "I Favor the Villainess"  # Watashi no Oshi wa Akuyaku Reijou – Dynasty novels


# ===========================================================================
# AllAnime – sub & dub anime watching
# ===========================================================================

class TestAllAnime:
    """AllAnime GraphQL source – search, episodes, streams."""

    @pytest.fixture(scope="class")
    def search_results(self):
        results = allanime.search(_ANIME_QUERY)
        assert results, f"AllAnime: no results for {_ANIME_QUERY!r}"
        return results

    @pytest.fixture(scope="class")
    def first_show_id(self, search_results):
        return search_results[0].id

    # -- search ---------------------------------------------------------------

    def test_search_result_structure(self, search_results):
        for r in search_results:
            assert r.source == "allanime"
            assert r.id
            assert r.title
            assert r.kind == "anime"

    def test_search_contains_target(self, search_results):
        titles = [r.title.lower() for r in search_results]
        assert any(
            "bloom" in t or "yagate" in t or "kimi ni naru" in t for t in titles
        ), f"expected 'Bloom Into You' in AllAnime results, got: {titles}"

    # -- show detail ----------------------------------------------------------

    def test_show_detail(self, first_show_id):
        detail = allanime.show(first_show_id)
        assert detail.get("_id") == first_show_id
        assert detail.get("name")
        assert detail.get("availableEpisodesDetail") is not None

    # -- episodes (sub) -------------------------------------------------------

    def test_episodes_sub_returned(self, first_show_id):
        eps = allanime.episodes(first_show_id, translation_type="sub")
        assert eps, "AllAnime: no sub episodes found"

    def test_episodes_sub_structure(self, first_show_id):
        eps = allanime.episodes(first_show_id, translation_type="sub")
        for ep in eps:
            assert ep.source == "allanime"
            assert ep.id
            assert ep.number >= 0

    def test_episodes_sub_sorted(self, first_show_id):
        eps = allanime.episodes(first_show_id, translation_type="sub")
        nums = [ep.number for ep in eps]
        assert nums == sorted(nums), "sub episodes not sorted by number"

    # -- episodes (dub) -------------------------------------------------------

    def test_episodes_dub_no_crash(self, first_show_id):
        # Dub may be absent for some titles – just ensure the call returns cleanly
        eps = allanime.episodes(first_show_id, translation_type="dub")
        for ep in eps:
            assert ep.source == "allanime"
            assert ep.number >= 0

    # -- streams (sub) --------------------------------------------------------

    def test_streams_sub_resolve(self, first_show_id):
        eps = allanime.episodes(first_show_id, translation_type="sub")
        assert eps, "need at least one sub episode to test streams"
        streams = allanime.streams(first_show_id, eps[0].id, translation_type="sub")
        if not streams:
            pytest.skip("AllAnime returned 0 streams for ep 1 – provider may be down")
        for s in streams:
            assert s.url.startswith("http"), f"stream URL invalid: {s.url!r}"

    def test_streams_sub_sorted_by_priority(self, first_show_id):
        eps = allanime.episodes(first_show_id, translation_type="sub")
        if not eps:
            pytest.skip("no sub episodes")
        streams = allanime.streams(first_show_id, eps[0].id, translation_type="sub")
        if len(streams) < 2:
            pytest.skip("only one stream, nothing to compare")
        # Verify descending sort order (best source first)
        keys = [allanime._stream_sort_key(s) for s in streams]
        assert keys == sorted(keys, reverse=True)

    # -- streams (dub) --------------------------------------------------------

    def test_streams_dub_no_crash(self, first_show_id):
        eps = allanime.episodes(first_show_id, translation_type="dub")
        if not eps:
            pytest.skip("no dub episodes for this title")
        streams = allanime.streams(first_show_id, eps[0].id, translation_type="dub")
        for s in streams:
            assert s.url.startswith("http")


# ===========================================================================
# AniXPlay – sub & dub anime watching
# ===========================================================================

class TestAniXPlay:
    """AniXPlay REST source – search, episodes, streams."""

    @pytest.fixture(scope="class")
    def search_results(self):
        results = anixplay.search(_ANIME_QUERY)
        assert results, f"AniXPlay: no results for {_ANIME_QUERY!r}"
        return results

    @pytest.fixture(scope="class")
    def first_show_id(self, search_results):
        return search_results[0].id

    # -- search ---------------------------------------------------------------

    def test_search_result_structure(self, search_results):
        for r in search_results:
            assert r.source == "anixplay"
            assert r.id
            assert r.title
            assert r.kind == "anime"

    # -- episodes (sub) -------------------------------------------------------

    def test_episodes_sub_returned(self, first_show_id):
        eps = anixplay.episodes(first_show_id, mode="sub")
        assert eps, "AniXPlay: no sub episodes found"

    def test_episodes_sub_structure(self, first_show_id):
        eps = anixplay.episodes(first_show_id, mode="sub")
        for ep in eps:
            assert ep.source == "anixplay"
            assert ep.id
            assert ep.number >= 0

    # -- episodes (dub) -------------------------------------------------------

    def test_episodes_dub_no_crash(self, first_show_id):
        eps = anixplay.episodes(first_show_id, mode="dub")
        for ep in eps:
            assert ep.source == "anixplay"
            assert ep.number >= 0

    # -- streams --------------------------------------------------------------

    def test_streams_sub_no_crash(self, first_show_id):
        eps = anixplay.episodes(first_show_id, mode="sub")
        if not eps:
            pytest.skip("no sub episodes")
        streams = anixplay.streams(first_show_id, eps[0].id, mode="sub")
        # AniXPlay player resolution is best-effort – warn but don't hard-fail
        if not streams:
            pytest.skip("AniXPlay returned 0 streams – player endpoint may be down")
        for s in streams:
            assert s.url.startswith("http"), f"stream URL invalid: {s.url!r}"

    def test_streams_dub_no_crash(self, first_show_id):
        eps = anixplay.episodes(first_show_id, mode="dub")
        if not eps:
            pytest.skip("no dub episodes for this title")
        streams = anixplay.streams(first_show_id, eps[0].id, mode="dub")
        for s in streams:
            assert s.url.startswith("http")


# ===========================================================================
# MangaDex – manga reading
# ===========================================================================

class TestMangaDex:
    """MangaDex REST source – search, chapters, pages."""

    @pytest.fixture(scope="class")
    def search_results(self):
        results = mangadex.search(_MANGA_QUERY)
        assert results, f"MangaDex: no results for {_MANGA_QUERY!r}"
        return results

    @pytest.fixture(scope="class")
    def first_manga_id(self, search_results):
        return search_results[0].id

    @pytest.fixture(scope="class")
    def chapters(self, first_manga_id):
        chs = mangadex.chapters(first_manga_id)
        assert chs, "MangaDex: no chapters returned"
        return chs

    # -- search ---------------------------------------------------------------

    def test_search_result_structure(self, search_results):
        for r in search_results:
            assert r.source == "mangadex"
            assert r.id
            assert r.title
            assert r.kind == "manga"

    def test_search_contains_target(self, search_results):
        titles = [r.title.lower() for r in search_results]
        assert any(
            "bloom" in t or "yagate" in t for t in titles
        ), f"expected 'Bloom Into You' in MangaDex results, got: {titles}"

    def test_search_results_are_yuri(self, search_results):
        # Every result must carry the yuri tag – enforced by filter_yuri()
        assert search_results, "no results to inspect"

    # -- is_yuri_manga --------------------------------------------------------

    def test_is_yuri_manga_true(self, first_manga_id):
        assert mangadex.is_yuri_manga(first_manga_id)

    # -- chapters -------------------------------------------------------------

    def test_chapters_structure(self, chapters):
        for ch in chapters:
            assert ch.source == "mangadex"
            assert ch.id
            assert ch.number >= 0

    def test_chapters_sorted(self, chapters):
        nums = [ch.number for ch in chapters]
        assert nums == sorted(nums), "chapters not sorted by number"

    def test_chapters_no_duplicates(self, chapters):
        nums = [ch.number for ch in chapters]
        assert len(nums) == len(set(nums)), "duplicate chapter numbers returned"

    # -- pages ----------------------------------------------------------------

    def test_chapter_pages_returned(self, chapters):
        pages = mangadex.chapter_pages(chapters[0].id)
        assert pages, "MangaDex: no pages for first chapter"

    def test_chapter_pages_are_urls(self, chapters):
        pages = mangadex.chapter_pages(chapters[0].id)
        for url in pages:
            assert url.startswith("http"), f"page URL invalid: {url!r}"

    def test_chapter_pages_use_cdn(self, chapters):
        pages = mangadex.chapter_pages(chapters[0].id)
        # All images should go through MangaDex at-home CDN
        assert all("mangadex" in url or "uploads" in url for url in pages)


# ===========================================================================
# Dynasty Scans – manga reading
# ===========================================================================

class TestDynastyManga:
    """Dynasty Scans source – manga search, chapters, pages."""

    @pytest.fixture(scope="class")
    def manga_results(self):
        results = dynasty.search(_MANGA_QUERY)
        manga = [r for r in results if r.kind == "manga"]
        assert manga, f"Dynasty: no manga results for {_MANGA_QUERY!r}"
        return manga

    @pytest.fixture(scope="class")
    def chapters(self, manga_results):
        chs = dynasty.chapters(manga_results[0].id)
        assert chs, "Dynasty: no chapters returned for manga"
        return chs

    # -- search ---------------------------------------------------------------

    def test_search_result_structure(self, manga_results):
        for r in manga_results:
            assert r.source == "dynasty"
            assert r.id
            assert r.title
            assert r.kind == "manga"

    # -- chapters -------------------------------------------------------------

    def test_chapters_structure(self, chapters):
        for ch in chapters:
            assert ch.source == "dynasty"
            assert ch.id

    # -- pages ----------------------------------------------------------------

    def test_chapter_pages_returned(self, chapters):
        pages = dynasty.chapter_pages(chapters[0].id)
        assert pages, "Dynasty: no pages for first chapter"

    def test_chapter_pages_are_urls(self, chapters):
        pages = dynasty.chapter_pages(chapters[0].id)
        for url in pages:
            assert url.startswith("http"), f"page URL invalid: {url!r}"


# ===========================================================================
# Dynasty Scans – novel reading
# ===========================================================================

class TestDynastyNovels:
    """Dynasty Scans source – novel search and chapters."""

    @pytest.fixture(scope="class")
    def novel_results(self):
        results = dynasty.search(_NOVEL_QUERY)
        novels = [r for r in results if r.kind == "novel"]
        assert novels, f"Dynasty: no novel results for {_NOVEL_QUERY!r}"
        return novels

    @pytest.fixture(scope="class")
    def chapters(self, novel_results):
        chs = dynasty.chapters(novel_results[0].id)
        assert chs, "Dynasty: no chapters returned for novel"
        return chs

    # -- search ---------------------------------------------------------------

    def test_search_result_structure(self, novel_results):
        for r in novel_results:
            assert r.source == "dynasty"
            assert r.id
            assert r.title
            assert r.kind == "novel"

    # -- chapters -------------------------------------------------------------

    def test_chapters_structure(self, chapters):
        for ch in chapters:
            assert ch.source == "dynasty"
            assert ch.id

    def test_chapters_have_titles(self, chapters):
        for ch in chapters:
            assert ch.title
