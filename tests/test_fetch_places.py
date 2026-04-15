import sqlite3
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from app.main import discover_contact_form_url, fetch_places, init_db, split_jp_address, upsert_lead


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


class FallbackDetailClient(FakeAsyncClient):
    async def get(self, url, params=None, follow_redirects=False):
        params = params or {}
        if "textsearch" in url:
            return FakeResponse(
                {
                    "status": "OK",
                    "results": [
                        {
                            "place_id": "p1",
                            "name": "Office 1",
                            "formatted_address": "日本、〒272-0023 千葉県市川市南八幡４丁目２−５",
                            "rating": 4.8,
                            "user_ratings_total": 12,
                            "types": ["lawyer"],
                        },
                        {
                            "place_id": "p2",
                            "name": "Office 2",
                            "formatted_address": "日本、〒272-0034 千葉県市川市市川１丁目７−１",
                            "rating": 4.6,
                            "user_ratings_total": 8,
                            "types": ["lawyer"],
                        },
                    ],
                }
            )

        if "details" in url:
            place_id = params.get("place_id", "")
            if place_id == "p1":
                return FakeResponse({"status": "OK", "result": {"name": "Office 1", "types": ["lawyer"]}})
            return FakeResponse({"status": "OVER_QUERY_LIMIT", "result": {}})

        return FakeResponse({})


class FakeContactFormClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None, follow_redirects=False):
        if url == "https://example.com":
            return FakeResponse({}, text='''
                <html><body>
                  <a href="/company">会社概要</a>
                  <a href="/contact">お問い合わせ</a>
                </body></html>
            ''')
        if url == "https://example.com/contact":
            return FakeResponse({}, text='''
                <html><body>
                  <h1>お問い合わせフォーム</h1>
                  <form action="/send" method="post">
                    <input type="text" name="name" />
                    <input type="email" name="email" />
                    <textarea name="message"></textarea>
                    <button type="submit">送信</button>
                  </form>
                </body></html>
            ''')
        return FakeResponse({}, text="<html><body>No form</body></html>")


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

    async def test_fetch_places_falls_back_to_textsearch_fields_when_details_are_missing(self):
        with patch("app.main.httpx.AsyncClient", FallbackDetailClient), patch(
            "app.main.extract_email_from_website", fake_extract_email_from_website
        ), patch("app.main.asyncio", types.SimpleNamespace(sleep=fake_sleep), create=True):
            items = await fetch_places(
                query="lawyer ichikawa",
                language="ja",
                max_results=10,
                api_key="dummy-key",
                place_type="lawyer",
            )

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["rating"], 4.8)
        self.assertEqual(items[1]["user_ratings_total"], 8)

    async def test_discover_contact_form_url_finds_contact_page(self):
        async with FakeContactFormClient() as client:
            url = await discover_contact_form_url(client, "https://example.com")

        self.assertEqual(url, "https://example.com/contact")

    def test_split_jp_address_keeps_full_city_name(self):
        parts = split_jp_address("日本、〒272-0023 千葉県市川市南八幡４丁目２−５")
        self.assertEqual(parts["prefecture"].strip(), "千葉県")
        self.assertEqual(parts["city"].strip(), "市川市")

    def test_upsert_lead_preserves_existing_values_when_new_data_is_blank(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch("app.main.DB_PATH", Path(tmpdir) / "test.db"):
            init_db()
            upsert_lead(
                {
                    "name": "Office A",
                    "place_id": "abc123",
                    "website": "https://example.com",
                    "phone": "03-0000-0000",
                    "email": "info@example.com",
                    "address": "千葉県市川市1-2-3",
                    "category": "法律事務所",
                    "industry": "専門サービス",
                    "rating": 4.8,
                    "user_ratings_total": 12,
                    "prefecture": "千葉県",
                    "city": "市川市",
                },
                user_id=1,
            )
            upsert_lead(
                {
                    "name": "Office A",
                    "place_id": "abc123",
                    "website": "",
                    "phone": "",
                    "email": "",
                    "address": "",
                    "category": "",
                    "industry": "",
                    "rating": None,
                    "user_ratings_total": None,
                    "prefecture": "",
                    "city": "",
                },
                user_id=None,
            )

            conn = sqlite3.connect(Path(tmpdir) / "test.db")
            conn.row_factory = sqlite3.Row
            row = conn.execute("select website, rating, user_ratings_total, user_id from leads where place_id='abc123'").fetchone()
            conn.close()

            self.assertEqual(row["website"], "https://example.com")
            self.assertEqual(row["rating"], 4.8)
            self.assertEqual(row["user_ratings_total"], 12)
            self.assertEqual(row["user_id"], 1)

    def test_upsert_lead_appends_new_unique_places(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch("app.main.DB_PATH", Path(tmpdir) / "test.db"):
            init_db()
            created1 = upsert_lead({"name": "A", "place_id": "p1"}, user_id=1)
            created2 = upsert_lead({"name": "B", "place_id": "p2"}, user_id=1)

            conn = sqlite3.connect(Path(tmpdir) / "test.db")
            count = conn.execute("select count(*) from leads").fetchone()[0]
            conn.close()

            self.assertTrue(created1)
            self.assertTrue(created2)
            self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
