from unittest.mock import patch

import requests
from django.core.cache import cache
from django.test import TestCase, override_settings

from app.models import MediaTypes, Sources
from app.providers import igdb, mal, tmdb


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
    def test_query_escapes_double_quotes(self, mock_api_request):
        """A double quote in the search text cannot end the quoted string."""
        mock_api_request.return_value = igdb_multiquery_response([])

        igdb.search('say "hi"', 1)

        _, kwargs = mock_api_request.call_args
        self.assertIn('name ~ *"say \\"hi\\""*', kwargs["data"])

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
    def test_anilist_failure_returns_no_results(self, mock_api_request):
        """A failing AniList leaves a short query empty, as it was before."""
        mock_api_request.side_effect = requests.exceptions.ConnectionError

        response = mal.search(MediaTypes.ANIME.value, "鬼滅", 1)

        self.assertEqual(response["results"], [])
        self.assertEqual(response["total_results"], 0)

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
            requests.exceptions.ConnectionError,
        ]

        response = tmdb.search(MediaTypes.MOVIE.value, "インセプション", 1)

        self.assertEqual(
            [(movie["title"], movie["native_title"]) for movie in response["results"]],
            [("Inception", None)],
        )
