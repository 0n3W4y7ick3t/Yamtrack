from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import MediaTypes, Sources


class MediaSearchNativeTitleTests(TestCase):
    """The search page shows the Japanese name of a result."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

        search_patcher = patch("app.providers.services.search")
        self.mock_search = search_patcher.start()
        self.addCleanup(search_patcher.stop)
        self.mock_search.return_value = {
            "page": 1,
            "total_results": 3,
            "total_pages": 1,
            "results": [
                {
                    "media_id": "7346",
                    "title": "The Legend of Zelda: Breath of the Wild",
                    "native_title": "ゼルダの伝説 ブレス オブ ザ ワイルド",
                    "media_type": MediaTypes.GAME.value,
                    "source": Sources.IGDB.value,
                    "image": "http://example.com/botw.jpg",
                },
                {
                    "media_id": "9927",
                    "title": "ペルソナ5",
                    "native_title": "ペルソナ5",
                    "media_type": MediaTypes.GAME.value,
                    "source": Sources.IGDB.value,
                    "image": "http://example.com/p5.jpg",
                },
                {
                    "media_id": "1942",
                    "title": "The Witcher 3: Wild Hunt",
                    "native_title": None,
                    "media_type": MediaTypes.GAME.value,
                    "source": Sources.IGDB.value,
                    "image": "http://example.com/witcher.jpg",
                },
            ],
        }

    def assert_native_titles(self, layout):
        """Check the native title line for one search layout."""
        response = self.client.get(
            reverse("search") + f"?media_type=game&q=ゼルダ&layout={layout}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, ">ゼルダの伝説 ブレス オブ ザ ワイルド</p>", count=1
        )
        # a native title equal to the title is not repeated under it
        self.assertNotContains(response, ">ペルソナ5</p>")
        self.assertNotContains(response, ">None</p>")

    def test_grid_layout_shows_native_title_under_title(self):
        """The grid card prints the Japanese name on a second line."""
        self.assert_native_titles("grid")

    def test_list_layout_shows_native_title_under_title(self):
        """The list card prints the Japanese name on a second line."""
        self.assert_native_titles("list")
