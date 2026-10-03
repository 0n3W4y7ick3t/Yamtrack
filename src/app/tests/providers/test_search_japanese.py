from unittest.mock import patch

import requests
from django.core.cache import cache
from django.test import TestCase, override_settings

from app.models import MediaTypes, Sources
from app.providers import igdb, japanese, mal, tmdb


def igdb_multiquery_response(games):
    """Build an IGDB multiquery response for a list of games."""
    return [
        {"name": "SearchResults", "result": games},
        {"name": "TotalCount", "count": len(games)},
    ]


class IGDBJapaneseSearch(TestCase):
    """Searching IGDB by a Japanese name."""

    def setUp(self):
        """Clear cached searches and stub the IGDB token."""
        cache.clear()
        token_patcher = patch("app.providers.igdb.get_access_token")
        token_patcher.start().return_value = "token"
        self.addCleanup(token_patcher.stop)

    @patch("app.providers.igdb.services.api_request")
    def test_query_matches_localized_and_alternative_names(self, mock_api_request):
        """A game is found by its localized name, not only by its main name."""
        mock_api_request.return_value = igdb_multiquery_response([])

        igdb.search("ゼルダの伝説", 1)

        _, kwargs = mock_api_request.call_args
        self.assertIn(
            '(name ~ *"ゼルダの伝説"*'
            ' | alternative_names.name ~ *"ゼルダの伝説"*'
            ' | game_localizations.name ~ *"ゼルダの伝説"*)'
            " & game_type = ",
            kwargs["data"],
        )

    @patch("app.providers.igdb.services.api_request")
    def test_query_escapes_quotes_and_backslashes_in_every_clause(
        self,
        mock_api_request,
    ):
        """Quotes and backslashes in the search text cannot end the quoted string."""
        mock_api_request.return_value = igdb_multiquery_response([])

        igdb.search('say "hi"\\', 1)

        _, kwargs = mock_api_request.call_args
        escaped = 'say \\"hi\\"\\\\'
        self.assertIn(
            f'where (name ~ *"{escaped}"*'
            f' | alternative_names.name ~ *"{escaped}"*'
            f' | game_localizations.name ~ *"{escaped}"*)',
            kwargs["data"],
        )

    @patch("app.providers.igdb.services.api_request")
    def test_result_carries_japanese_name(self, mock_api_request):
        """The Japan localization becomes the native title of a result."""
        mock_api_request.return_value = igdb_multiquery_response(
            [
                {
                    "id": 7346,
                    "name": "The Legend of Zelda: Breath of the Wild",
                    "cover": {"id": 1, "image_id": "co3p2d"},
                    "game_localizations": [
                        {
                            "id": 10,
                            "name": "젤다의 전설 브레스 오브 더 와일드",
                            "region": {"id": 2, "identifier": "ko-KR"},
                        },
                        {
                            "id": 11,
                            "name": "ゼルダの伝説 ブレス オブ ザ ワイルド",
                            "region": {"id": 3, "identifier": "ja-JP"},
                        },
                    ],
                },
                {
                    "id": 1942,
                    "name": "The Witcher 3: Wild Hunt",
                    "cover": {"id": 2, "image_id": "co1wyy"},
                },
                {
                    "id": 250324,
                    "name": "Islands Expansion",
                    "cover": {"id": 3, "image_id": "co5xyz"},
                    "game_localizations": [
                        {"id": 12, "region": {"id": 3, "identifier": "ja-JP"}},
                    ],
                },
            ],
        )

        response = igdb.search("ゼルダの伝説", 1)

        self.assertEqual(
            [
                (
                    game["media_id"],
                    game["source"],
                    game["media_type"],
                    game["title"],
                    game["native_title"],
                )
                for game in response["results"]
            ],
            [
                (
                    7346,
                    Sources.IGDB.value,
                    MediaTypes.GAME.value,
                    "The Legend of Zelda: Breath of the Wild",
                    "ゼルダの伝説 ブレス オブ ザ ワイルド",
                ),
                (
                    1942,
                    Sources.IGDB.value,
                    MediaTypes.GAME.value,
                    "The Witcher 3: Wild Hunt",
                    None,
                ),
                (
                    250324,
                    Sources.IGDB.value,
                    MediaTypes.GAME.value,
                    "Islands Expansion",
                    None,
                ),
            ],
        )

    @patch("app.providers.igdb.services.api_request")
    def test_query_requests_localized_names(self, mock_api_request):
        """The localized names are requested together with the search."""
        mock_api_request.return_value = igdb_multiquery_response([])

        igdb.search("ペルソナ", 1)

        _, kwargs = mock_api_request.call_args
        self.assertIn(
            "fields name,cover.image_id,"
            "game_localizations.name,game_localizations.region.identifier;",
            kwargs["data"],
        )


