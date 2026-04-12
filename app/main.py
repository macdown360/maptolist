import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import urlparse
import smtplib
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "autosales.db"
load_dotenv(BASE_DIR / ".env")
GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
DEFAULT_DAILY_SEND_LIMIT = int(os.getenv("DAILY_SEND_LIMIT", "100"))

CLASSIFY_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "行政書士": {
        "industry": "士業",
        "keywords": ["行政書士", "認可", "許認可", "入管", "相続"],
    },
    "工事会社": {
        "industry": "建設",
        "keywords": ["工事", "施工", "設備", "電気工事", "配管", "塗装", "解体", "防水"],
    },
    "工務店": {
        "industry": "住宅",
        "keywords": ["工務店", "注文住宅", "リフォーム", "新築", "住宅", "設計事務所"],
    },
}

app = FastAPI(title="AutoSales Lead Collector", version="0.2.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


class ImportRequest(BaseModel):
    query: str = Field(..., description="検索キーワード。例: 工務店 東京")
    region: str = Field("", description="任意。地域キーワード")
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


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def safe_add_column(conn: sqlite3.Connection, table: str, column_def: str) -> None:
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" not in str(exc).lower():
            raise


def get_google_api_key() -> str:
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


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/settings/google-maps-key")
def get_google_maps_key_status() -> dict[str, Any]:
    init_db()
    key = get_google_api_key()
    if not key:
        return {"configured": False, "masked": ""}
    return {
        "configured": True,
        "masked": f"{key[:6]}...{key[-4:]}" if len(key) >= 10 else "configured",
    }


@app.post("/api/settings/google-maps-key")
def set_google_maps_key(payload: GoogleMapsKeyRequest) -> dict[str, Any]:
    init_db()
    key = payload.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="APIキーが空です")
    set_env_key("GOOGLE_MAPS_API_KEY", key)
    log_audit("update_setting", "setting", "google_maps_api_key", {"configured": True})
    return {"ok": True}


@app.get("/api/leads")
def get_leads(
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
        WHERE 1=1
    """
    params: list[str] = []

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
            WHERE COALESCE(mt.category, l.category) <> ''
            ORDER BY c
            """
        ).fetchall()
        industries = conn.execute(
            """
            SELECT DISTINCT COALESCE(mt.industry, l.industry) AS i
            FROM leads l
            LEFT JOIN manual_tags mt ON mt.lead_id = l.id
            WHERE COALESCE(mt.industry, l.industry) <> ''
            ORDER BY i
            """
        ).fetchall()

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


@app.post("/api/import/google-places")
async def import_google_places(payload: ImportRequest) -> dict[str, Any]:
    init_db()
    api_key = get_google_api_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="GOOGLE_MAPS_API_KEY が未設定です")

    query = payload.query.strip()
    if payload.region.strip():
        query = f"{query} {payload.region.strip()}"

    items = await fetch_places(query=query, language=payload.language, max_results=payload.max_results, api_key=api_key)
    saved = 0
    for item in items:
        upsert_lead(item)
        saved += 1

    log_audit("import_google_places", "lead", "bulk", {"query": query, "saved": saved})
    return {"imported": saved, "total_fetched": len(items)}


@app.post("/api/contact/email")
def send_email(payload: ContactRequest) -> dict[str, Any]:
    init_db()
    if not payload.lead_ids:
        raise HTTPException(status_code=400, detail="対象企業を選択してください")

    remaining = get_limit_remaining("email")
    if remaining <= 0:
        raise HTTPException(status_code=429, detail="本日のメール送信上限に達しました")

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM leads WHERE id IN ({','.join(['?'] * len(payload.lead_ids))})",
            payload.lead_ids,
        ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="対象企業が見つかりません")

    dry_run = os.getenv("EMAIL_DRY_RUN", "true").lower() == "true"
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    sent = 0
    skipped = 0
    limited = 0

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

        if dry_run:
            save_contact_log(lead["id"], "email", "dry_run", payload.subject, rendered_body)
            increment_daily_stats("email", 1)
            log_audit("contact_email", "lead", str(lead["id"]), {"status": "dry_run", "to": to_email})
            sent += 1
            continue

        if not smtp_host or not from_email:
            raise HTTPException(status_code=400, detail="SMTP設定が不足しています")

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
            log_audit("contact_email", "lead", str(lead["id"]), {"status": "sent", "to": to_email})
            sent += 1
        except Exception as exc:  # noqa: BLE001
            save_contact_log(lead["id"], "email", "failed", payload.subject, str(exc))
            log_audit("contact_email", "lead", str(lead["id"]), {"status": "failed", "error": str(exc)})

    return {"sent": sent, "skipped": skipped, "limited": limited, "dry_run": dry_run}


