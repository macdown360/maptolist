import base64
import json
import os
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote_plus, urlparse
import smtplib

import httpx
from authlib.integrations.starlette_client import OAuth
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "autosales.db"
load_dotenv(BASE_DIR / ".env")
EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
DEFAULT_DAILY_SEND_LIMIT = int(os.getenv("DAILY_SEND_LIMIT", "100"))
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_hex(32))
DISABLE_GOOGLE_LOGIN = os.getenv("DISABLE_GOOGLE_LOGIN", "false").lower() == "true"
DEMO_USER_GOOGLE_ID = "local-demo-user"
DEMO_USER_EMAIL = "demo@local"
DEMO_USER_NAME = "Demo User"
MY_LIST_STATUS_VALUES = {"new", "contacted", "nurturing", "closed", "excluded"}
MY_LIST_PRIORITY_VALUES = {"high", "medium", "low"}

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

app = FastAPI(title="AutoSales Lead Collector", version="0.3.0")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=86400 * 30, https_only=False)
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
    max_results: int = Field(20, ge=1, le=60, description="取得件数上限")


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
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                place_id TEXT UNIQUE,
                website TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                category TEXT,
                industry TEXT,
                rating REAL,
                user_ratings_total INTEGER,
                editorial_summary TEXT,
                raw_types TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        # Backward compatible migrations for existing DB files.
        safe_add_column(conn, "leads", "rating REAL")
        safe_add_column(conn, "leads", "user_ratings_total INTEGER")
        safe_add_column(conn, "leads", "editorial_summary TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contact_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_send_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        safe_add_column(conn, "leads", "user_id INTEGER")


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def safe_add_column(conn: sqlite3.Connection, table: str, column_def: str) -> None:
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def get_google_api_key(user: dict[str, Any] | None = None) -> str:
    if user and user.get("maps_api_key"):
        return str(user["maps_api_key"]).strip()
    return os.getenv("GOOGLE_MAPS_API_KEY", "").strip()


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
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
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
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
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
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
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
    with sqlite3.connect(DB_PATH) as conn:
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
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT 1 FROM suppression_list WHERE email = ?", (normalize_email(email),)).fetchone()
    return row is not None


def get_limit_remaining(channel: str) -> int:
    day = datetime.now(UTC).date().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT count FROM daily_send_stats WHERE day = ? AND channel = ?", (day, channel)).fetchone()
    used = row[0] if row else 0
    return max(0, DEFAULT_DAILY_SEND_LIMIT - used)


def increment_daily_stats(channel: str, by_count: int = 1) -> None:
    day = datetime.now(UTC).date().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
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
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (action, actor, target_type, target_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (action, actor, target_type, target_id, json.dumps(details, ensure_ascii=False), now_iso()),
        )


def is_google_oauth_configured() -> bool:
    return bool(GOOGLE_CLIENT_ID.strip() and GOOGLE_CLIENT_SECRET.strip())


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
    return templates.TemplateResponse("index.html", {"request": request, "user": user})


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
    key = get_google_api_key()
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
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE users SET maps_api_key=?, updated_at=? WHERE id=?",
            (key, now_iso(), user["id"]),
        )
    log_audit("update_setting", "setting", "google_maps_api_key", {"configured": True}, actor=user["email"])
    return {"ok": True}


