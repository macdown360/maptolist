import types
import unittest
from unittest.mock import patch

from app.main import fetch_places


class FakeResponse:
    def __init__(self, payload, text=""):
        self._payload = payload
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.page2_attempts = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None, follow_redirects=False):
        params = params or {}

        if "textsearch" in url:
            token = params.get("pagetoken")
            if not token:
                return FakeResponse(
                    {
                        "status": "OK",
                        "results": [{"place_id": f"p{i}", "name": f"Place {i}", "formatted_address": f"Addr {i}"} for i in range(20)],
                        "next_page_token": "page-2",
                    }
                )

            if token == "page-2":
                self.page2_attempts += 1
                if self.page2_attempts == 1:
                    return FakeResponse(
                        {
                            "status": "INVALID_REQUEST",
                            "results": [],
                        }
                    )
                return FakeResponse(
                    {
                        "status": "OK",
                        "results": [{"place_id": f"p{20 + i}", "name": f"Place {20 + i}", "formatted_address": f"Addr {20 + i}"} for i in range(20)],
                        "next_page_token": "page-3",
                    }
                )

            if token == "page-3":
                return FakeResponse(
                    {
                        "status": "OK",
                        "results": [{"place_id": f"p{40 + i}", "name": f"Place {40 + i}", "formatted_address": f"Addr {40 + i}"} for i in range(20)],
                    }
                )

        if "details" in url:
            place_id = params.get("place_id", "")
            return FakeResponse(
                {
                    "result": {
                        "name": place_id,
                        "website": "",
                        "formatted_phone_number": "",
                        "formatted_address": f"Address for {place_id}",
                        "address_components": [],
                        "types": ["restaurant"],
                        "rating": 4.5,
                        "user_ratings_total": 10,
                    }
                }
            )

        return FakeResponse({})


async def fake_extract_email_from_website(client, website):
    return ""


async def fake_sleep(_seconds):
    return None


class FetchPlacesPaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_places_retries_next_page_token_until_max_results(self):
        with patch("app.main.httpx.AsyncClient", FakeAsyncClient), patch(
            "app.main.extract_email_from_website", fake_extract_email_from_website
        ), patch("app.main.asyncio", types.SimpleNamespace(sleep=fake_sleep), create=True):
            items = await fetch_places(
                query="cafe tokyo",
                language="ja",
                max_results=50,
                api_key="dummy-key",
            )

        self.assertEqual(len(items), 50)


if __name__ == "__main__":
    unittest.main()
