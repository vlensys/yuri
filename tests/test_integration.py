from __future__ import annotations

import pytest

from yuri_cli.sources import allanime, anixplay, dynasty, mangadex

pytestmark = pytest.mark.integration

_ANIME_QUERY = "bloom into you"
_MANGA_QUERY = "bloom into you"
_NOVEL_QUERY = "I Favor the Villainess"


class TestAllAnime:
    @pytest.fixture(scope="class")
    def search_results(self):
        results = allanime.search(_ANIME_QUERY)
        assert results, f"AllAnime: no results for {_ANIME_QUERY!r}"
        return results

    @pytest.fixture(scope="class")
    def first_show_id(self, search_results):
        return search_results[0].id

    def test_search_result_structure(self, search_results):
        for r in search_results:
            assert r.source == "allanime"
            assert r.id
            assert r.title
            assert r.kind == "anime"

    def test_search_contains_target(self, search_results):
        titles = [r.title.lower() for r in search_results]
        assert any("bloom" in t or "yagate" in t or "kimi ni naru" in t for t in titles)

    def test_show_detail(self, first_show_id):
        detail = allanime.show(first_show_id)
        assert detail.get("_id") == first_show_id
        assert detail.get("name")
        assert detail.get("availableEpisodesDetail") is not None

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
        assert nums == sorted(nums)

    def test_episodes_dub_no_crash(self, first_show_id):
        eps = allanime.episodes(first_show_id, translation_type="dub")
        for ep in eps:
            assert ep.source == "allanime"
            assert ep.number >= 0

    def test_streams_sub_resolve(self, first_show_id):
        eps = allanime.episodes(first_show_id, translation_type="sub")
        assert eps
        streams = allanime.streams(first_show_id, eps[0].id, translation_type="sub")
        if not streams:
            pytest.skip("AllAnime returned 0 streams – provider may be down")
        for s in streams:
            assert s.url.startswith("http")

    def test_streams_sub_sorted_by_priority(self, first_show_id):
        eps = allanime.episodes(first_show_id, translation_type="sub")
        if not eps:
            pytest.skip("no sub episodes")
        streams = allanime.streams(first_show_id, eps[0].id, translation_type="sub")
        if len(streams) < 2:
            pytest.skip("only one stream")
        keys = [allanime._stream_sort_key(s) for s in streams]
        assert keys == sorted(keys, reverse=True)

    def test_streams_dub_no_crash(self, first_show_id):
        eps = allanime.episodes(first_show_id, translation_type="dub")
        if not eps:
            pytest.skip("no dub episodes for this title")
        streams = allanime.streams(first_show_id, eps[0].id, translation_type="dub")
        for s in streams:
            assert s.url.startswith("http")


class TestAniXPlay:
    @pytest.fixture(scope="class")
    def search_results(self):
        results = anixplay.search(_ANIME_QUERY)
        assert results, f"AniXPlay: no results for {_ANIME_QUERY!r}"
        return results

    @pytest.fixture(scope="class")
    def first_show_id(self, search_results):
        return search_results[0].id

    def test_search_result_structure(self, search_results):
        for r in search_results:
            assert r.source == "anixplay"
            assert r.id
            assert r.title
            assert r.kind == "anime"

    def test_episodes_sub_returned(self, first_show_id):
        eps = anixplay.episodes(first_show_id, mode="sub")
        assert eps, "AniXPlay: no sub episodes found"

    def test_episodes_sub_structure(self, first_show_id):
        eps = anixplay.episodes(first_show_id, mode="sub")
        for ep in eps:
            assert ep.source == "anixplay"
            assert ep.id
            assert ep.number >= 0

    def test_episodes_dub_no_crash(self, first_show_id):
        eps = anixplay.episodes(first_show_id, mode="dub")
        for ep in eps:
            assert ep.source == "anixplay"
            assert ep.number >= 0

    def test_streams_sub_no_crash(self, first_show_id):
        eps = anixplay.episodes(first_show_id, mode="sub")
        if not eps:
            pytest.skip("no sub episodes")
        streams = anixplay.streams(first_show_id, eps[0].id, mode="sub")
        if not streams:
            pytest.skip("AniXPlay returned 0 streams – player endpoint may be down")
        for s in streams:
            assert s.url.startswith("http")

    def test_streams_dub_no_crash(self, first_show_id):
        eps = anixplay.episodes(first_show_id, mode="dub")
        if not eps:
            pytest.skip("no dub episodes for this title")
        streams = anixplay.streams(first_show_id, eps[0].id, mode="dub")
        for s in streams:
            assert s.url.startswith("http")


class TestMangaDex:
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

    def test_search_result_structure(self, search_results):
        for r in search_results:
            assert r.source == "mangadex"
            assert r.id
            assert r.title
            assert r.kind == "manga"

    def test_search_contains_target(self, search_results):
        titles = [r.title.lower() for r in search_results]
        assert any("bloom" in t or "yagate" in t for t in titles)

    def test_is_yuri_manga_true(self, first_manga_id):
        assert mangadex.is_yuri_manga(first_manga_id)

    def test_chapters_structure(self, chapters):
        for ch in chapters:
            assert ch.source == "mangadex"
            assert ch.id
            assert ch.number >= 0

    def test_chapters_sorted(self, chapters):
        nums = [ch.number for ch in chapters]
        assert nums == sorted(nums)

    def test_chapters_no_duplicates(self, chapters):
        nums = [ch.number for ch in chapters]
        assert len(nums) == len(set(nums))

    def test_chapter_pages_returned(self, chapters):
        pages = mangadex.chapter_pages(chapters[0].id)
        assert pages, "MangaDex: no pages for first chapter"

    def test_chapter_pages_are_urls(self, chapters):
        pages = mangadex.chapter_pages(chapters[0].id)
        for url in pages:
            assert url.startswith("http")

    def test_chapter_pages_use_cdn(self, chapters):
        pages = mangadex.chapter_pages(chapters[0].id)
        assert all("mangadex" in url or "uploads" in url for url in pages)


class TestDynastyManga:
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

    def test_search_result_structure(self, manga_results):
        for r in manga_results:
            assert r.source == "dynasty"
            assert r.id
            assert r.title
            assert r.kind == "manga"

    def test_chapters_structure(self, chapters):
        for ch in chapters:
            assert ch.source == "dynasty"
            assert ch.id

    def test_chapter_pages_returned(self, chapters):
        pages = dynasty.chapter_pages(chapters[0].id)
        assert pages, "Dynasty: no pages for first chapter"

    def test_chapter_pages_are_urls(self, chapters):
        pages = dynasty.chapter_pages(chapters[0].id)
        for url in pages:
            assert url.startswith("http")


class TestDynastyNovels:
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

    def test_search_result_structure(self, novel_results):
        for r in novel_results:
            assert r.source == "dynasty"
            assert r.id
            assert r.title
            assert r.kind == "novel"

    def test_chapters_structure(self, chapters):
        for ch in chapters:
            assert ch.source == "dynasty"
            assert ch.id

    def test_chapters_have_titles(self, chapters):
        for ch in chapters:
            assert ch.title