@app.get("/api/leads")
def get_leads(
    user: CurrentUser,
    q: str = Query("", description="会社名や住所で検索"),
    category: str = Query("", description="業種フィルタ"),
    industry: str = Query("", description="業界フィルタ"),
) -> dict[str, Any]:
    init_db()

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
        WHERE l.user_id = ?
    """
    params: list[Any] = [user["id"]]

    if q:
        sql += " AND (l.name LIKE ? OR l.address LIKE ? OR l.website LIKE ?)"
        like_q = f"%{q}%"
        params.extend([like_q, like_q, like_q])
    if category:
        sql += " AND COALESCE(mt.category, l.category) = ?"
        params.append(category)
    if industry:
        sql += " AND COALESCE(mt.industry, l.industry) = ?"
        params.append(industry)

    sql += " ORDER BY l.updated_at DESC"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        categories = conn.execute(
            """
            SELECT DISTINCT COALESCE(mt.category, l.category) AS c
            FROM leads l
            LEFT JOIN manual_tags mt ON mt.lead_id = l.id
            WHERE COALESCE(mt.category, l.category) <> '' AND l.user_id = ?
            ORDER BY c
            """
        , (user["id"],)).fetchall()
        industries = conn.execute(
            """
            SELECT DISTINCT COALESCE(mt.industry, l.industry) AS i
            FROM leads l
            LEFT JOIN manual_tags mt ON mt.lead_id = l.id
            WHERE COALESCE(mt.industry, l.industry) <> '' AND l.user_id = ?
            ORDER BY i
            """
        , (user["id"],)).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["suppressed"] = is_suppressed(item.get("email", ""))
        items.append(item)

    return {
        "items": items,
        "filters": {
            "categories": [r[0] for r in categories],
            "industries": [r[0] for r in industries],
        },
        "send_limit": {
            "daily_limit": DEFAULT_DAILY_SEND_LIMIT,
            "email_remaining": get_limit_remaining("email"),
            "form_remaining": get_limit_remaining("form"),
        },
    }


@app.get("/api/leads/names")
def get_lead_names(user: CurrentUser, limit: int = Query(300, ge=1, le=2000)) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT name
            FROM leads
            WHERE user_id = ? AND name <> ''
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (user["id"], limit),
        ).fetchall()
    return {"items": [r[0] for r in rows]}


@app.post("/api/import/google-places")
async def import_google_places(payload: ImportRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    api_key = get_google_api_key(user)
    if not api_key:
        raise HTTPException(status_code=400, detail="Google Maps APIキーが未設定です。設定画面で登録してください。")

    query = payload.query.strip()
    if payload.region.strip():
        query = f"{query} {payload.region.strip()}"

    place_type = payload.place_type.strip().lower()
    if place_type and place_type not in PLACE_TYPE_LABELS:
        raise HTTPException(status_code=400, detail="未対応の業種タイプです")

    items = await fetch_places(
        query=query,
        language=payload.language,
        max_results=payload.max_results,
        api_key=api_key,
        place_type=place_type,
    )
    saved = 0
    for item in items:
        upsert_lead(item, user_id=user["id"])
        saved += 1

    log_audit(
        "import_google_places",
        "lead",
        "bulk",
        {"query": query, "place_type": place_type, "saved": saved},
        actor=user["email"],
    )
    return {"imported": saved, "total_fetched": len(items)}


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
async def send_email(payload: ContactRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    if not payload.lead_ids:
        raise HTTPException(status_code=400, detail="対象企業を選択してください")

    remaining = get_limit_remaining("email")
    if remaining <= 0:
        raise HTTPException(status_code=429, detail="本日のメール送信上限に達しました")

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM leads WHERE id IN ({','.join(['?'] * len(payload.lead_ids))}) AND user_id = ?",
            [*payload.lead_ids, user["id"]],
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
def send_form(payload: ContactRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    if not payload.lead_ids:
        raise HTTPException(status_code=400, detail="対象企業を選択してください")

    remaining = get_limit_remaining("form")
    if remaining <= 0:
        raise HTTPException(status_code=429, detail="本日のフォーム送信上限に達しました")

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        leads = conn.execute(
            f"SELECT * FROM leads WHERE id IN ({','.join(['?'] * len(payload.lead_ids))}) AND user_id = ?",
            [*payload.lead_ids, user["id"]],
        ).fetchall()

    dry_run = os.getenv("FORM_DRY_RUN", "true").lower() == "true"
    from_email = user["email"]
    from_name = user.get("name") or os.getenv("CONTACT_FROM_NAME", "AutoSales")

    sent = 0
    skipped = 0
    limited = 0

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
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
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM form_adapters ORDER BY updated_at DESC").fetchall()
    return {"items": [dict(r) for r in rows]}


@app.post("/api/form-adapters")
def create_form_adapter(payload: FormAdapterRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    domain = normalize_domain(payload.domain if payload.domain.startswith("http") else f"https://{payload.domain}")
    if not domain:
        raise HTTPException(status_code=400, detail="domain が不正です")

    now = now_iso()
    with sqlite3.connect(DB_PATH) as conn:
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
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM suppression_list ORDER BY created_at DESC").fetchall()
    return {"items": [dict(r) for r in rows]}


@app.post("/api/suppressions")
def add_suppression(payload: SuppressionRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    email = normalize_email(payload.email)
    if not EMAIL_REGEX.fullmatch(email):
        raise HTTPException(status_code=400, detail="有効なメールアドレスを入力してください")

    with sqlite3.connect(DB_PATH) as conn:
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
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM suppression_list WHERE email = ?", (normalized,))
    log_audit("remove_suppression", "email", normalized, {})
    return {"ok": True}


@app.post("/api/leads/tags/bulk")
def update_manual_tags(payload: BulkTagRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    if not payload.lead_ids:
        raise HTTPException(status_code=400, detail="対象企業を選択してください")

    with sqlite3.connect(DB_PATH) as conn:
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
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
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

    async with httpx.AsyncClient(timeout=20) as client:
        while len(places) < max_results:
            params = {
                "query": query,
                "language": language,
                "key": api_key,
            }
            if next_page_token:
                params = {"pagetoken": next_page_token, "key": api_key}

            response = await client.get(search_url, params=params)
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            for place in results:
                detail_params = {
                    "place_id": place.get("place_id"),
                    "fields": "name,website,formatted_phone_number,formatted_address,types,rating,user_ratings_total",
                    "language": language,
                    "key": api_key,
                }
                detail_resp = await client.get(details_url, params=detail_params)
                detail_resp.raise_for_status()
                detail_data = detail_resp.json().get("result", {})
                detail_types = [t.strip().lower() for t in detail_data.get("types", []) if t and t.strip()]

                if place_type and place_type not in detail_types:
                    continue

                website = detail_data.get("website", "")
                email = await extract_email_from_website(client, website)
                category, industry = classify_business(detail_types, place.get("name", ""), website)

                places.append(
                    {
                        "name": detail_data.get("name") or place.get("name", ""),
                        "place_id": place.get("place_id", ""),
                        "website": website,
                        "phone": detail_data.get("formatted_phone_number", ""),
                        "email": email,
                        "address": detail_data.get("formatted_address") or place.get("formatted_address", ""),
                        "rating": detail_data.get("rating"),
                        "user_ratings_total": detail_data.get("user_ratings_total"),
                        "raw_types": ",".join(detail_types),
                        "category": category,
                        "industry": industry,
                    }
                )
                if len(places) >= max_results:
                    break

            next_page_token = data.get("next_page_token", "")
            if not next_page_token:
                break

    return places[:max_results]


async def extract_email_from_website(client: httpx.AsyncClient, website: str) -> str:
    if not website:
        return ""
    try:
        response = await client.get(website, follow_redirects=True)
        if response.status_code >= 400:
            return ""
        text = response.text
        matches = EMAIL_REGEX.findall(text)
        for email in matches:
            if email.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                continue
            return email
    except Exception:  # noqa: BLE001
        return ""
    return ""


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


def upsert_lead(item: dict[str, Any], user_id: int | None = None) -> None:
    now = now_iso()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO leads (name, place_id, website, phone, email, address, category, industry, rating, user_ratings_total, raw_types, user_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(place_id) DO UPDATE SET
                name=excluded.name,
                website=excluded.website,
                phone=excluded.phone,
                email=excluded.email,
                address=excluded.address,
                category=excluded.category,
                industry=excluded.industry,
                rating=excluded.rating,
                user_ratings_total=excluded.user_ratings_total,
                raw_types=excluded.raw_types,
                user_id=excluded.user_id,
                updated_at=excluded.updated_at
            """,
            (
                item.get("name", ""),
                item.get("place_id", ""),
                item.get("website", ""),
                item.get("phone", ""),
                normalize_email(item.get("email", "")) if item.get("email") else "",
                item.get("address", ""),
                item.get("category", ""),
                item.get("industry", ""),
                item.get("rating"),
                item.get("user_ratings_total"),
                item.get("raw_types", ""),
                user_id,
                now,
                now,
            ),
        )