class MALJapaneseSearch(TestCase):
    """Searching MyAnimeList by a Japanese name."""

    def setUp(self):
        """Clear cached searches."""
        cache.clear()

    @patch("app.providers.mal.services.api_request")
    def test_result_carries_japanese_title(self, mock_api_request):
        """The Japanese alternative title becomes the native title of a result."""
        mock_api_request.return_value = {
            "data": [
                {
                    "node": {
                        "id": 52991,
                        "title": "Sousou no Frieren",
                        "main_picture": {"large": "http://example.com/frieren.jpg"},
                        "media_type": "tv",
                        "alternative_titles": {
                            "synonyms": [],
                            "en": "Frieren: Beyond Journey's End",
                            "ja": "葬送のフリーレン",
                        },
                    },
                },
                {
                    "node": {
                        "id": 1,
                        "title": "Cowboy Bebop",
                        "main_picture": {"large": "http://example.com/bebop.jpg"},
                        "media_type": "tv",
                        "alternative_titles": {"synonyms": [], "en": "", "ja": ""},
                    },
                },
            ],
        }

        response = mal.search(MediaTypes.ANIME.value, "葬送のフリーレン", 1)

        _, kwargs = mock_api_request.call_args
        self.assertEqual(kwargs["params"]["fields"], "media_type,alternative_titles")
        self.assertEqual(
            [
                (anime["media_id"], anime["title"], anime["native_title"])
                for anime in response["results"]
            ],
            [
                (52991, "Sousou no Frieren", "葬送のフリーレン"),
                (1, "Cowboy Bebop", None),
            ],
        )

    @patch("app.providers.mal.services.api_request")
    def test_short_japanese_query_is_answered_by_anilist(self, mock_api_request):
        """MyAnimeList rejects queries under 3 characters, AniList does not."""
        mock_api_request.return_value = {
            "data": {
                "Page": {
                    "pageInfo": {"total": 3},
                    "media": [
                        {
                            "idMal": 38000,
                            "title": {
                                "romaji": "Kimetsu no Yaiba",
                                "native": "鬼滅の刃",
                            },
                            "coverImage": {"large": "http://example.com/kimetsu.jpg"},
                        },
                        {
                            "idMal": None,
                            "title": {"romaji": "Not on MyAnimeList", "native": "鬼滅"},
                            "coverImage": {"large": "http://example.com/other.jpg"},
                        },
                    ],
                },
            },
        }

        response = mal.search(MediaTypes.ANIME.value, "鬼滅", 1)

        args, kwargs = mock_api_request.call_args
        self.assertEqual(args[2], "https://graphql.anilist.co")
        self.assertEqual(
            kwargs["params"]["variables"],
            {"search": "鬼滅", "type": "ANIME", "page": 1, "perPage": 24},
        )
        self.assertEqual(
            response["results"],
            [
                {
                    "media_id": 38000,
                    "source": Sources.MAL.value,
                    "media_type": MediaTypes.ANIME.value,
                    "title": "Kimetsu no Yaiba",
                    "native_title": "鬼滅の刃",
                    "image": "http://example.com/kimetsu.jpg",
                },
            ],
        )
        self.assertEqual(response["total_results"], 3)

    @patch("app.providers.mal.services.api_request")
    def test_short_latin_query_stays_on_myanimelist(self, mock_api_request):
        """Only Japanese text is redirected, other short queries behave as before."""
        mock_api_request.return_value = {"data": []}

        mal.search(MediaTypes.MANGA.value, "ab", 1)

        args, _ = mock_api_request.call_args
        self.assertEqual(args[2], "https://api.myanimelist.net/v2/manga")

    @patch("app.providers.mal.services.api_request")
    def test_anilist_failure_returns_no_results_and_is_not_cached(
        self,
        mock_api_request,
    ):
        """A failing AniList leaves a short query empty, but only for that request."""
        anilist_page = {
            "data": {
                "Page": {
                    "pageInfo": {"total": 1},
                    "media": [
                        {
                            "idMal": 38000,
                            "title": {
                                "romaji": "Kimetsu no Yaiba",
                                "native": "鬼滅の刃",
                            },
                            "coverImage": {"large": "http://example.com/kimetsu.jpg"},
                        },
                    ],
                },
            },
        }
        mock_api_request.side_effect = [
            requests.exceptions.ConnectionError,
            {"data": None, "errors": [{"message": "Too Many Requests"}]},
            anilist_page,
        ]

        with self.assertLogs("app.providers.japanese", level="WARNING"):
            failed = mal.search(MediaTypes.ANIME.value, "鬼滅", 1)
        with self.assertLogs("app.providers.japanese", level="WARNING"):
            rejected = mal.search(MediaTypes.ANIME.value, "鬼滅", 1)
        recovered = mal.search(MediaTypes.ANIME.value, "鬼滅", 1)

        self.assertEqual(failed["results"], [])
        self.assertEqual(failed["total_results"], 0)
        self.assertEqual(rejected["results"], [])
        self.assertEqual([anime["media_id"] for anime in recovered["results"]], [38000])
        self.assertEqual(mock_api_request.call_count, 3)

    @patch("app.providers.mal.services.api_request")
    def test_anilist_results_are_cached(self, mock_api_request):
        """A successful AniList answer is reused like any other search."""
        mock_api_request.return_value = {
            "data": {"Page": {"pageInfo": {"total": 0}, "media": []}},
        }

        mal.search(MediaTypes.ANIME.value, "鬼滅", 2)
        mal.search(MediaTypes.ANIME.value, "鬼滅", 2)

        mock_api_request.assert_called_once()
        _, kwargs = mock_api_request.call_args
        self.assertEqual(kwargs["params"]["variables"]["page"], 2)

    @patch("app.providers.mal.services.api_request")
    def test_three_japanese_characters_stay_on_myanimelist(self, mock_api_request):
        """The redirect covers only what MyAnimeList refuses."""
        mock_api_request.return_value = {"data": []}

        mal.search(MediaTypes.ANIME.value, "鬼滅の", 1)
        mal.search(MediaTypes.ANIME.value, " 鬼滅 ", 1)

        urls = [call.args[2] for call in mock_api_request.call_args_list]
        self.assertEqual(
            urls,
            ["https://api.myanimelist.net/v2/anime", "https://graphql.anilist.co"],
        )

    @patch("app.providers.mal.services.api_request")
    def test_anilist_search_follows_the_adult_content_setting(self, mock_api_request):
        """Adult entries are excluded unless MyAnimeList NSFW results are enabled."""
        mock_api_request.return_value = {
            "data": {"Page": {"pageInfo": {"total": 0}, "media": []}},
        }

        mal.search(MediaTypes.ANIME.value, "鬼滅", 1)
        _, kwargs = mock_api_request.call_args
        self.assertIn("isAdult: false", kwargs["params"]["query"])

        with override_settings(MAL_NSFW=True):
            mal.search(MediaTypes.ANIME.value, "呪術", 1)
        _, kwargs = mock_api_request.call_args
        self.assertNotIn("isAdult", kwargs["params"]["query"])


