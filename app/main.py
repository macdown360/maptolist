import asyncio
import base64
import ipaddress
import json
import os
import re
import secrets
from contextlib import closing
from datetime import UTC, datetime, timedelta
from email.mime.text import MIMEText
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote_plus, urljoin, urlparse
import smtplib

import httpx
from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware

from app.db import get_connection

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
POSTAL_CODE_REGEX = re.compile(r"〒?\s*(\d{3})[-ー]?\s*(\d{4})")
COUNTRY_PREFIX_REGEX = re.compile(r"^(?:日本|Japan)[、,\s　]*", re.IGNORECASE)
PREFECTURE_REGEX = re.compile(
    r"(北海道|東京都|京都府|大阪府|(?:[^\s、,]{2,3}県))"
)
CITY_REGEX = re.compile(
    r"^(.*(?:郡.*[町村]|市.*区|市|区|町|村))"
)
DEFAULT_DAILY_SEND_LIMIT = int(os.getenv("DAILY_SEND_LIMIT", "100"))
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
APP_BASE_URL = os.getenv("APP_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000")
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_hex(32))
DISABLE_GOOGLE_LOGIN = os.getenv("DISABLE_GOOGLE_LOGIN", "false").lower() == "true"
CORS_ALLOW_ORIGINS = [x.strip() for x in os.getenv("CORS_ALLOW_ORIGINS", "").split(",") if x.strip()]
DEMO_USER_GOOGLE_ID = "local-demo-user"
DEMO_USER_EMAIL = "demo@local"
DEMO_USER_NAME = "Demo User"
MY_LIST_STATUS_VALUES = {"new", "contacted", "nurturing", "closed", "excluded"}
MY_LIST_PRIORITY_VALUES = {"high", "medium", "low"}
CONTACT_PATH_HINTS = (
    "contact",
    "contact-us",
    "contactus",
    "inquiry",
    "support",
    "otoiawase",
    "toiawase",
    "form",
    "mail",
    "consult",
)
CONTACT_TEXT_HINTS = (
    "お問い合わせ",
    "お問合せ",
    "問合せ",
    "問い合わせ",
    "資料請求",
    "ご相談",
    "連絡",
    "contact",
    "inquiry",
    "support",
)
NEGATIVE_FORM_HINTS = ("newsletter", "subscribe", "search", "login", "signin", "register", "comment")
FORM_FIELD_HINTS = ("name", "email", "mail", "message", "body", "content", "inquiry", "contact", "company", "subject", "phone", "tel", "お名前", "メール", "件名", "本文")
COMMON_CONTACT_PATHS = (
    "/contact",
    "/contact/",
    "/inquiry",
    "/inquiry/",
    "/contact-us",
    "/contactus",
    "/support",
    "/form",
    "/otoiawase",
    "/toiawase",
    "/company/contact",
)

PLACE_TYPE_LABELS: dict[str, str] = {
    "accounting": "会計事務所",
    "airport": "空港",
    "amusement_park": "遊園地",
    "aquarium": "水族館",
    "art_gallery": "美術館",
    "atm": "ATM",
    "bakery": "ベーカリー",
    "bank": "銀行",
    "bar": "バー",
    "beauty_salon": "美容サロン",
    "bicycle_store": "自転車店",
    "book_store": "書店",
    "bowling_alley": "ボウリング場",
    "bus_station": "バス停",
    "cafe": "カフェ",
    "car_dealer": "カーディーラー",
    "car_rental": "レンタカー",
    "car_repair": "自動車整備",
    "car_wash": "洗車",
    "clothing_store": "衣料品店",
    "convenience_store": "コンビニ",
    "courthouse": "裁判所",
    "dentist": "歯科",
    "department_store": "百貨店",
    "doctor": "医院",
    "drugstore": "ドラッグストア",
    "electrician": "電気工事",
    "electronics_store": "家電店",
    "embassy": "大使館",
    "florist": "花屋",
    "funeral_home": "葬儀社",
    "furniture_store": "家具店",
    "gas_station": "ガソリンスタンド",
    "general_contractor": "総合工事",
    "gym": "ジム",
    "hair_care": "ヘアサロン",
    "hardware_store": "ホームセンター",
    "hospital": "病院",
    "hotel": "ホテル",
    "insurance_agency": "保険代理店",
    "jewelry_store": "宝飾店",
    "laundry": "クリーニング",
    "lawyer": "法律事務所",
    "library": "図書館",
    "local_government_office": "行政機関",
    "lodging": "宿泊施設",
    "meal_delivery": "宅配",
    "meal_takeaway": "テイクアウト",
    "movie_theater": "映画館",
    "museum": "博物館",
    "night_club": "ナイトクラブ",
    "painter": "塗装業",
    "park": "公園",
    "parking": "駐車場",
    "pet_store": "ペットショップ",
    "pharmacy": "薬局",
    "physiotherapist": "整体・リハビリ",
    "plumber": "配管工事",
    "police": "警察",
    "post_office": "郵便局",
    "real_estate_agency": "不動産",
    "restaurant": "レストラン",
    "roofing_contractor": "屋根工事",
    "rv_park": "RVパーク",
    "school": "学校",
    "shoe_store": "靴店",
    "shopping_mall": "ショッピングモール",
    "spa": "スパ",
    "stadium": "スタジアム",
    "storage": "倉庫",
    "store": "小売店",
    "subway_station": "地下鉄駅",
    "supermarket": "スーパーマーケット",
    "taxi_stand": "タクシー乗り場",
    "tourist_attraction": "観光地",
    "train_station": "駅",
    "travel_agency": "旅行代理店",
    "university": "大学",
    "veterinary_care": "動物病院",
    "zoo": "動物園",
}

PLACE_INDUSTRY_MAP: dict[str, str] = {
    "accounting": "専門サービス",
    "lawyer": "専門サービス",
    "insurance_agency": "金融・保険",
    "bank": "金融・保険",
    "atm": "金融・保険",
    "general_contractor": "建設・不動産",
    "roofing_contractor": "建設・不動産",
    "electrician": "建設・不動産",
    "plumber": "建設・不動産",
    "painter": "建設・不動産",
    "real_estate_agency": "建設・不動産",
    "car_dealer": "自動車",
    "car_repair": "自動車",
    "car_rental": "自動車",
    "car_wash": "自動車",
    "gas_station": "自動車",
    "restaurant": "飲食",
    "cafe": "飲食",
    "bar": "飲食",
    "bakery": "飲食",
    "meal_delivery": "飲食",
    "meal_takeaway": "飲食",
    "hospital": "医療・ヘルスケア",
    "doctor": "医療・ヘルスケア",
    "dentist": "医療・ヘルスケア",
    "pharmacy": "医療・ヘルスケア",
    "physiotherapist": "医療・ヘルスケア",
    "veterinary_care": "医療・ヘルスケア",
    "beauty_salon": "美容・生活",
    "hair_care": "美容・生活",
    "spa": "美容・生活",
    "laundry": "美容・生活",
    "department_store": "小売",
    "shopping_mall": "小売",
    "supermarket": "小売",
    "convenience_store": "小売",
    "clothing_store": "小売",
    "book_store": "小売",
    "electronics_store": "小売",
    "pet_store": "小売",
    "shoe_store": "小売",
    "furniture_store": "小売",
    "hotel": "観光・宿泊",
    "lodging": "観光・宿泊",
    "travel_agency": "観光・宿泊",
    "tourist_attraction": "観光・宿泊",
    "museum": "観光・宿泊",
    "art_gallery": "観光・宿泊",
    "movie_theater": "観光・娯楽",
    "night_club": "観光・娯楽",
    "amusement_park": "観光・娯楽",
    "aquarium": "観光・娯楽",
    "zoo": "観光・娯楽",
    "gym": "スポーツ",
    "stadium": "スポーツ",
    "school": "教育",
    "university": "教育",
    "library": "教育",
    "airport": "交通・公共",
    "train_station": "交通・公共",
    "subway_station": "交通・公共",
    "bus_station": "交通・公共",
    "taxi_stand": "交通・公共",
    "post_office": "交通・公共",
    "local_government_office": "公共",
    "courthouse": "公共",
    "police": "公共",
    "embassy": "公共",
    "florist": "生活サービス",
    "funeral_home": "生活サービス",
    "storage": "物流・インフラ",
    "parking": "物流・インフラ",
    "rv_park": "観光・宿泊",
    "hardware_store": "小売",
    "jewelry_store": "小売",
    "drugstore": "小売",
    "bicycle_store": "小売",
    "store": "小売",
}

TYPE_PRIORITY: list[str] = [
    "car_dealer",
    "car_repair",
    "general_contractor",
    "real_estate_agency",
    "lawyer",
    "accounting",
    "restaurant",
    "cafe",
    "hospital",
    "hotel",
    "shopping_mall",
    "supermarket",
    "school",
    "university",
    "airport",
    "train_station",
]

# ---------- レートリミット設定 ----------
# /api/import/google-places への連続呼び出しを制限する
# 環境変数 RATE_LIMIT_PLACES で上書き可能（例: "10/minute"）
DEFAULT_RATE_LIMIT_PLACES = os.getenv("RATE_LIMIT_PLACES", "5/minute")
limiter = Limiter(key_func=get_remote_address)

# ---------- データ取得件数上限 ----------
FETCH_LIMIT_PER_REQUEST: int = int(os.getenv("FETCH_LIMIT_PER_REQUEST", "50"))
FETCH_LIMIT_DAILY: int = int(os.getenv("FETCH_LIMIT_DAILY", "200"))
FETCH_LIMIT_MONTHLY: int = int(os.getenv("FETCH_LIMIT_MONTHLY", "1000"))

app = FastAPI(title="Map to List Lead Collector", version="0.3.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=86400 * 30, https_only=False)
if CORS_ALLOW_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile https://www.googleapis.com/auth/gmail.send",
        "access_type": "offline",
        "prompt": "consent",
    },
)


class ImportRequest(BaseModel):
    query: str = Field(..., description="検索キーワード。例: カフェ 東京")
    region: str = Field("", description="任意。地域キーワード")
    place_type: str = Field("", description="任意。Google Placesの業種タイプ")
    language: str = Field("ja", description="Google Places API language")
    max_results: int = Field(20, ge=1, le=50, description="取得件数上限")
    api_key: str = Field("", description="任意。ブラウザ保存キーをリクエストで渡す")


