"""Japanese names for provider search results."""

import logging
import re

import requests
from django.conf import settings

from app import helpers
from app.models import Sources
from app.providers import services

logger = logging.getLogger(__name__)

japan_region = "ja-JP"

# hiragana, katakana, CJK ideographs and half-width katakana
japanese_script = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")

anilist_url = "https://graphql.anilist.co"
anilist_search_query = """
query ($search: String, $type: MediaType, $page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    pageInfo {
      total
    }
    media(search: $search, type: $type, sort: POPULARITY_DESC%(adult_filter)s) {
      idMal
      title {
        romaji
        native
      }
      coverImage {
        large
      }
    }
  }
}
"""


def contains_japanese(text):
    """Return True when the text has kana or kanji."""
    return bool(japanese_script.search(text))


def igdb_native_title(game):
    """Return the Japanese name of an IGDB game, if it has one."""
    for localization in game.get("game_localizations", []):
        region = localization.get("region") or {}
        if region.get("identifier") == japan_region and localization.get("name"):
            return localization["name"]
    return None


def mal_native_title(node):
    """Return the Japanese title of a MyAnimeList entry, if it has one."""
    return (node.get("alternative_titles") or {}).get("ja") or None


def tmdb_japanese_titles(url, params):
    """Return the Japanese titles of a TMDB search page keyed by id, None on failure."""
    try:
        response = services.api_request(
            Sources.TMDB.value,
            "GET",
            url,
            params={**params, "language": japan_region},
        )
    except requests.exceptions.RequestException as error:
        # the request url carries the api key, so the error itself stays out of the log
        logger.warning("TMDB Japanese title lookup failed: %s", type(error).__name__)
        return None

    return {
        media["id"]: media.get("title") or media.get("name")
        for media in response["results"]
    }


def tmdb_native_title(media, japanese_titles):
    """Return the Japanese title of a TMDB search result, if it has one."""
    japanese_title = japanese_titles.get(media["id"])
    if japanese_title:
        return japanese_title

    # a Japanese work carries its Japanese title as the original one
    if media.get("original_language") == "ja":
        return media.get("original_title") or media.get("original_name") or None

    return None


def anilist_search(media_type, query, page):
    """Search AniList and return the matches as MyAnimeList results, None on failure.

    MyAnimeList rejects queries under 3 characters, which rules out short
    Japanese titles. AniList accepts them and knows each entry's MyAnimeList id.
    """
    adult_filter = "" if settings.MAL_NSFW else ", isAdult: false"
    variables = {
        "search": query,
        "type": media_type.upper(),
        "page": page,
        "perPage": settings.PER_PAGE,
    }

    try:
        response = services.api_request(
            "ANILIST",
            "POST",
            anilist_url,
            params={
                "query": anilist_search_query % {"adult_filter": adult_filter},
                "variables": variables,
            },
        )
    except requests.exceptions.RequestException as error:
        logger.warning("AniList search failed for %s: %s", query, type(error).__name__)
        return None

    if not response.get("data"):
        logger.warning(
            "AniList returned no data for %s: %s", query, response.get("errors")
        )
        return None

    page_data = response["data"]["Page"]
    results = [
        {
            "media_id": media["idMal"],
            "source": Sources.MAL.value,
            "media_type": media_type,
            "title": media["title"]["romaji"],
            "native_title": media["title"]["native"],
            "image": media["coverImage"]["large"],
        }
        for media in page_data["media"]
        if media["idMal"]
    ]

    return helpers.format_search_response(
        page,
        settings.PER_PAGE,
        page_data["pageInfo"]["total"],
        results,
    )