@app.post("/api/contact/form")
def send_form(payload: ContactRequest) -> dict[str, Any]:
    init_db()
    if not payload.lead_ids:
        raise HTTPException(status_code=400, detail="対象企業を選択してください")

    remaining = get_limit_remaining("form")
    if remaining <= 0:
        raise HTTPException(status_code=429, detail="本日のフォーム送信上限に達しました")

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        leads = conn.execute(
            f"SELECT * FROM leads WHERE id IN ({','.join(['?'] * len(payload.lead_ids))})",
            payload.lead_ids,
        ).fetchall()

    dry_run = os.getenv("FORM_DRY_RUN", "true").lower() == "true"
    from_email = os.getenv("FROM_EMAIL", "")
    from_name = os.getenv("CONTACT_FROM_NAME", "AutoSales")

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
def list_form_adapters() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM form_adapters ORDER BY updated_at DESC").fetchall()
    return {"items": [dict(r) for r in rows]}


@app.post("/api/form-adapters")
def create_form_adapter(payload: FormAdapterRequest) -> dict[str, Any]:
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
def list_suppressions() -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM suppression_list ORDER BY created_at DESC").fetchall()
    return {"items": [dict(r) for r in rows]}


@app.post("/api/suppressions")
def add_suppression(payload: SuppressionRequest) -> dict[str, Any]:
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
def remove_suppression(email: str) -> dict[str, Any]:
    init_db()
    normalized = normalize_email(email)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM suppression_list WHERE email = ?", (normalized,))
    log_audit("remove_suppression", "email", normalized, {})
    return {"ok": True}


@app.post("/api/leads/tags/bulk")
def update_manual_tags(payload: BulkTagRequest) -> dict[str, Any]:
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
def get_audit_logs(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return {"items": [dict(r) for r in rows]}


async def fetch_places(query: str, language: str, max_results: int, api_key: str) -> list[dict[str, Any]]:
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

                website = detail_data.get("website", "")
                email = await extract_email_from_website(client, website)
                category, industry = classify_business(detail_data.get("types", []), place.get("name", ""), website)

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
                        "raw_types": ",".join(detail_data.get("types", [])),
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
    tset = set(types)
    text = f"{name} {website}".lower()

    if "lawyer" in tset or "行政書士" in text:
        return "行政書士", "士業"
    if "general_contractor" in tset or "roofing_contractor" in tset or "plumber" in tset:
        return "工事会社", "建設"

    best_category = "その他"
    best_industry = "未分類"
    best_score = 0

    for category, rule in CLASSIFY_KEYWORDS.items():
        score = 0
        for kw in rule["keywords"]:
            if kw.lower() in text:
                score += 1
        if score > best_score:
            best_score = score
            best_category = category
            best_industry = str(rule["industry"])

    return best_category, best_industry


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


def upsert_lead(item: dict[str, Any]) -> None:
    now = now_iso()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO leads (name, place_id, website, phone, email, address, category, industry, rating, user_ratings_total, raw_types, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                now,
                now,
            ),
        )


def save_contact_log(lead_id: int, channel: str, status: str, subject: str, message: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO contact_logs (lead_id, channel, status, subject, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (lead_id, channel, status, subject, message, now_iso()),
        )