def tmdb_search_response(results):
    """Build a TMDB search response."""
    return {"page": 1, "results": results, "total_pages": 1, "total_results": 2}


class TMDBJapaneseSearch(TestCase):
    """Searching TMDB by a Japanese name."""

    def setUp(self):
        """Clear cached searches."""
        cache.clear()

    @patch("app.providers.tmdb.services.api_request")
    def test_japanese_query_fetches_japanese_titles(self, mock_api_request):
        """A Japanese query gets the Japanese name of every result."""
        mock_api_request.side_effect = [
            tmdb_search_response(
                [
                    {
                        "id": 27205,
                        "title": "Inception",
                        "original_title": "Inception",
                        "original_language": "en",
                        "poster_path": "/inception.jpg",
                    },
                    {
                        "id": 129,
                        "title": "Spirited Away",
                        "original_title": "千と千尋の神隠し",
                        "original_language": "ja",
                        "poster_path": "/spirited.jpg",
                    },
                ],
            ),
            tmdb_search_response(
                [
                    {"id": 27205, "title": "インセプション"},
                    {"id": 129, "title": "千と千尋の神隠し"},
                ],
            ),
        ]

        response = tmdb.search(MediaTypes.MOVIE.value, "インセプション", 1)

        self.assertEqual(mock_api_request.call_count, 2)
        first_call, second_call = mock_api_request.call_args_list
        self.assertEqual(first_call.kwargs["params"]["language"], "en")
        self.assertEqual(second_call.kwargs["params"]["language"], "ja-JP")
        self.assertEqual(second_call.kwargs["params"]["query"], "インセプション")
        self.assertEqual(
            [
                (movie["media_id"], movie["title"], movie["native_title"])
                for movie in response["results"]
            ],
            [
                (27205, "Inception", "インセプション"),
                (129, "Spirited Away", "千と千尋の神隠し"),
            ],
        )

    @patch("app.providers.tmdb.services.api_request")
    def test_other_query_uses_original_title_of_japanese_works(self, mock_api_request):
        """Without a Japanese query no second call is made."""
        mock_api_request.return_value = tmdb_search_response(
            [
                {
                    "id": 55582,
                    "name": "Solitary Gourmet",
                    "original_name": "孤独のグルメ",
                    "original_language": "ja",
                    "poster_path": "/gourmet.jpg",
                },
                {
                    "id": 1396,
                    "name": "Breaking Bad",
                    "original_name": "Breaking Bad",
                    "original_language": "en",
                    "poster_path": "/bb.jpg",
                },
                {
                    "id": 94605,
                    "name": "Arcane",
                    "original_name": "Arcane",
                    "original_language": "fr",
                    "poster_path": "/arcane.jpg",
                },
            ],
        )

        response = tmdb.search(MediaTypes.TV.value, "gourmet", 1)

        self.assertEqual(mock_api_request.call_count, 1)
        self.assertEqual(
            [(tv["media_id"], tv["native_title"]) for tv in response["results"]],
            [(55582, "孤独のグルメ"), (1396, None), (94605, None)],
        )

    @patch("app.providers.tmdb.services.api_request")
    def test_failed_japanese_lookup_keeps_the_results(self, mock_api_request):
        """The search still answers when the Japanese titles cannot be fetched."""
        mock_api_request.side_effect = [
            tmdb_search_response(
                [
                    {
                        "id": 27205,
                        "title": "Inception",
                        "original_title": "Inception",
                        "original_language": "en",
                        "poster_path": "/inception.jpg",
                    },
                ],
            ),
            requests.exceptions.ConnectionError(
                "Max retries exceeded with url: /3/search/movie?api_key=secret",
            ),
        ]

        with self.assertLogs("app.providers.japanese", level="WARNING") as logs:
            response = tmdb.search(MediaTypes.MOVIE.value, "インセプション", 1)

        self.assertEqual(
            [(movie["title"], movie["native_title"]) for movie in response["results"]],
            [("Inception", None)],
        )
        # the request url carries the api key, so it must stay out of the log
        self.assertNotIn("api_key", "".join(logs.output))

    @patch("app.providers.tmdb.services.api_request")
    def test_failed_japanese_lookup_is_not_cached(self, mock_api_request):
        """After a failed lookup the next identical search tries again."""
        page = tmdb_search_response(
            [
                {
                    "id": 27205,
                    "title": "Inception",
                    "original_title": "Inception",
                    "original_language": "en",
                    "poster_path": "/inception.jpg",
                },
            ],
        )
        mock_api_request.side_effect = [
            page,
            requests.exceptions.ReadTimeout,
            page,
            tmdb_search_response([{"id": 27205, "title": "インセプション"}]),
        ]

        with self.assertLogs("app.providers.japanese", level="WARNING"):
            tmdb.search(MediaTypes.MOVIE.value, "インセプション", 1)
        response = tmdb.search(MediaTypes.MOVIE.value, "インセプション", 1)

        self.assertEqual(mock_api_request.call_count, 4)
        self.assertEqual(response["results"][0]["native_title"], "インセプション")

    @patch("app.providers.tmdb.services.api_request")
    def test_japanese_tv_query_prefers_the_japanese_name(self, mock_api_request):
        """For a show the Japanese lookup wins over the original name."""
        mock_api_request.side_effect = [
            tmdb_search_response(
                [
                    {
                        "id": 1396,
                        "name": "Breaking Bad",
                        "original_name": "Breaking Bad",
                        "original_language": "en",
                        "poster_path": "/bb.jpg",
                    },
                    {
                        "id": 70523,
                        "name": "Dark",
                        "original_name": "Dark",
                        "original_language": "de",
                        "poster_path": "/dark.jpg",
                    },
                ],
            ),
            tmdb_search_response([{"id": 1396, "name": "ブレイキング・バッド"}]),
        ]

        response = tmdb.search(MediaTypes.TV.value, "ブレイキング", 2)

        _, second_call = mock_api_request.call_args_list
        self.assertEqual(second_call.kwargs["params"]["page"], 2)
        self.assertEqual(
            [(tv["media_id"], tv["native_title"]) for tv in response["results"]],
            [(1396, "ブレイキング・バッド"), (70523, None)],
        )


class ContainsJapanese(TestCase):
    """Detection of Japanese script in a search text."""

    def test_detects_kana_kanji_and_half_width_katakana(self):
        """Any Japanese script counts, mixed with Latin or not."""
        for text in (
            "鬼滅",
            "ゼルダの伝説",
            "インセプション",
            "ｶﾞﾝﾀﾞﾑ",
            "Persona 5 ザ・ロイヤル",
        ):
            with self.subTest(text=text):
                self.assertTrue(japanese.contains_japanese(text))

    def test_ignores_latin_text(self):
        """Plain Latin text, digits and punctuation are not Japanese."""
        for text in ("Persona 5", "q", "", "2001: A Space Odyssey"):
            with self.subTest(text=text):
                self.assertFalse(japanese.contains_japanese(text))