def save_contact_log(lead_id: int, channel: str, status: str, subject: str, message: str) -> None:
    created_at = now_iso()
    with sqlite3.connect(DB_PATH) as conn:
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
    user: CurrentUser,
    q: str = Query("", description="会社名や住所で検索"),
    status: str = Query("", description="マイリスト状態フィルタ"),
    priority: str = Query("", description="優先度フィルタ"),
    sort_by: str = Query("updated_at", description="並び替え項目"),
    sort_dir: str = Query("desc", description="並び順 asc/desc"),
) -> dict[str, Any]:
    init_db()

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
        WHERE m.user_id = ?
    """
    params: list[Any] = [user["id"]]

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

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()

        statuses = conn.execute(
            "SELECT DISTINCT status FROM my_list_items WHERE user_id = ? ORDER BY status",
            (user["id"],),
        ).fetchall()
        priorities = conn.execute(
            "SELECT DISTINCT priority FROM my_list_items WHERE user_id = ? ORDER BY priority",
            (user["id"],),
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
def add_to_my_list(payload: MyListBulkAddRequest, user: CurrentUser) -> dict[str, Any]:
    init_db()
    if not payload.lead_ids:
        raise HTTPException(status_code=400, detail="対象企業を選択してください")

    status_value = validate_my_list_status(payload.status)
    priority_value = validate_my_list_priority(payload.priority)

    now = now_iso()
    added = 0
    updated = 0

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        existing_rows = conn.execute(
            f"SELECT id FROM leads WHERE id IN ({','.join(['?'] * len(payload.lead_ids))}) AND user_id = ?",
            [*payload.lead_ids, user["id"]],
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

    with sqlite3.connect(DB_PATH) as conn:
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
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("DELETE FROM my_list_items WHERE id = ? AND user_id = ?", (item_id, user["id"]))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="マイリスト項目が見つかりません")

    log_audit("remove_my_list", "my_list_item", str(item_id), {}, actor=user["email"])
    return {"ok": True, "id": item_id}


@app.get("/api/contact-logs")
def get_contact_logs(
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
        WHERE l.user_id = ?
    """
    params: list[Any] = [user["id"]]

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

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()

    return {"items": [dict(r) for r in rows]}


@app.get("/api/leads/{lead_id}/timeline")
def get_lead_timeline(lead_id: int, user: CurrentUser, limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        lead = conn.execute("SELECT * FROM leads WHERE id = ? AND user_id = ?", (lead_id, user["id"])).fetchone()
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