class ContactRequest(BaseModel):
    lead_ids: list[int] = Field(default_factory=list)
    subject: str
    body: str


class SuppressionRequest(BaseModel):
    email: str
    reason: str = "user_request"


class FormAdapterRequest(BaseModel):
    name: str
    domain: str
    path: str
    method: str = Field("POST")
    payload_template: dict[str, Any]
    enabled: bool = True


class BulkTagRequest(BaseModel):
    lead_ids: list[int] = Field(default_factory=list)
    category: str = ""
    industry: str = ""
    note: str = ""


class LeadSelectionRequest(BaseModel):
    lead_ids: list[int] = Field(default_factory=list)


class MyListBulkAddRequest(BaseModel):
    lead_ids: list[int] = Field(default_factory=list)
    status: str = "new"
    priority: str = "medium"
    note: str = ""


class MyListUpdateRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    note: str | None = None
    owner_name: str | None = None


class GoogleMapsKeyRequest(BaseModel):
    api_key: str


@app.on_event("startup")
def startup() -> None:
    init_db()


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                place_id TEXT UNIQUE,
                website TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                category TEXT,
                industry TEXT,
                rating DOUBLE PRECISION,
                user_ratings_total INTEGER,
                editorial_summary TEXT,
                raw_types TEXT,
                postal_code TEXT,
                prefecture TEXT,
                city TEXT,
                address_detail TEXT,
                address_components_json TEXT,
                user_id INTEGER,
                browser_client_id TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contact_logs (
                id SERIAL PRIMARY KEY,
                lead_id INTEGER NOT NULL,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                subject TEXT,
                message TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (lead_id) REFERENCES leads (id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS suppression_list (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_send_stats (
                id SERIAL PRIMARY KEY,
                day TEXT NOT NULL,
                channel TEXT NOT NULL,
                count INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(day, channel)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS manual_tags (
                id SERIAL PRIMARY KEY,
                lead_id INTEGER NOT NULL UNIQUE,
                category TEXT,
                industry TEXT,
                note TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (lead_id) REFERENCES leads (id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS form_adapters (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                domain TEXT UNIQUE NOT NULL,
                path TEXT NOT NULL,
                method TEXT NOT NULL,
                payload_template TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                google_id TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL,
                name TEXT,
                picture TEXT,
                maps_api_key TEXT DEFAULT '',
                gmail_access_token TEXT DEFAULT '',
                gmail_refresh_token TEXT DEFAULT '',
                gmail_token_expiry TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS my_list_items (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                lead_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                priority TEXT NOT NULL DEFAULT 'medium',
                owner_name TEXT,
                note TEXT,
                added_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_contacted_at TEXT,
                contact_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, lead_id),
                FOREIGN KEY (lead_id) REFERENCES leads (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contact_form_discoveries (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                lead_id INTEGER NOT NULL,
                website TEXT NOT NULL,
                form_url TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                browser_client_id TEXT DEFAULT '',
                source TEXT NOT NULL DEFAULT 'heuristic_crawl',
                confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
                checked_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, lead_id),
                FOREIGN KEY (lead_id) REFERENCES leads (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fetch_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, day)
            )
            """
        )
        try:
            conn.execute("ALTER TABLE contact_form_discoveries ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        except Exception:
            # 既存環境ではカラム追加済みの場合がある
            pass


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def get_daily_fetch_usage(user_id: int) -> int:
    """今日のユーザーのデータ取得件数を返す。"""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT count FROM fetch_usage WHERE user_id = ? AND day = ?",
            (user_id, today),
        ).fetchone()
    return row[0] if row else 0


def get_monthly_fetch_usage(user_id: int) -> int:
    """今月のユーザーのデータ取得件数合計を返す。"""
    month_prefix = datetime.now(UTC).strftime("%Y-%m")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(count), 0) FROM fetch_usage WHERE user_id = ? AND day LIKE ?",
            (user_id, f"{month_prefix}-%"),
        ).fetchone()
    return row[0] if row else 0


def record_fetch_usage(user_id: int, count: int) -> None:
    """今日の取得件数を加算して記録する。"""
    if count <= 0:
        return
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    ts = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO fetch_usage (user_id, day, count, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, day) DO UPDATE SET
                count = count + excluded.count,
                updated_at = excluded.updated_at
            """,
            (user_id, today, count, ts),
        )


def clean_address_text(raw_value: str) -> str:
    text = COUNTRY_PREFIX_REGEX.sub("", str(raw_value or "").strip())
    text = text.replace("　", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" 、")


def trim_address_detail(detail: str, place_name: str = "") -> str:
    value = clean_address_text(detail)
    if not value:
        return ""

    m = re.match(r"^(.*?\d[0-9０-９\-−ー丁目番地号]*)\s+[^0-9０-９].*$", value)
    if m:
        value = m.group(1).strip()

    if place_name:
        simplified_value = re.sub(r"\s+", "", value)
        simplified_name = re.sub(r"\s+", "", str(place_name or ""))
        if simplified_name and simplified_value.endswith(simplified_name):
            value = value[: max(0, len(value) - len(str(place_name).strip()))].strip(" 、")

    return value.strip(" 、")


def split_jp_address(raw_address: str) -> dict[str, str]:
    """Split Japanese address into postal code/prefecture/city/detail for display."""
    text = clean_address_text(raw_address)
    postal_code = ""
    prefecture = ""
    city = ""
    detail = ""

    if not text:
        return {
            "postal_code": postal_code,
            "prefecture": prefecture,
            "city": city,
            "address_detail": detail,
        }

    m_postal = POSTAL_CODE_REGEX.search(text)
    if m_postal:
        postal_code = f"{m_postal.group(1)}-{m_postal.group(2)}"
        text = (text[:m_postal.start()] + text[m_postal.end():]).strip()

    text = COUNTRY_PREFIX_REGEX.sub("", text).strip(" 、　")

    m_pref = PREFECTURE_REGEX.search(text)
    if m_pref:
        prefecture = m_pref.group(1).strip(" 、　")
        rest = text[m_pref.end():].strip(" 、　")
    else:
        rest = text

    county_match = re.match(r"^(.+?郡.+?[町村])", rest)
    if county_match:
        city = county_match.group(1).strip(" 、　")
        detail = rest[county_match.end():].strip(" 、　")
    else:
        city_match = re.match(r"^(.+?市.+?区)", rest)
        if not city_match:
            city_match = re.match(r"^(.+?市)", rest)
        if not city_match:
            city_match = re.match(r"^(.+?区)", rest)
        if not city_match:
            city_match = re.match(r"^(.+?[町村])", rest)

        if city_match:
            city = city_match.group(1).strip(" 、　")
            detail = rest[city_match.end():].strip(" 、　")
        else:
            detail = rest.strip(" 、　")

    return {
        "postal_code": postal_code,
        "prefecture": prefecture,
        "city": city,
        "address_detail": trim_address_detail(detail),
    }


def parse_address_components(address_components: list[dict[str, Any]]) -> dict[str, str]:
    """Extract key address fields from Google Places address_components."""
    if not address_components:
        return {
            "postal_code": "",
            "prefecture": "",
            "city": "",
            "address_detail": "",
        }

    by_type: dict[str, str] = {}
    for component in address_components:
        long_name = str(component.get("long_name", "")).strip()
        types = component.get("types", [])
        if not long_name or not isinstance(types, list):
            continue
        for t in types:
            t_name = str(t).strip()
            if t_name and t_name not in by_type:
                by_type[t_name] = long_name

    postal = by_type.get("postal_code", "").strip()
    postal_suffix = by_type.get("postal_code_suffix", "").strip()
    postal_code = f"{postal}-{postal_suffix}" if postal and postal_suffix else postal

    prefecture = re.sub(r"\s+", "", by_type.get("administrative_area_level_1", "").strip())
    city = re.sub(
        r"\s+",
        "",
        (
            by_type.get("locality", "")
            or by_type.get("administrative_area_level_2", "")
            or by_type.get("sublocality_level_1", "")
        ).strip(),
    )

    detail_parts: list[str] = []
    for key in [
        "sublocality_level_2",
        "sublocality_level_3",
        "sublocality_level_4",
        "sublocality_level_5",
        "route",
        "street_number",
        "premise",
        "subpremise",
    ]:
        val = by_type.get(key, "")
        if val:
            detail_parts.append(val)

    address_detail = trim_address_detail("".join(detail_parts))

    return {
        "postal_code": postal_code,
        "prefecture": prefecture,
        "city": city,
        "address_detail": address_detail,
    }




def normalize_browser_client_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]", "", str(value or "").strip())
    return normalized[:120]


def get_browser_client_id(request: Request) -> str:
    return normalize_browser_client_id(
        request.headers.get("X-Browser-Client-Id", "") or request.query_params.get("client_id", "")
    )


def scope_place_id(place_id: str, browser_client_id: str = "") -> str:
    raw = str(place_id or "").strip()
    if not raw:
        return ""
    client_id = normalize_browser_client_id(browser_client_id)
    prefix = f"{client_id}::"
    if client_id and raw.startswith(prefix):
        return raw
    return f"{prefix}{raw}" if client_id else raw


def get_google_api_key(user: dict[str, Any] | None = None) -> str:
    return os.getenv("GOOGLE_PLACES_API_KEY", "").strip() or os.getenv("GOOGLE_MAPS_API_KEY", "").strip()


def set_env_key(key: str, value: str) -> None:
    env_path = BASE_DIR / ".env"
    existing: list[str] = []
    if env_path.exists():
        existing = env_path.read_text(encoding="utf-8").splitlines()

    updated = False
    out: list[str] = []
    for line in existing:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            updated = True
        else:
            out.append(line)

    if not updated:
        out.append(f"{key}={value}")

    env_path.write_text("\n".join(out).strip() + "\n", encoding="utf-8")
    os.environ[key] = value


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_current_user(request: Request) -> dict[str, Any] | None:
    user_id = request.session.get("user_id")
    if not user_id:
        if is_auth_disabled():
            return get_or_create_demo_user()
        return None
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row:
        return dict(row)
    if is_auth_disabled():
        return get_or_create_demo_user()
    return None


def require_user(request: Request) -> dict[str, Any]:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="ログインが必要です")
    return user


def is_auth_disabled() -> bool:
    return DISABLE_GOOGLE_LOGIN or not is_google_oauth_configured()


def get_or_create_demo_user() -> dict[str, Any]:
    init_db()
    now = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (google_id, email, name, picture, maps_api_key, gmail_access_token, gmail_refresh_token, gmail_token_expiry, created_at, updated_at)
            VALUES (?, ?, ?, ?, '', '', '', '', ?, ?)
            ON CONFLICT(google_id) DO UPDATE SET
                email=excluded.email,
                name=excluded.name,
                updated_at=excluded.updated_at
            """,
            (DEMO_USER_GOOGLE_ID, DEMO_USER_EMAIL, DEMO_USER_NAME, "", now, now),
        )
        row = conn.execute("SELECT * FROM users WHERE google_id = ?", (DEMO_USER_GOOGLE_ID,)).fetchone()
    return dict(row) if row else {}


# FastAPI dependency alias
CurrentUser = Annotated[dict[str, Any], Depends(require_user)]


def validate_my_list_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in MY_LIST_STATUS_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"status は {sorted(MY_LIST_STATUS_VALUES)} のいずれかを指定してください",
        )
    return normalized


def validate_my_list_priority(priority: str) -> str:
    normalized = priority.strip().lower()
    if normalized not in MY_LIST_PRIORITY_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"priority は {sorted(MY_LIST_PRIORITY_VALUES)} のいずれかを指定してください",
        )
    return normalized


def upsert_user(
    google_id: str,
    email: str,
    name: str,
    picture: str,
    access_token: str,
    refresh_token: str,
    token_expiry: str,
) -> dict[str, Any]:
    now = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (google_id, email, name, picture, gmail_access_token, gmail_refresh_token, gmail_token_expiry, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(google_id) DO UPDATE SET
                email=excluded.email,
                name=excluded.name,
                picture=excluded.picture,
                gmail_access_token=CASE WHEN excluded.gmail_access_token <> '' THEN excluded.gmail_access_token ELSE users.gmail_access_token END,
                gmail_refresh_token=CASE WHEN excluded.gmail_refresh_token <> '' THEN excluded.gmail_refresh_token ELSE users.gmail_refresh_token END,
                gmail_token_expiry=CASE WHEN excluded.gmail_token_expiry <> '' THEN excluded.gmail_token_expiry ELSE users.gmail_token_expiry END,
                updated_at=excluded.updated_at
            """,
            (google_id, email, name, picture, access_token, refresh_token, token_expiry, now, now),
        )
        row = conn.execute("SELECT * FROM users WHERE google_id = ?", (google_id,)).fetchone()
    return dict(row)


async def _refresh_gmail_token(refresh_token: str, user_id: int) -> str:
    """Refresh Gmail access token and persist new token to DB."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        data = resp.json()
    new_token = data.get("access_token", "")
    expires_in = int(data.get("expires_in", 3600))
    new_expiry = (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET gmail_access_token=?, gmail_token_expiry=?, updated_at=? WHERE id=?",
            (new_token, new_expiry, now_iso(), user_id),
        )
    return new_token


async def send_via_gmail_api(user: dict[str, Any], to_email: str, subject: str, body: str) -> None:
    """Send an email via Gmail API using the user's OAuth2 token."""
    access_token = user.get("gmail_access_token", "")
    refresh_token = user.get("gmail_refresh_token", "")
    user_id = int(user["id"])

    expiry_str = user.get("gmail_token_expiry", "")
    if expiry_str:
        try:
            expiry = datetime.fromisoformat(expiry_str)
            if datetime.now(UTC) >= expiry - timedelta(minutes=5):
                access_token = await _refresh_gmail_token(refresh_token, user_id)
        except (ValueError, TypeError):
            pass

    if not access_token:
        raise ValueError("Gmailアクセストークンがありません。再ログインしてください。")

    msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = to_email
    msg["From"] = user["email"]
    msg["Subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
        )
        if resp.status_code == 401 and refresh_token:
            access_token = await _refresh_gmail_token(refresh_token, user_id)
            resp = await client.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw},
            )
        resp.raise_for_status()

def normalize_domain(website: str) -> str:
    if not website:
        return ""
    parsed = urlparse(website)
    domain = parsed.netloc.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def normalize_email(value: str) -> str:
    return value.strip().lower()


def is_suppressed(email: str) -> bool:
    if not email:
        return False
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM suppression_list WHERE email = ?", (normalize_email(email),)).fetchone()
    return row is not None


def get_limit_remaining(channel: str) -> int:
    day = datetime.now(UTC).date().isoformat()
    with get_connection() as conn:
        row = conn.execute("SELECT count FROM daily_send_stats WHERE day = ? AND channel = ?", (day, channel)).fetchone()
    used = row[0] if row else 0
    return max(0, DEFAULT_DAILY_SEND_LIMIT - used)


def increment_daily_stats(channel: str, by_count: int = 1) -> None:
    day = datetime.now(UTC).date().isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO daily_send_stats (day, channel, count, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(day, channel) DO UPDATE SET
                count = daily_send_stats.count + excluded.count,
                updated_at = excluded.updated_at
            """,
            (day, channel, by_count, now_iso()),
        )


def log_audit(action: str, target_type: str, target_id: str, details: dict[str, Any], actor: str = "system") -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (action, actor, target_type, target_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (action, actor, target_type, target_id, json.dumps(details, ensure_ascii=False), now_iso()),
        )


def adopt_orphan_leads(user_id: int) -> None:
    """Backfill legacy rows that were created before user_id existed."""
    if not user_id:
        return
    with get_connection() as conn:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if is_auth_disabled() or user_count <= 1:
            conn.execute("UPDATE leads SET user_id = ? WHERE user_id IS NULL", (user_id,))


def is_google_oauth_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID.strip() and GOOGLE_CLIENT_SECRET.strip())


class ContactFormHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self.form_count = 0
        self.form_hints: list[str] = []
        self.text_parts: list[str] = []
        self.title_parts: list[str] = []
        self._current_href = ""
        self._current_link_text: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {str(k).lower(): str(v or "") for k, v in attrs}
        normalized_tag = tag.lower()
        if normalized_tag == "a":
            self._current_href = attr_map.get("href", "")
            self._current_link_text = []
        elif normalized_tag == "form":
            self.form_count += 1
            for key in ("action", "id", "class", "name"):
                value = attr_map.get(key, "").strip()
                if value:
                    self.form_hints.append(value)
        elif normalized_tag in {"input", "textarea", "select", "button", "label"}:
            for key in ("type", "name", "placeholder", "aria-label", "value", "id", "class"):
                value = attr_map.get(key, "").strip()
                if value:
                    self.form_hints.append(value)
        elif normalized_tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "a":
            text = " ".join(self._current_link_text).strip()
            if self._current_href:
                self.links.append({"href": self._current_href, "text": text})
            self._current_href = ""
            self._current_link_text = []
        elif normalized_tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = str(data or "").strip()
        if not text:
            return
        self.text_parts.append(text)
        if self._current_href:
            self._current_link_text.append(text)
        if self._in_title:
            self.title_parts.append(text)

    @property
    def title(self) -> str:
        return " ".join(self.title_parts).strip()

    @property
    def text(self) -> str:
        return " ".join(self.text_parts).strip()


def normalize_website_url(website: str) -> str:
    value = str(website or "").strip()
    if not value:
        return ""
    if not re.match(r"^https?://", value, flags=re.IGNORECASE):
        value = f"https://{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path or ''}"


def is_safe_public_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False
    if hostname in {"localhost", "127.0.0.1", "0.0.0.0"} or hostname.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    except ValueError:
        pass
    return parsed.scheme in {"http", "https"}


def _contains_any_hint(text: str, hints: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(h.lower() in lowered for h in hints)


def extract_candidate_contact_urls(base_url: str, html: str) -> list[str]:
    parser = ContactFormHTMLParser()
    parser.feed(str(html or "")[:300000])

    base_domain = urlparse(base_url).netloc.lower()
    candidates: list[str] = [base_url]
    seen: set[str] = {base_url}

    for path in COMMON_CONTACT_PATHS:
        candidate = urljoin(base_url, path)
        if candidate not in seen and is_safe_public_url(candidate):
            seen.add(candidate)
            candidates.append(candidate)

    for link in parser.links:
        href = str(link.get("href", "")).strip()
        text = str(link.get("text", "")).strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if not (_contains_any_hint(href, CONTACT_PATH_HINTS) or _contains_any_hint(text, CONTACT_TEXT_HINTS)):
            continue
        candidate = urljoin(base_url, href)
        parsed = urlparse(candidate)
        if parsed.netloc.lower() != base_domain:
            continue
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path or ''}"
        if normalized not in seen and is_safe_public_url(normalized):
            seen.add(normalized)
            candidates.append(normalized)

    return candidates[:12]


def analyze_contact_page(url: str, html: str) -> dict[str, Any]:
    parser = ContactFormHTMLParser()
    parser.feed(str(html or "")[:300000])

    path_text = f"{url} {parser.title} {parser.text} {' '.join(parser.form_hints)}"
    positive = 0
    for hint in CONTACT_PATH_HINTS:
        if hint.lower() in str(url).lower():
            positive += 3
    for hint in CONTACT_TEXT_HINTS:
        if hint.lower() in path_text.lower():
            positive += 2
    for hint in FORM_FIELD_HINTS:
        if hint.lower() in path_text.lower():
            positive += 1

    negative = 0
    for hint in NEGATIVE_FORM_HINTS:
        if hint.lower() in path_text.lower():
            negative += 3

    score = positive + (parser.form_count * 4) - negative
    has_contact_form = parser.form_count > 0 and score >= 8
    return {
        "url": url,
        "title": parser.title,
        "score": score,
        "form_count": parser.form_count,
        "has_contact_form": has_contact_form,
    }


async def fetch_html_page(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    if not url or not is_safe_public_url(url):
        return "", url
    try:
        response = await client.get(url, follow_redirects=True)
    except Exception:  # noqa: BLE001
        return "", url

    if getattr(response, "status_code", 500) >= 400:
        return "", str(getattr(response, "url", url))

    headers = getattr(response, "headers", {}) or {}
    content_type = str(headers.get("content-type", "")).lower()
    if content_type and "html" not in content_type:
        return "", str(getattr(response, "url", url))

    return str(getattr(response, "text", "") or "")[:300000], str(getattr(response, "url", url))


async def discover_contact_form_info(client: httpx.AsyncClient, website: str) -> dict[str, Any]:
    base_url = normalize_website_url(website)
    if not base_url:
        return {"form_url": "", "email": "", "source": "heuristic_crawl", "confidence": 0.0, "title": ""}

    home_html, resolved_base = await fetch_html_page(client, base_url)
    if not home_html:
        return {"form_url": "", "email": "", "source": "heuristic_crawl", "confidence": 0.0, "title": ""}

    candidates = extract_candidate_contact_urls(resolved_base, home_html)
    best: dict[str, Any] = {"url": "", "score": 0, "title": ""}
    discovered_email = ""
    visited: set[str] = set()

    for candidate in candidates:
        if candidate in visited:
            continue
        visited.add(candidate)
        html, final_url = await fetch_html_page(client, candidate)
        if not html:
            continue

        if not discovered_email:
            matches = EMAIL_REGEX.findall(html)
            for matched in matches:
                email = str(matched or "").strip()
                if not email:
                    continue
                lowered = email.lower()
                if lowered.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    continue
                discovered_email = email
                break

        analysis = analyze_contact_page(final_url, html)
        if analysis["score"] > best["score"]:
            best = analysis

    if not best.get("has_contact_form"):
        return {
            "form_url": "",
            "email": discovered_email,
            "source": "heuristic_crawl",
            "confidence": 0.0,
            "title": "",
        }

    confidence = min(0.99, max(0.5, float(best["score"]) / 20.0))
    return {
        "form_url": str(best.get("url", "")),
        "email": discovered_email,
        "source": "heuristic_crawl",
        "confidence": confidence,
        "title": str(best.get("title", "")),
    }


async def discover_contact_form_url(client: httpx.AsyncClient, website: str) -> str:
    info = await discover_contact_form_info(client, website)
    return str(info.get("form_url", ""))


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "oauth_configured": is_google_oauth_configured(),
                "oauth_error": request.query_params.get("oauth_error", ""),
            },
        )
    return templates.TemplateResponse("index.html", {"request": request, "user": user, "app_base_url": APP_BASE_URL})


@app.get("/auth/login")
async def auth_login(request: Request) -> RedirectResponse:
    if is_auth_disabled():
        return RedirectResponse("/")
    if not is_google_oauth_configured():
        msg = "Google OAuthが未設定です。GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET を設定してください。"
        return RedirectResponse(url=f"/?oauth_error={quote_plus(msg)}")
    redirect_uri = f"{APP_BASE_URL}/auth/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback")
async def auth_callback(request: Request) -> RedirectResponse:
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"OAuth認証エラー: {exc}") from exc

    user_info = token.get("userinfo") or {}
    google_id = user_info.get("sub", "")
    email = user_info.get("email", "")
    name = user_info.get("name", "")
    picture = user_info.get("picture", "")

    if not google_id or not email:
        raise HTTPException(status_code=400, detail="Googleアカウント情報の取得に失敗しました")

    access_token = token.get("access_token", "")
    refresh_token = token.get("refresh_token", "")
    expires_in = int(token.get("expires_in", 3600))
    token_expiry = (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat()

    init_db()
    user = upsert_user(google_id, email, name, picture, access_token, refresh_token, token_expiry)
    request.session["user_id"] = user["id"]
    log_audit("login", "user", str(user["id"]), {"email": email})
    return RedirectResponse("/")


@app.get("/auth/logout")
def auth_logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/")


@app.get("/api/auth/me")
def auth_me(user: CurrentUser) -> dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "picture": user["picture"],
        "gmail_connected": bool(user.get("gmail_refresh_token") or user.get("gmail_access_token")),
        "maps_key_configured": bool(user.get("maps_api_key")),
    }


@app.get("/api/settings/google-maps-key")
def get_google_maps_key_status(user: CurrentUser) -> dict[str, Any]:
    init_db()
    key = get_google_api_key(user)
    if not key:
        return {"configured": False, "masked": ""}
    return {
        "configured": True,
        "masked": f"{key[:6]}...{key[-4:]}" if len(key) >= 10 else "configured",
    }


@app.post("/api/settings/google-maps-key")
def set_google_maps_key(payload: GoogleMapsKeyRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    key = payload.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="APIキーが空です")
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET maps_api_key=?, updated_at=? WHERE id=?",
            (key, now_iso(), user["id"]),
        )
    log_audit("update_setting", "setting", "google_places_api_key", {"configured": True}, actor=user["email"])
    return {"ok": True}


@app.get("/api/leads")
def get_leads(
    request: Request,
    user: CurrentUser,
    q: str = Query("", description="会社名や住所で検索"),
    prefecture: str = Query("", description="都道府県フィルタ"),
    city: str = Query("", description="市区町村フィルタ"),
    category: str = Query("", description="業種フィルタ"),
    industry: str = Query("", description="業界フィルタ"),
    sort_by: str = Query("updated_at", description="並び替え項目"),
    sort_dir: str = Query("desc", description="並び順 asc/desc"),
) -> dict[str, Any]:
    init_db()
    adopt_orphan_leads(int(user["id"]))
    browser_client_id = get_browser_client_id(request)

    sql = """
        SELECT
            l.*,
            mt.category AS manual_category,
            mt.industry AS manual_industry,
            mt.note AS manual_note,
            COALESCE(mt.category, l.category) AS effective_category,
            COALESCE(mt.industry, l.industry) AS effective_industry
        FROM leads l
        LEFT JOIN manual_tags mt ON mt.lead_id = l.id
        WHERE l.user_id = ? AND COALESCE(l.browser_client_id, '') = ?
    """
    params: list[Any] = [user["id"], browser_client_id]

    normalized_q = q.strip()
    if normalized_q:
        sql += " AND (l.name LIKE ? OR l.address LIKE ? OR l.website LIKE ?)"
        like_q = f"%{normalized_q}%"
        params.extend([like_q, like_q, like_q])
    normalized_prefecture = prefecture.strip()
    normalized_city = city.strip()
    normalized_category = category.strip()
    normalized_industry = industry.strip()

    if normalized_prefecture:
        sql += " AND TRIM(COALESCE(l.prefecture, '')) = ?"
        params.append(normalized_prefecture)
    if normalized_city:
        sql += " AND TRIM(COALESCE(l.city, '')) = ?"
        params.append(normalized_city)
    if normalized_category:
        sql += " AND TRIM(COALESCE(mt.category, l.category)) = ?"
        params.append(normalized_category)
    if normalized_industry:
        sql += " AND TRIM(COALESCE(mt.industry, l.industry)) = ?"
        params.append(normalized_industry)

    allowed_sort_columns = {
        "updated_at": "l.updated_at {dir}, l.id DESC",
        "address": "l.address {dir}, TRIM(COALESCE(l.prefecture, '')) {dir}, TRIM(COALESCE(l.city, '')) {dir}, l.updated_at DESC",
        "prefecture": "TRIM(COALESCE(l.prefecture, '')) {dir}, TRIM(COALESCE(l.city, '')) {dir}, TRIM(COALESCE(l.address_detail, '')) {dir}, l.name {dir}, l.updated_at DESC",
        "city": "TRIM(COALESCE(l.city, '')) {dir}, TRIM(COALESCE(l.prefecture, '')) {dir}, TRIM(COALESCE(l.address_detail, '')) {dir}, l.name {dir}, l.updated_at DESC",
        "name": "l.name {dir}, l.updated_at DESC",
        "category": "COALESCE(mt.category, l.category) {dir}, l.name {dir}, l.updated_at DESC",
        "industry": "COALESCE(mt.industry, l.industry) {dir}, l.name {dir}, l.updated_at DESC",
        "rating": "l.rating {dir}, l.user_ratings_total {dir}, l.name {dir}, l.updated_at DESC",
        "user_ratings_total": "l.user_ratings_total {dir}, l.rating {dir}, l.name {dir}, l.updated_at DESC",
    }

    normalized_dir = sort_dir.strip().lower()
    if normalized_dir not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="sort_dir は asc または desc を指定してください")

    normalized_sort_by = sort_by.strip().lower()
    sort_column = allowed_sort_columns.get(normalized_sort_by)
    if not sort_column:
        raise HTTPException(status_code=400, detail="未対応の sort_by です")

    sql += " ORDER BY " + sort_column.format(dir=normalized_dir.upper())

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
        categories = conn.execute(
            """
            SELECT DISTINCT COALESCE(mt.category, l.category) AS c
            FROM leads l
            LEFT JOIN manual_tags mt ON mt.lead_id = l.id
            WHERE COALESCE(mt.category, l.category) <> '' AND l.user_id = ? AND COALESCE(l.browser_client_id, '') = ?
            ORDER BY c
            """
        , (user["id"], browser_client_id)).fetchall()
        industries = conn.execute(
            """
            SELECT DISTINCT COALESCE(mt.industry, l.industry) AS i
            FROM leads l
            LEFT JOIN manual_tags mt ON mt.lead_id = l.id
            WHERE COALESCE(mt.industry, l.industry) <> '' AND l.user_id = ? AND COALESCE(l.browser_client_id, '') = ?
            ORDER BY i
            """
        , (user["id"], browser_client_id)).fetchall()

    # option_rows: 別接続で取得（address_components_json カラムが存在しない場合も考慮）
    option_rows: list[Any] = []
    try:
        with get_connection() as conn2:
            option_rows = conn2.execute(
                """
                SELECT
                    l.address,
                    l.prefecture,
                    l.city,
                    l.address_components_json
                FROM leads l
                WHERE l.user_id = ? AND COALESCE(l.browser_client_id, '') = ?
                """
            , (user["id"], browser_client_id)).fetchall()
    except Exception:
        # address_components_json カラムが存在しない旧DBの場合はフォールバック
        try:
            with get_connection() as conn3:
                option_rows = conn3.execute(
                    """
                    SELECT l.address, l.prefecture, l.city
                    FROM leads l
                    WHERE l.user_id = ? AND COALESCE(l.browser_client_id, '') = ?
                    """
                , (user["id"], browser_client_id)).fetchall()
        except Exception:
            option_rows = []

    prefecture_set: set[str] = set()
    city_set: set[str] = set()
    for row in option_rows:
        row_address = str(row["address"] or "")
        parsed = split_jp_address(row_address)

        option_components_json = str((row["address_components_json"] if "address_components_json" in row.keys() else "") or "").strip()
        if option_components_json:
            try:
                parsed_components = json.loads(option_components_json)
                if isinstance(parsed_components, list):
                    from_components = parse_address_components(parsed_components)
                    for k, v in from_components.items():
                        if v:
                            parsed[k] = v
            except json.JSONDecodeError:
                pass

        parsed_prefecture = re.sub(r"\s+", "", str(parsed.get("prefecture", "") or "").strip())
        parsed_city = re.sub(r"\s+", "", str(parsed.get("city", "") or "").strip())

        stored_prefecture = re.sub(r"\s+", "", str(row["prefecture"] or "").strip())
        stored_city = re.sub(r"\s+", "", str(row["city"] or "").strip())

        prefecture_value = stored_prefecture or parsed_prefecture
        city_value = stored_city or parsed_city

        if prefecture_value:
            prefecture_set.add(prefecture_value)

        if city_value:
            if not normalized_prefecture or prefecture_value == normalized_prefecture:
                city_set.add(city_value)

    prefectures = sorted(prefecture_set)
    cities = sorted(city_set)

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["suppressed"] = is_suppressed(item.get("email", ""))
        item["address"] = clean_address_text(item.get("address", ""))

        resolved = split_jp_address(item.get("address", ""))
        components_json = item.get("address_components_json", "") or ""
        if components_json:
            try:
                parsed_components = json.loads(components_json)
                if isinstance(parsed_components, list):
                    from_components = parse_address_components(parsed_components)
                    for k, v in from_components.items():
                        if v:
                            resolved[k] = v
            except json.JSONDecodeError:
                pass

        for key in ["postal_code", "prefecture", "city", "address_detail"]:
            stored_value = str(item.get(key, "") or "").strip()
            if not resolved.get(key) and stored_value and stored_value not in {"市", "区", "町", "村"}:
                resolved[key] = stored_value

        resolved["prefecture"] = re.sub(r"\s+", "", str(resolved.get("prefecture", "") or "").strip())
        resolved["city"] = re.sub(r"\s+", "", str(resolved.get("city", "") or "").strip())
        resolved["address_detail"] = trim_address_detail(resolved.get("address_detail", ""), item.get("name", ""))
        item.update(resolved)
        items.append(item)

    return {
        "items": items,
        "filters": {
            "prefectures": prefectures,
            "cities": cities,
            "categories": [r[0] for r in categories],
            "industries": [r[0] for r in industries],
        },
        "sort": {
            "sort_by": normalized_sort_by,
            "sort_dir": normalized_dir,
        },
        "send_limit": {
            "daily_limit": DEFAULT_DAILY_SEND_LIMIT,
            "email_remaining": get_limit_remaining("email"),
            "form_remaining": get_limit_remaining("form"),
        },
    }


@app.get("/api/leads/names")
def get_lead_names(request: Request, user: CurrentUser, limit: int = Query(300, ge=1, le=2000)) -> dict[str, Any]:
    init_db()
    adopt_orphan_leads(int(user["id"]))
    browser_client_id = get_browser_client_id(request)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT name
            FROM leads
            WHERE user_id = ? AND COALESCE(browser_client_id, '') = ? AND name <> ''
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (user["id"], browser_client_id, limit),
        ).fetchall()
    return {"items": [r[0] for r in rows]}


@app.post("/api/import/google-places")
@limiter.limit(lambda: DEFAULT_RATE_LIMIT_PLACES)
async def import_google_places(request: Request, payload: ImportRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    adopt_orphan_leads(int(user["id"]))
    browser_client_id = get_browser_client_id(request)
    api_key = get_google_api_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="Google Places APIキーがサーバーに設定されていません。")

    # ---- 取得件数上限チェック ----
    user_id = int(user["id"])
    daily_used = get_daily_fetch_usage(user_id)
    monthly_used = get_monthly_fetch_usage(user_id)
    daily_remaining = max(0, FETCH_LIMIT_DAILY - daily_used)
    monthly_remaining = max(0, FETCH_LIMIT_MONTHLY - monthly_used)
    if daily_remaining == 0:
        raise HTTPException(
            status_code=429,
            detail=f"本日の取得件数上限（{FETCH_LIMIT_DAILY}件）に達しました。明日以降にお試しください。"
        )
    if monthly_remaining == 0:
        raise HTTPException(
            status_code=429,
            detail=f"今月の取得件数上限（{FETCH_LIMIT_MONTHLY}件）に達しました。来月以降にお試しください。"
        )
    # リクエスト件数を残枠に収める
    effective_max = min(payload.max_results, daily_remaining, monthly_remaining)

    query = payload.query.strip()
    if payload.region.strip():
        query = f"{query} {payload.region.strip()}"

    place_type = payload.place_type.strip().lower()
    if place_type and place_type not in PLACE_TYPE_LABELS:
        raise HTTPException(status_code=400, detail="未対応の業種タイプです")

    items = await fetch_places(
        query=query,
        language=payload.language,
        max_results=effective_max,
        api_key=api_key,
        place_type=place_type,
    )

    # 実際に取得した件数を記録
    record_fetch_usage(user_id, len(items))

    saved = 0
    added = 0
    updated = 0
    for item in items:
        item["place_id"] = scope_place_id(item.get("place_id", ""), browser_client_id)
        item["browser_client_id"] = browser_client_id
        created = upsert_lead(item, user_id=user["id"], browser_client_id=browser_client_id)
        if created:
            added += 1
        else:
            updated += 1
        saved += 1

    log_audit(
        "import_google_places",
        "lead",
        "bulk",
        {"query": query, "place_type": place_type, "saved": saved, "added": added, "updated": updated},
        actor=user["email"],
    )
    return {"imported": saved, "added": added, "updated": updated, "total_fetched": len(items), "items": items}


@app.get("/api/place-types")
def list_place_types(user: CurrentUser) -> dict[str, Any]:
    recommended_set = set(TYPE_PRIORITY)
    items = [
        {
            "value": place_type,
            "label": label,
            "industry": PLACE_INDUSTRY_MAP.get(place_type, "未分類"),
            "recommended": place_type in recommended_set,
        }
        for place_type, label in PLACE_TYPE_LABELS.items()
    ]
    items.sort(key=lambda x: (x["industry"], 0 if x["recommended"] else 1, x["label"]))
    return {"items": items}


@app.post("/api/contact/email")
async def send_email(request: Request, payload: ContactRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    browser_client_id = get_browser_client_id(request)
    if not payload.lead_ids:
        raise HTTPException(status_code=400, detail="対象企業を選択してください")

    remaining = get_limit_remaining("email")
    if remaining <= 0:
        raise HTTPException(status_code=429, detail="本日のメール送信上限に達しました")

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM leads WHERE id = ANY(?) AND user_id = ? AND COALESCE(browser_client_id, '') = ?",
            (payload.lead_ids, user["id"], browser_client_id),
        ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="対象企業が見つかりません")

    # Gmailトークンがあればそちらを優先
    use_gmail = bool(user.get("gmail_refresh_token") or user.get("gmail_access_token"))
    # SMTPフォールバック
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    from_email = user["email"]
    dry_run = not use_gmail and os.getenv("EMAIL_DRY_RUN", "true").lower() == "true"

    sent = 0
    skipped = 0
    limited = 0
    errors = 0

    for row in rows:
        lead = dict(row)

        if sent >= remaining:
            save_contact_log(lead["id"], "email", "daily_limit", payload.subject, "本日の送信上限")
            limited += 1
            continue

        to_email = normalize_email(lead.get("email", ""))
        if not to_email:
            save_contact_log(lead["id"], "email", "skipped", payload.subject, "メールアドレス未登録")
            skipped += 1
            continue

        if is_suppressed(to_email):
            save_contact_log(lead["id"], "email", "suppressed", payload.subject, "配信停止対象")
            skipped += 1
            continue

        rendered_body = render_contact_body_template(payload.body, lead)

        if use_gmail:
            try:
                await send_via_gmail_api(user, to_email, payload.subject, rendered_body)
                save_contact_log(lead["id"], "email", "sent", payload.subject, rendered_body)
                increment_daily_stats("email", 1)
                log_audit("contact_email", "lead", str(lead["id"]), {"status": "sent", "to": to_email, "via": "gmail"}, actor=user["email"])
                sent += 1
            except Exception as exc:  # noqa: BLE001
                save_contact_log(lead["id"], "email", "failed", payload.subject, str(exc))
                log_audit("contact_email", "lead", str(lead["id"]), {"status": "failed", "error": str(exc)}, actor=user["email"])
                errors += 1
            continue

        if dry_run:
            save_contact_log(lead["id"], "email", "dry_run", payload.subject, rendered_body)
            increment_daily_stats("email", 1)
            log_audit("contact_email", "lead", str(lead["id"]), {"status": "dry_run", "to": to_email}, actor=user["email"])
            sent += 1
            continue

        if not smtp_host:
            raise HTTPException(status_code=400, detail="SMTP設定が不足しています。または再ログインしてGmail権限を許可してください。")

        msg = MIMEText(rendered_body, "plain", "utf-8")
        msg["Subject"] = payload.subject
        msg["From"] = from_email
        msg["To"] = to_email

        try:
            with closing(smtplib.SMTP(smtp_host, smtp_port)) as server:
                server.starttls()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(from_email, [to_email], msg.as_string())
            save_contact_log(lead["id"], "email", "sent", payload.subject, rendered_body)
            increment_daily_stats("email", 1)
            log_audit("contact_email", "lead", str(lead["id"]), {"status": "sent", "to": to_email}, actor=user["email"])
            sent += 1
        except Exception as exc:  # noqa: BLE001
            save_contact_log(lead["id"], "email", "failed", payload.subject, str(exc))
            log_audit("contact_email", "lead", str(lead["id"]), {"status": "failed", "error": str(exc)}, actor=user["email"])
            errors += 1

    via = "gmail" if use_gmail else ("dry_run" if dry_run else "smtp")
    return {"sent": sent, "skipped": skipped, "limited": limited, "errors": errors, "via": via}


@app.post("/api/contact/form")
def send_form(request: Request, payload: ContactRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    browser_client_id = get_browser_client_id(request)
    if not payload.lead_ids:
        raise HTTPException(status_code=400, detail="対象企業を選択してください")

    remaining = get_limit_remaining("form")
    if remaining <= 0:
        raise HTTPException(status_code=429, detail="本日のフォーム送信上限に達しました")

    with get_connection() as conn:
        leads = conn.execute(
            "SELECT * FROM leads WHERE id = ANY(?) AND user_id = ? AND COALESCE(browser_client_id, '') = ?",
            (payload.lead_ids, user["id"], browser_client_id),
        ).fetchall()

    dry_run = os.getenv("FORM_DRY_RUN", "true").lower() == "true"
    from_email = user["email"]
    from_name = user.get("name") or os.getenv("CONTACT_FROM_NAME", "Map to List")

    sent = 0
    skipped = 0
    limited = 0

    with get_connection() as conn:
        adapters = conn.execute("SELECT * FROM form_adapters WHERE enabled = 1").fetchall()
    adapter_map = {a["domain"]: dict(a) for a in adapters}

    for row in leads:
        lead = dict(row)
        if sent >= remaining:
            save_contact_log(lead["id"], "form", "daily_limit", payload.subject, "本日の送信上限")
            limited += 1
            continue

        domain = normalize_domain(lead.get("website", ""))
        if not domain or domain not in adapter_map:
            save_contact_log(lead["id"], "form", "no_adapter", payload.subject, "対応アダプタなし")
            skipped += 1
            continue

        if lead.get("email") and is_suppressed(lead.get("email", "")):
            save_contact_log(lead["id"], "form", "suppressed", payload.subject, "配信停止対象")
            skipped += 1
            continue

        adapter = adapter_map[domain]
        payload_template = json.loads(adapter["payload_template"])
        rendered_body = render_contact_body_template(payload.body, lead)
        body = render_form_payload(
            payload_template,
            {
                "company_name": lead.get("name", ""),
                "subject": payload.subject,
                "body": rendered_body,
                "from_name": from_name,
                "from_email": from_email,
                "phone": lead.get("phone", ""),
            },
        )
        target_url = f"https://{adapter['domain']}{adapter['path']}"

        if dry_run:
            save_contact_log(lead["id"], "form", "dry_run", payload.subject, json.dumps(body, ensure_ascii=False))
            increment_daily_stats("form", 1)
            log_audit("contact_form", "lead", str(lead["id"]), {"status": "dry_run", "url": target_url})
            sent += 1
            continue

        try:
            method = adapter["method"].upper()
            with httpx.Client(timeout=20) as client:
                if method == "POST":
                    response = client.post(target_url, data=body)
                else:
                    response = client.get(target_url, params=body)
            if response.status_code >= 400:
                save_contact_log(lead["id"], "form", "failed", payload.subject, f"HTTP {response.status_code}")
                log_audit(
                    "contact_form",
                    "lead",
                    str(lead["id"]),
                    {"status": "failed", "url": target_url, "code": response.status_code},
                )
                continue

            save_contact_log(lead["id"], "form", "sent", payload.subject, target_url)
            increment_daily_stats("form", 1)
            log_audit("contact_form", "lead", str(lead["id"]), {"status": "sent", "url": target_url})
            sent += 1
        except Exception as exc:  # noqa: BLE001
            save_contact_log(lead["id"], "form", "failed", payload.subject, str(exc))
            log_audit("contact_form", "lead", str(lead["id"]), {"status": "failed", "error": str(exc)})

    return {"sent": sent, "skipped": skipped, "limited": limited, "dry_run": dry_run, "adapters": len(adapter_map)}


@app.get("/api/form-adapters")
def list_form_adapters(user: CurrentUser) -> dict[str, Any]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM form_adapters ORDER BY updated_at DESC").fetchall()
    return {"items": [dict(r) for r in rows]}


@app.get("/api/contact-forms")
def list_contact_forms(request: Request, user: CurrentUser) -> dict[str, Any]:
    init_db()
    browser_client_id = get_browser_client_id(request)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                d.id,
                d.lead_id,
                l.name AS lead_name,
                d.website,
                d.form_url,
                d.email,
                d.source,
                d.confidence,
                d.checked_at
            FROM contact_form_discoveries d
            JOIN leads l ON l.id = d.lead_id
            WHERE d.user_id = ? AND COALESCE(d.browser_client_id, '') = ? AND (d.form_url <> '' OR d.email <> '')
            ORDER BY d.checked_at DESC, l.name ASC
            """,
            (user["id"], browser_client_id),
        ).fetchall()
    return {"items": [dict(r) for r in rows], "count": len(rows)}


@app.post("/api/contact-forms/discover")
async def discover_contact_forms(request: Request, payload: LeadSelectionRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    browser_client_id = get_browser_client_id(request)
    if not payload.lead_ids:
        raise HTTPException(status_code=400, detail="対象企業を選択してください")

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, website FROM leads WHERE id = ANY(?) AND user_id = ? AND COALESCE(browser_client_id, '') = ?",
            (payload.lead_ids, user["id"], browser_client_id),
        ).fetchall()

    leads = [dict(r) for r in rows]
    if not leads:
        raise HTTPException(status_code=404, detail="対象企業が見つかりません")

    semaphore = asyncio.Semaphore(5)

    async def inspect_lead(lead: dict[str, Any]) -> dict[str, Any] | None:
        website = normalize_website_url(lead.get("website", ""))
        if not website:
            return None
        async with semaphore:
            info = await discover_contact_form_info(client, website)
        form_url = str(info.get("form_url", "")).strip()
        email = str(info.get("email", "")).strip()
        if not form_url and not email:
            return None
        return {
            "lead_id": int(lead["id"]),
            "lead_name": str(lead.get("name", "")),
            "website": website,
            "form_url": form_url,
            "email": email,
            "source": str(info.get("source", "heuristic_crawl")),
            "confidence": float(info.get("confidence", 0.0)),
            "checked_at": now_iso(),
        }

    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(*(inspect_lead(lead) for lead in leads))

    found_items = [item for item in results if item]
    found_by_lead = {int(item["lead_id"]): item for item in found_items}
    now = now_iso()

    with get_connection() as conn:
        for lead in leads:
            lead_id = int(lead["id"])
            item = found_by_lead.get(lead_id)
            if not item:
                conn.execute(
                    "DELETE FROM contact_form_discoveries WHERE user_id = ? AND lead_id = ? AND COALESCE(browser_client_id, '') = ?",
                    (user["id"], lead_id, browser_client_id),
                )
                continue

            conn.execute(
                """
                INSERT INTO contact_form_discoveries (user_id, lead_id, website, form_url, email, browser_client_id, source, confidence, checked_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, lead_id) DO UPDATE SET
                    website=excluded.website,
                    form_url=excluded.form_url,
                    email=excluded.email,
                    browser_client_id=excluded.browser_client_id,
                    source=excluded.source,
                    confidence=excluded.confidence,
                    checked_at=excluded.checked_at,
                    updated_at=excluded.updated_at
                """,
                (
                    user["id"],
                    item["lead_id"],
                    item["website"],
                    item["form_url"],
                    item["email"],
                    browser_client_id,
                    item["source"],
                    item["confidence"],
                    item["checked_at"],
                    now,
                    now,
                ),
            )

    log_audit(
        "discover_contact_forms",
        "lead",
        "bulk",
        {"lead_ids": payload.lead_ids, "checked": len(leads), "found": len(found_items)},
        actor=user["email"],
    )

    return {
        "checked": len(leads),
        "found": len(found_items),
        "items": found_items,
        "method": "heuristic_crawl",
    }


@app.post("/api/form-adapters")
def create_form_adapter(payload: FormAdapterRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    domain = normalize_domain(payload.domain if payload.domain.startswith("http") else f"https://{payload.domain}")
    if not domain:
        raise HTTPException(status_code=400, detail="domain が不正です")

    now = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO form_adapters (name, domain, path, method, payload_template, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                name=excluded.name,
                path=excluded.path,
                method=excluded.method,
                payload_template=excluded.payload_template,
                enabled=excluded.enabled,
                updated_at=excluded.updated_at
            """,
            (
                payload.name,
                domain,
                payload.path,
                payload.method.upper(),
                json.dumps(payload.payload_template, ensure_ascii=False),
                1 if payload.enabled else 0,
                now,
                now,
            ),
        )
    log_audit("upsert_form_adapter", "adapter", domain, {"name": payload.name})
    return {"ok": True, "domain": domain}


@app.get("/api/suppressions")
def list_suppressions(user: CurrentUser) -> dict[str, Any]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM suppression_list ORDER BY created_at DESC").fetchall()
    return {"items": [dict(r) for r in rows]}


@app.post("/api/suppressions")
def add_suppression(payload: SuppressionRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    email = normalize_email(payload.email)
    if not EMAIL_REGEX.fullmatch(email):
        raise HTTPException(status_code=400, detail="有効なメールアドレスを入力してください")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO suppression_list (email, reason, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                reason=excluded.reason,
                created_at=excluded.created_at
            """,
            (email, payload.reason, now_iso()),
        )
    log_audit("add_suppression", "email", email, {"reason": payload.reason})
    return {"ok": True, "email": email}


@app.delete("/api/suppressions/{email}")
def remove_suppression(email: str, user: CurrentUser) -> dict[str, Any]:
    init_db()
    normalized = normalize_email(email)
    with get_connection() as conn:
        conn.execute("DELETE FROM suppression_list WHERE email = ?", (normalized,))
    log_audit("remove_suppression", "email", normalized, {})
    return {"ok": True}


@app.post("/api/leads/tags/bulk")
def update_manual_tags(payload: BulkTagRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    if not payload.lead_ids:
        raise HTTPException(status_code=400, detail="対象企業を選択してください")

    with get_connection() as conn:
        for lead_id in payload.lead_ids:
            conn.execute(
                """
                INSERT INTO manual_tags (lead_id, category, industry, note, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(lead_id) DO UPDATE SET
                    category=excluded.category,
                    industry=excluded.industry,
                    note=excluded.note,
                    updated_at=excluded.updated_at
                """,
                (lead_id, payload.category, payload.industry, payload.note, now_iso()),
            )
            log_audit(
                "update_manual_tag",
                "lead",
                str(lead_id),
                {"category": payload.category, "industry": payload.industry, "note": payload.note},
            )

    return {"updated": len(payload.lead_ids)}


@app.get("/api/audit-logs")
def get_audit_logs(user: CurrentUser, limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return {"items": [dict(r) for r in rows]}


async def fetch_places(
    query: str,
    language: str,
    max_results: int,
    api_key: str,
    place_type: str = "",
) -> list[dict[str, Any]]:
    search_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    details_url = "https://maps.googleapis.com/maps/api/place/details/json"

    places: list[dict[str, Any]] = []
    next_page_token = ""
    next_page_attempts = 0
    seen_place_ids: set[str] = set()

    async with httpx.AsyncClient(timeout=20) as client:
        while len(places) < max_results:
            params = {
                "query": query,
                "language": language,
                "key": api_key,
            }
            if place_type and not next_page_token:
                params["type"] = place_type
            if next_page_token:
                await asyncio.sleep(2)
                params = {"pagetoken": next_page_token, "key": api_key}

            response = await client.get(search_url, params=params)
            response.raise_for_status()
            data = response.json()
            status = str(data.get("status", "OK")).upper()

            if status == "INVALID_REQUEST" and next_page_token:
                next_page_attempts += 1
                if next_page_attempts < 4:
                    continue
                raise HTTPException(
                    status_code=502,
                    detail="Google Places の次ページ取得に失敗しました。少し待って再試行してください。",
                )

            if status not in {"OK", "ZERO_RESULTS"}:
                detail = data.get("error_message") or status
                raise HTTPException(status_code=502, detail=f"Google Places API error: {detail}")

            next_page_attempts = 0
            results = data.get("results", [])
            for place in results:
                place_id = str(place.get("place_id", "")).strip()
                if not place_id or place_id in seen_place_ids:
                    continue
                seen_place_ids.add(place_id)

                detail_data: dict[str, Any] = {}
                address_components: list[dict[str, Any]] = []
                website = ""
                phone = ""
                rating = place.get("rating")
                user_ratings_total = place.get("user_ratings_total")
                raw_type_values = place.get("types", [])

                detail_params = {
                    "place_id": place_id,
                    "fields": "name,website,formatted_phone_number,formatted_address,address_components,types,rating,user_ratings_total",
                    "language": language,
                    "key": api_key,
                }

                for attempt in range(3):
                    try:
                        detail_resp = await client.get(details_url, params=detail_params)
                        detail_resp.raise_for_status()
                        detail_payload = detail_resp.json()
                        detail_status = str(detail_payload.get("status", "OK")).upper()

                        if detail_status in {"OK", ""}:
                            detail_data = detail_payload.get("result", {}) or {}
                            break

                        if detail_status in {"OVER_QUERY_LIMIT", "UNKNOWN_ERROR"} and attempt < 2:
                            await asyncio.sleep(1 + attempt)
                            continue
                        break
                    except Exception:
                        if attempt < 2:
                            await asyncio.sleep(1 + attempt)
                            continue
                        break

                if detail_data:
                    website = str(detail_data.get("website", "") or "").strip()
                    phone = str(detail_data.get("formatted_phone_number", "") or "").strip()
                    rating = detail_data.get("rating", rating)
                    user_ratings_total = detail_data.get("user_ratings_total", user_ratings_total)
                    raw_type_values = detail_data.get("types", raw_type_values)
                    address_components = detail_data.get("address_components", [])
                    if not isinstance(address_components, list):
                        address_components = []

                detail_types = [t.strip().lower() for t in raw_type_values if t and str(t).strip()]
                if place_type and place_type not in detail_types:
                    continue

                category, industry = classify_business(detail_types, place.get("name", ""), website)
                address = clean_address_text(detail_data.get("formatted_address") or place.get("formatted_address", ""))
                address_parts = parse_address_components(address_components)
                if not any(address_parts.values()):
                    address_parts = split_jp_address(address)
                address_parts["address_detail"] = trim_address_detail(address_parts.get("address_detail", ""), place.get("name", ""))

                places.append(
                    {
                        "name": detail_data.get("name") or place.get("name", ""),
                        "place_id": place_id,
                        "website": website,
                        "phone": phone,
                        "address": address,
                        "rating": rating,
                        "user_ratings_total": user_ratings_total,
                        "raw_types": ",".join(detail_types),
                        "category": category,
                        "industry": industry,
                        "postal_code": address_parts.get("postal_code", ""),
                        "prefecture": address_parts.get("prefecture", ""),
                        "city": address_parts.get("city", ""),
                        "address_detail": address_parts.get("address_detail", ""),
                        "address_components_json": json.dumps(address_components, ensure_ascii=False),
                    }
                )
                if len(places) >= max_results:
                    break

            next_page_token = str(data.get("next_page_token", "")).strip()
            if not next_page_token:
                break

    return places[:max_results]


def classify_business(types: list[str], name: str, website: str = "") -> tuple[str, str]:
    normalized_types = [t.strip().lower() for t in types if t and t.strip()]
    unique_types: list[str] = list(dict.fromkeys(normalized_types))
    tset = set(unique_types)

    category_type = ""
    for t in TYPE_PRIORITY:
        if t in tset:
            category_type = t
            break
    if not category_type and unique_types:
        category_type = unique_types[0]

    category = PLACE_TYPE_LABELS.get(category_type, humanize_place_type(category_type)) if category_type else "その他"

    industry = "未分類"
    for t in unique_types:
        if t in PLACE_INDUSTRY_MAP:
            industry = PLACE_INDUSTRY_MAP[t]
            break

    # Places typeが付かないケース向けの最小フォールバック
    text = f"{name} {website}".lower()
    if industry == "未分類":
        if "行政書士" in text:
            return "行政書士", "専門サービス"
        if "工務店" in text or "施工" in text:
            return "工務店", "建設・不動産"

    return category, industry


def humanize_place_type(type_name: str) -> str:
    if not type_name:
        return "その他"
    return type_name.replace("_", " ").title()


def render_form_payload(payload_template: Any, vars_map: dict[str, str]) -> Any:
    if isinstance(payload_template, dict):
        return {k: render_form_payload(v, vars_map) for k, v in payload_template.items()}
    if isinstance(payload_template, list):
        return [render_form_payload(v, vars_map) for v in payload_template]
    if isinstance(payload_template, str):
        out = payload_template
        for key, value in vars_map.items():
            out = out.replace(f"{{{{{key}}}}}", value)
        return out
    return payload_template


def render_contact_body_template(body: str, lead: dict[str, Any]) -> str:
    vars_map = {
        "company_name": str(lead.get("name", "")),
        "company_address": str(lead.get("address", "")),
        "company_phone": str(lead.get("phone", "")),
        "company_website": str(lead.get("website", "")),
    }
    out = body
    for key, value in vars_map.items():
        out = out.replace(f"{{{{{key}}}}}", value)
    return out


def upsert_lead(item: dict[str, Any], user_id: int | None = None, browser_client_id: str = "") -> bool:
    now = now_iso()
    scoped_place_id = scope_place_id(item.get("place_id", ""), browser_client_id or item.get("browser_client_id", ""))
    normalized_client_id = normalize_browser_client_id(browser_client_id or item.get("browser_client_id", ""))
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM leads WHERE place_id = ?",
            (scoped_place_id,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO leads (name, place_id, website, phone, email, address, category, industry, rating, user_ratings_total, raw_types, postal_code, prefecture, city, address_detail, address_components_json, user_id, browser_client_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(place_id) DO UPDATE SET
                name=CASE WHEN TRIM(COALESCE(excluded.name, '')) <> '' THEN excluded.name ELSE leads.name END,
                website=CASE WHEN TRIM(COALESCE(excluded.website, '')) <> '' THEN excluded.website ELSE leads.website END,
                phone=CASE WHEN TRIM(COALESCE(excluded.phone, '')) <> '' THEN excluded.phone ELSE leads.phone END,
                email=CASE WHEN TRIM(COALESCE(excluded.email, '')) <> '' THEN excluded.email ELSE leads.email END,
                address=CASE WHEN TRIM(COALESCE(excluded.address, '')) <> '' THEN excluded.address ELSE leads.address END,
                category=CASE WHEN TRIM(COALESCE(excluded.category, '')) <> '' THEN excluded.category ELSE leads.category END,
                industry=CASE WHEN TRIM(COALESCE(excluded.industry, '')) <> '' THEN excluded.industry ELSE leads.industry END,
                rating=COALESCE(excluded.rating, leads.rating),
                user_ratings_total=COALESCE(excluded.user_ratings_total, leads.user_ratings_total),
                raw_types=CASE WHEN TRIM(COALESCE(excluded.raw_types, '')) <> '' THEN excluded.raw_types ELSE leads.raw_types END,
                postal_code=CASE WHEN TRIM(COALESCE(excluded.postal_code, '')) <> '' THEN excluded.postal_code ELSE leads.postal_code END,
                prefecture=CASE WHEN TRIM(COALESCE(excluded.prefecture, '')) <> '' THEN excluded.prefecture ELSE leads.prefecture END,
                city=CASE WHEN TRIM(COALESCE(excluded.city, '')) <> '' THEN excluded.city ELSE leads.city END,
                address_detail=CASE WHEN TRIM(COALESCE(excluded.address_detail, '')) <> '' THEN excluded.address_detail ELSE leads.address_detail END,
                address_components_json=CASE WHEN TRIM(COALESCE(excluded.address_components_json, '')) <> '' THEN excluded.address_components_json ELSE leads.address_components_json END,
                user_id=COALESCE(excluded.user_id, leads.user_id),
                browser_client_id=CASE WHEN TRIM(COALESCE(excluded.browser_client_id, '')) <> '' THEN excluded.browser_client_id ELSE leads.browser_client_id END,
                updated_at=excluded.updated_at
            """,
            (
                item.get("name", ""),
                scoped_place_id,
                item.get("website", ""),
                item.get("phone", ""),
                normalize_email(item.get("email", "")) if item.get("email") else "",
                item.get("address", ""),
                item.get("category", ""),
                item.get("industry", ""),
                item.get("rating"),
                item.get("user_ratings_total"),
                item.get("raw_types", ""),
                item.get("postal_code", ""),
                item.get("prefecture", ""),
                item.get("city", ""),
                item.get("address_detail", ""),
                item.get("address_components_json", ""),
                user_id,
                normalized_client_id,
                now,
                now,
            ),
        )
    return existing is None


def save_contact_log(lead_id: int, channel: str, status: str, subject: str, message: str) -> None:
    created_at = now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO contact_logs (lead_id, channel, status, subject, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (lead_id, channel, status, subject, message, created_at),
        )
        conn.execute(
            """
            UPDATE my_list_items
            SET
                contact_count = COALESCE(contact_count, 0) + 1,
                last_contacted_at = ?,
                updated_at = ?
            WHERE lead_id = ?
            """,
            (created_at, created_at, lead_id),
        )


@app.get("/api/my-list")
def get_my_list(
    request: Request,
    user: CurrentUser,
    q: str = Query("", description="会社名や住所で検索"),
    status: str = Query("", description="マイリスト状態フィルタ"),
    priority: str = Query("", description="優先度フィルタ"),
    sort_by: str = Query("updated_at", description="並び替え項目"),
    sort_dir: str = Query("desc", description="並び順 asc/desc"),
) -> dict[str, Any]:
    init_db()
    browser_client_id = get_browser_client_id(request)

    sql = """
        SELECT
            m.id,
            m.user_id,
            m.lead_id,
            m.status,
            m.priority,
            m.owner_name,
            m.note,
            m.added_at,
            m.updated_at,
            m.last_contacted_at,
            m.contact_count,
            l.name,
            l.website,
            l.phone,
            l.email,
            l.address,
            COALESCE(mt.category, l.category) AS effective_category,
            COALESCE(mt.industry, l.industry) AS effective_industry
        FROM my_list_items m
        JOIN leads l ON l.id = m.lead_id
        LEFT JOIN manual_tags mt ON mt.lead_id = l.id
        WHERE m.user_id = ? AND COALESCE(l.browser_client_id, '') = ?
    """
    params: list[Any] = [user["id"], browser_client_id]

    if q:
        like_q = f"%{q}%"
        sql += " AND (l.name LIKE ? OR l.address LIKE ? OR l.website LIKE ?)"
        params.extend([like_q, like_q, like_q])
    if status:
        sql += " AND m.status = ?"
        params.append(status)
    if priority:
        sql += " AND m.priority = ?"
        params.append(priority)

    allowed_sort_columns = {
        "updated_at": "m.updated_at",
        "added_at": "m.added_at",
        "last_contacted_at": "m.last_contacted_at",
        "contact_count": "m.contact_count",
        "name": "l.name",
    }

    normalized_dir = sort_dir.strip().lower()
    if normalized_dir not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="sort_dir は asc または desc を指定してください")

    normalized_sort_by = sort_by.strip().lower()
    if normalized_sort_by == "priority":
        sql += (
            " ORDER BY "
            "CASE m.priority "
            "WHEN 'high' THEN 1 "
            "WHEN 'medium' THEN 2 "
            "WHEN 'low' THEN 3 "
            "ELSE 99 END "
            f"{normalized_dir}, m.updated_at DESC"
        )
    else:
        sort_column = allowed_sort_columns.get(normalized_sort_by)
        if not sort_column:
            raise HTTPException(status_code=400, detail="未対応の sort_by です")
        sql += f" ORDER BY {sort_column} {normalized_dir}, m.updated_at DESC"

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

        statuses = conn.execute(
            """
            SELECT DISTINCT m.status
            FROM my_list_items m
            JOIN leads l ON l.id = m.lead_id
            WHERE m.user_id = ? AND COALESCE(l.browser_client_id, '') = ?
            ORDER BY m.status
            """,
            (user["id"], browser_client_id),
        ).fetchall()
        priorities = conn.execute(
            """
            SELECT DISTINCT m.priority
            FROM my_list_items m
            JOIN leads l ON l.id = m.lead_id
            WHERE m.user_id = ? AND COALESCE(l.browser_client_id, '') = ?
            ORDER BY m.priority
            """,
            (user["id"], browser_client_id),
        ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "filters": {
            "statuses": [r[0] for r in statuses],
            "priorities": [r[0] for r in priorities],
        },
        "sort": {
            "sort_by": normalized_sort_by,
            "sort_dir": normalized_dir,
        },
    }


@app.post("/api/my-list")
def add_to_my_list(request: Request, payload: MyListBulkAddRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    browser_client_id = get_browser_client_id(request)
    if not payload.lead_ids:
        raise HTTPException(status_code=400, detail="対象企業を選択してください")

    status_value = validate_my_list_status(payload.status)
    priority_value = validate_my_list_priority(payload.priority)

    now = now_iso()
    added = 0
    updated = 0

    with get_connection() as conn:
        existing_rows = conn.execute(
            "SELECT id FROM leads WHERE id = ANY(?) AND user_id = ? AND COALESCE(browser_client_id, '') = ?",
            (payload.lead_ids, user["id"], browser_client_id),
        ).fetchall()
        valid_lead_ids = [int(r["id"]) for r in existing_rows]

        if not valid_lead_ids:
            raise HTTPException(status_code=404, detail="対象企業が見つかりません")

        for lead_id in valid_lead_ids:
            row = conn.execute(
                "SELECT id FROM my_list_items WHERE user_id = ? AND lead_id = ?",
                (user["id"], lead_id),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE my_list_items
                    SET status = ?, priority = ?, note = ?, updated_at = ?
                    WHERE user_id = ? AND lead_id = ?
                    """,
                    (status_value, priority_value, payload.note, now, user["id"], lead_id),
                )
                updated += 1
                continue

            conn.execute(
                """
                INSERT INTO my_list_items (user_id, lead_id, status, priority, owner_name, note, added_at, updated_at, last_contacted_at, contact_count)
                VALUES (?, ?, ?, ?, '', ?, ?, ?, NULL, 0)
                """,
                (user["id"], lead_id, status_value, priority_value, payload.note, now, now),
            )
            added += 1

    log_audit(
        "add_my_list",
        "lead",
        "bulk",
        {
            "lead_ids": payload.lead_ids,
            "added": added,
            "updated": updated,
            "status": status_value,
            "priority": priority_value,
        },
        actor=user["email"],
    )
    return {"added": added, "updated": updated, "total": added + updated}


@app.patch("/api/my-list/{item_id}")
def update_my_list_item(item_id: int, payload: MyListUpdateRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    updates: list[str] = []
    params: list[Any] = []

    if payload.status is not None:
        updates.append("status = ?")
        params.append(validate_my_list_status(payload.status))
    if payload.priority is not None:
        updates.append("priority = ?")
        params.append(validate_my_list_priority(payload.priority))
    if payload.note is not None:
        updates.append("note = ?")
        params.append(payload.note)
    if payload.owner_name is not None:
        updates.append("owner_name = ?")
        params.append(payload.owner_name)

    if not updates:
        raise HTTPException(status_code=400, detail="更新項目がありません")

    updates.append("updated_at = ?")
    params.append(now_iso())
    params.extend([item_id, user["id"]])

    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE my_list_items SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
            params,
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="マイリスト項目が見つかりません")

    log_audit(
        "update_my_list",
        "my_list_item",
        str(item_id),
        {
            "status": payload.status,
            "priority": payload.priority,
            "note": payload.note,
            "owner_name": payload.owner_name,
        },
        actor=user["email"],
    )
    return {"ok": True, "id": item_id}


@app.delete("/api/my-list/{item_id}")
def remove_my_list_item(item_id: int, user: CurrentUser) -> dict[str, Any]:
    init_db()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM my_list_items WHERE id = ? AND user_id = ?", (item_id, user["id"]))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="マイリスト項目が見つかりません")

    log_audit("remove_my_list", "my_list_item", str(item_id), {}, actor=user["email"])
    return {"ok": True, "id": item_id}


@app.get("/api/contact-logs")
def get_contact_logs(
    request: Request,
    user: CurrentUser,
    lead_id: int | None = Query(None),
    q: str = Query("", description="企業名・件名・本文検索"),
    from_date: str = Query("", description="開始日(YYYY-MM-DD)"),
    to_date: str = Query("", description="終了日(YYYY-MM-DD)"),
    channel: str = Query(""),
    status: str = Query(""),
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    init_db()
    browser_client_id = get_browser_client_id(request)

    sql = """
        SELECT
            c.id,
            c.lead_id,
            c.channel,
            c.status,
            c.subject,
            c.message,
            c.created_at,
            l.name AS lead_name,
            l.email AS lead_email,
            l.website AS lead_website
        FROM contact_logs c
        JOIN leads l ON l.id = c.lead_id
        WHERE l.user_id = ? AND COALESCE(l.browser_client_id, '') = ?
    """
    params: list[Any] = [user["id"], browser_client_id]

    if lead_id is not None:
        sql += " AND c.lead_id = ?"
        params.append(lead_id)
    if q:
        like_q = f"%{q}%"
        sql += " AND (l.name LIKE ? OR c.subject LIKE ? OR c.message LIKE ?)"
        params.extend([like_q, like_q, like_q])
    if from_date:
        sql += " AND c.created_at >= ?"
        params.append(f"{from_date}T00:00:00+00:00")
    if to_date:
        sql += " AND c.created_at <= ?"
        params.append(f"{to_date}T23:59:59.999999+00:00")
    if channel:
        sql += " AND c.channel = ?"
        params.append(channel)
    if status:
        sql += " AND c.status = ?"
        params.append(status)

    sql += " ORDER BY c.created_at DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return {"items": [dict(r) for r in rows]}


@app.get("/api/leads/{lead_id}/timeline")
def get_lead_timeline(lead_id: int, request: Request, user: CurrentUser, limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
    init_db()
    browser_client_id = get_browser_client_id(request)
    with get_connection() as conn:
        lead = conn.execute("SELECT * FROM leads WHERE id = ? AND user_id = ? AND COALESCE(browser_client_id, '') = ?", (lead_id, user["id"], browser_client_id)).fetchone()
        if not lead:
            raise HTTPException(status_code=404, detail="企業が見つかりません")

        logs = conn.execute(
            """
            SELECT id, lead_id, channel, status, subject, message, created_at
            FROM contact_logs
            WHERE lead_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (lead_id, limit),
        ).fetchall()

    return {
        "lead": {
            "id": lead["id"],
            "name": lead["name"],
            "email": lead["email"],
            "website": lead["website"],
        },
        "items": [dict(r) for r in logs],
    }
