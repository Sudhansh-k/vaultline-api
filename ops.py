"""ops.py
======
Resale operations, inventory risk controls, and SQLite persistence (ops.db).

Tables:
  - state (key TEXT PRIMARY KEY, value REAL)
  - inventory (id INTEGER PRIMARY KEY, item_id, name, image_url, condition_score,
               defects, bought_price, list_price, current_price, status, bought_at,
               sold_at, sold_price, photo_sha, photo_phash)
  - quotes (quote_id TEXT PRIMARY KEY, item_id, offer_price, list_price,
            condition_score, defects, photo_sha, photo_phash, expires_at, used)
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from PIL import Image

import common.db

logger = logging.getLogger("ops")

# ── Settings from env with defaults ──────────────────────────────────────────
OPS_DB_PATH = os.getenv("OPS_DB", "ops.db")
MAX_UNITS_PER_SET = int(os.getenv("MAX_UNITS_PER_SET", "3"))
MAX_TOTAL_UNITS = int(os.getenv("MAX_TOTAL_UNITS", "20"))
MIN_CAPITAL_RESERVE = float(os.getenv("MIN_CAPITAL_RESERVE", "50000"))
START_CAPITAL = float(os.getenv("START_CAPITAL", "500000"))
AGING_DAYS_1 = int(os.getenv("AGING_DAYS_1", "14"))
AGING_DISCOUNT_1 = float(os.getenv("AGING_DISCOUNT_1", "0.05"))
AGING_DAYS_2 = int(os.getenv("AGING_DAYS_2", "30"))
AGING_DISCOUNT_2 = float(os.getenv("AGING_DISCOUNT_2", "0.12"))
QUOTE_VALID_MINUTES = int(os.getenv("QUOTE_VALID_MINUTES", "15"))
DUPLICATE_CHECK = int(os.getenv("DUPLICATE_CHECK", "1"))
ALLOW_LEGACY_ACCEPT = int(os.getenv("ALLOW_LEGACY_ACCEPT", "1"))
ADMIN_KEY = os.getenv("ADMIN_KEY")

SCHEMA = """
CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         TEXT NOT NULL,
    name            TEXT NOT NULL,
    image_url       TEXT,
    condition_score REAL,
    defects         TEXT,
    bought_price    REAL NOT NULL,
    list_price      REAL NOT NULL,
    current_price   REAL NOT NULL,
    status          TEXT NOT NULL, -- 'listed' | 'sold'
    bought_at       TEXT NOT NULL,
    sold_at         TEXT,
    sold_price      REAL,
    photo_sha       TEXT,
    photo_phash     TEXT
);

CREATE INDEX IF NOT EXISTS idx_inventory_status ON inventory(status);
CREATE INDEX IF NOT EXISTS idx_inventory_item ON inventory(item_id);

CREATE TABLE IF NOT EXISTS quotes (
    quote_id        TEXT PRIMARY KEY,
    item_id         TEXT NOT NULL,
    offer_price     REAL NOT NULL,
    list_price      REAL NOT NULL,
    condition_score REAL NOT NULL,
    defects         TEXT,
    photo_sha       TEXT,
    photo_phash     TEXT,
    expires_at      TEXT NOT NULL,
    used            INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_quotes_used ON quotes(used);
"""


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(OPS_DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_ops_db() -> None:
    """Initialize ops.db schema and initial state if not already created."""
    with get_db_connection() as conn:
        conn.executescript(SCHEMA)
        cur = conn.execute("SELECT value FROM state WHERE key = 'capital'")
        row = cur.fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO state (key, value) VALUES ('capital', ?)",
                (float(START_CAPITAL),),
            )
            conn.commit()


# ── State helpers ─────────────────────────────────────────────────────────────

def get_capital() -> float:
    with get_db_connection() as conn:
        cur = conn.execute("SELECT value FROM state WHERE key = 'capital'")
        row = cur.fetchone()
        if row is not None:
            return float(row["value"])
    return float(START_CAPITAL)


def set_capital(val: float) -> None:
    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO state (key, value) VALUES ('capital', ?)", (float(val),))
        conn.commit()


def get_listed_count_for_set(item_id: str) -> int:
    with get_db_connection() as conn:
        cur = conn.execute(
            "SELECT COUNT(*) AS cnt FROM inventory WHERE item_id = ? AND status = 'listed'",
            (item_id,),
        )
        return int(cur.fetchone()["cnt"])


def get_total_listed_count() -> int:
    with get_db_connection() as conn:
        cur = conn.execute("SELECT COUNT(*) AS cnt FROM inventory WHERE status = 'listed'")
        return int(cur.fetchone()["cnt"])


# ── Photo hash & duplicate detection ──────────────────────────────────────────

def compute_phash(image_bytes: bytes) -> str:
    """Compute 64-bit average hash (aHash) with Pillow: 8x8 grayscale vs mean."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
            pixels = list(img.tobytes())
            avg = sum(pixels) / len(pixels)
            bits = "".join("1" if p > avg else "0" for p in pixels)
            return f"{int(bits, 2):016x}"
    except Exception as e:
        logger.warning("compute_phash failed: %s", e)
        return ""


def compute_hashes(image_bytes: bytes) -> tuple[str, str]:
    sha = hashlib.sha256(image_bytes).hexdigest()
    phash = compute_phash(image_bytes)
    return sha, phash


def hamming_distance(h1: str, h2: str) -> int:
    try:
        return bin(int(h1, 16) ^ int(h2, 16)).count("1")
    except Exception:
        return 64


def is_duplicate_photo(sha: str, phash: str) -> bool:
    """Check if photo matches existing inventory (same sha or aHash Hamming dist <= 5)."""
    with get_db_connection() as conn:
        cur = conn.execute("SELECT photo_sha, photo_phash FROM inventory")
        rows = cur.fetchall()
        for r in rows:
            stored_sha = r["photo_sha"]
            stored_phash = r["photo_phash"]
            if sha and stored_sha and sha == stored_sha:
                return True
            if phash and stored_phash:
                if hamming_distance(phash, stored_phash) <= 5:
                    return True
    return False


# ── Quote creation ────────────────────────────────────────────────────────────

def create_quote(
    item_id: str,
    offer_price: float,
    list_price: float,
    condition_score: float,
    defects: list[str] | Any,
    photo_sha: str,
    photo_phash: str,
) -> tuple[str, str]:
    quote_id = str(uuid.uuid4())
    expires_dt = datetime.now(timezone.utc) + timedelta(minutes=QUOTE_VALID_MINUTES)
    expires_at = expires_dt.isoformat()
    defects_json = json.dumps(defects) if isinstance(defects, (list, dict)) else str(defects or "[]")

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO quotes (
                quote_id, item_id, offer_price, list_price,
                condition_score, defects, photo_sha, photo_phash, expires_at, used
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                quote_id,
                item_id,
                float(offer_price),
                float(list_price),
                float(condition_score),
                defects_json,
                photo_sha,
                photo_phash,
                expires_at,
            ),
        )
        conn.commit()

    return quote_id, expires_at


# ── Aging discounts ───────────────────────────────────────────────────────────

def apply_aging_discounts() -> int:
    """
    For each listed item, age = days since bought_at.
    past AGING_DAYS_1 current_price = list_price*(1-AGING_DISCOUNT_1),
    past AGING_DAYS_2 current_price = list_price*(1-AGING_DISCOUNT_2);
    never below bought_price*0.95.
    """
    now = datetime.now(timezone.utc)
    updated_count = 0

    with get_db_connection() as conn:
        cur = conn.execute(
            "SELECT id, bought_price, list_price, current_price, bought_at FROM inventory WHERE status = 'listed'"
        )
        rows = cur.fetchall()
        for r in rows:
            try:
                bought_dt = datetime.fromisoformat(r["bought_at"])
                if bought_dt.tzinfo is None:
                    bought_dt = bought_dt.replace(tzinfo=timezone.utc)
                age_days = (now - bought_dt).total_seconds() / 86400.0
            except Exception:
                age_days = 0.0

            list_p = float(r["list_price"])
            bought_p = float(r["bought_price"])

            if age_days >= AGING_DAYS_2:
                target_p = list_p * (1.0 - AGING_DISCOUNT_2)
            elif age_days >= AGING_DAYS_1:
                target_p = list_p * (1.0 - AGING_DISCOUNT_1)
            else:
                target_p = list_p

            floor_p = bought_p * 0.95
            new_current = round(max(target_p, floor_p), 2)

            if abs(new_current - float(r["current_price"])) > 0.001:
                conn.execute(
                    "UPDATE inventory SET current_price = ? WHERE id = ?",
                    (new_current, r["id"]),
                )
                updated_count += 1

        if updated_count > 0:
            conn.commit()

    return updated_count


# ── Acceptance ────────────────────────────────────────────────────────────────

def get_catalog_metadata(item_id: str) -> tuple[str, str | None]:
    """Lookup name and image_url from market.db catalog table."""
    try:
        with common.db.connect() as c:
            cur = c.execute(
                "SELECT name, image_url FROM catalog WHERE item_id = ?",
                (item_id,),
            )
            row = cur.fetchone()
            if row:
                return str(row[0]), (str(row[1]) if row[1] else None)
    except Exception as e:
        logger.warning("get_catalog_metadata failed: %s", e)
    return item_id, None


def accept_quote(quote_id: str) -> dict:
    with get_db_connection() as conn:
        cur = conn.execute(
            "SELECT quote_id, item_id, offer_price, list_price, condition_score, "
            "defects, photo_sha, photo_phash, expires_at, used FROM quotes WHERE quote_id = ?",
            (quote_id,),
        )
        quote = cur.fetchone()
        if not quote:
            raise ValueError("Quote not found")
        if quote["used"]:
            raise ValueError("Quote has already been used")

        # Expiry check
        expires_dt = datetime.fromisoformat(quote["expires_at"])
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_dt:
            raise ValueError("Quote has expired")

        # Capital check
        capital_cur = conn.execute("SELECT value FROM state WHERE key = 'capital'")
        cap_row = capital_cur.fetchone()
        capital = float(cap_row["value"]) if cap_row else START_CAPITAL
        offer_price = float(quote["offer_price"])
        if capital < offer_price:
            raise ValueError("Insufficient capital to accept this offer")

        new_capital = round(capital - offer_price, 2)
        conn.execute("UPDATE state SET value = ? WHERE key = 'capital'", (new_capital,))

        name, image_url = get_catalog_metadata(quote["item_id"])
        now_iso = datetime.now(timezone.utc).isoformat()
        list_price = float(quote["list_price"])

        ins_cur = conn.execute(
            """
            INSERT INTO inventory (
                item_id, name, image_url, condition_score, defects,
                bought_price, list_price, current_price, status,
                bought_at, sold_at, sold_price, photo_sha, photo_phash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'listed', ?, NULL, NULL, ?, ?)
            """,
            (
                quote["item_id"],
                name,
                image_url,
                float(quote["condition_score"]),
                quote["defects"],
                offer_price,
                list_price,
                list_price,
                now_iso,
                quote["photo_sha"],
                quote["photo_phash"],
            ),
        )
        inventory_id = ins_cur.lastrowid
        conn.execute("UPDATE quotes SET used = 1 WHERE quote_id = ?", (quote_id,))
        conn.commit()

    return {
        "capital": new_capital,
        "inventory_id": int(inventory_id),
        "listed_at_price": list_price,
    }


def accept_legacy(item_id: str, price: float) -> dict:
    if not ALLOW_LEGACY_ACCEPT:
        raise ValueError("quote_id is required (legacy accept is disabled)")

    price = float(price)
    with get_db_connection() as conn:
        cap_cur = conn.execute("SELECT value FROM state WHERE key = 'capital'")
        cap_row = cap_cur.fetchone()
        capital = float(cap_row["value"]) if cap_row else START_CAPITAL
        if capital < price:
            raise ValueError("Insufficient capital")

        new_capital = round(capital - price, 2)
        conn.execute("UPDATE state SET value = ? WHERE key = 'capital'", (new_capital,))

        name, image_url = get_catalog_metadata(item_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        list_price = round(price * 1.25, 2)

        ins_cur = conn.execute(
            """
            INSERT INTO inventory (
                item_id, name, image_url, condition_score, defects,
                bought_price, list_price, current_price, status,
                bought_at, sold_at, sold_price, photo_sha, photo_phash
            ) VALUES (?, ?, ?, 8.0, '[]', ?, ?, ?, 'listed', ?, NULL, NULL, NULL, NULL)
            """,
            (
                item_id,
                name,
                image_url,
                price,
                list_price,
                list_price,
                now_iso,
            ),
        )
        inventory_id = ins_cur.lastrowid
        conn.commit()

    return {
        "capital": new_capital,
        "inventory_id": int(inventory_id),
        "listed_at_price": list_price,
    }


# ── Shop operations ───────────────────────────────────────────────────────────

def get_shop_items() -> list[dict]:
    apply_aging_discounts()
    now = datetime.now(timezone.utc)
    items = []

    with get_db_connection() as conn:
        cur = conn.execute(
            """
            SELECT id, item_id, name, image_url, condition_score, defects,
                   list_price, current_price, bought_at
            FROM inventory
            WHERE status = 'listed'
            ORDER BY bought_at DESC, id DESC
            """
        )
        rows = cur.fetchall()
        for r in rows:
            try:
                bought_dt = datetime.fromisoformat(r["bought_at"])
                if bought_dt.tzinfo is None:
                    bought_dt = bought_dt.replace(tzinfo=timezone.utc)
                age_days = round((now - bought_dt).total_seconds() / 86400.0, 1)
            except Exception:
                age_days = 0.0

            try:
                defects = json.loads(r["defects"]) if r["defects"] else []
            except Exception:
                defects = []

            list_p = float(r["list_price"])
            cur_p = float(r["current_price"])

            items.append({
                "id": int(r["id"]),
                "item_id": r["item_id"],
                "name": r["name"],
                "image_url": r["image_url"],
                "condition_score": float(r["condition_score"]) if r["condition_score"] is not None else None,
                "defects": defects,
                "list_price": list_p,
                "current_price": cur_p,
                "age_days": age_days,
                "discounted": bool(cur_p < list_p),
            })

    return items


def buy_item(inventory_id: int) -> dict:
    apply_aging_discounts()
    with get_db_connection() as conn:
        cur = conn.execute(
            "SELECT id, status, current_price, bought_price FROM inventory WHERE id = ?",
            (inventory_id,),
        )
        item = cur.fetchone()
        if not item:
            raise KeyError("Item not found")
        if item["status"] != "listed":
            raise ValueError("Item already sold")

        sold_price = float(item["current_price"])
        bought_price = float(item["bought_price"])
        profit = round(sold_price - bought_price, 2)
        now_iso = datetime.now(timezone.utc).isoformat()

        conn.execute(
            "UPDATE inventory SET status = 'sold', sold_at = ?, sold_price = ? WHERE id = ?",
            (now_iso, sold_price, inventory_id),
        )
        conn.execute(
            "UPDATE state SET value = value + ? WHERE key = 'capital'",
            (sold_price,),
        )
        conn.commit()

    return {"profit": profit, "sold_price": sold_price}


# ── Ops reporting ─────────────────────────────────────────────────────────────

def get_summary() -> dict:
    apply_aging_discounts()
    capital = get_capital()

    with get_db_connection() as conn:
        # Units and values
        cur = conn.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'listed' THEN 1 ELSE 0 END) AS units_listed,
                SUM(CASE WHEN status = 'sold' THEN 1 ELSE 0 END) AS units_sold,
                SUM(CASE WHEN status = 'listed' THEN bought_price ELSE 0.0 END) AS stock_cost,
                SUM(CASE WHEN status = 'listed' THEN current_price ELSE 0.0 END) AS stock_list,
                SUM(CASE WHEN status = 'sold' THEN (sold_price - bought_price) ELSE 0.0 END) AS profit,
                SUM(CASE WHEN status = 'sold' THEN sold_price ELSE 0.0 END) AS revenue,
                SUM(bought_price) AS total_bought
            FROM inventory
            """
        )
        row = cur.fetchone()

        units_listed = int(row["units_listed"] or 0)
        units_sold = int(row["units_sold"] or 0)
        stock_cost = round(float(row["stock_cost"] or 0.0), 2)
        stock_list = round(float(row["stock_list"] or 0.0), 2)
        realized_profit = round(float(row["profit"] or 0.0), 2)
        total_revenue = round(float(row["revenue"] or 0.0), 2)
        total_bought = round(float(row["total_bought"] or 0.0), 2)

        avg_margin_pct = (
            round((realized_profit / total_revenue) * 100.0, 2)
            if total_revenue > 0
            else 0.0
        )

    return {
        "capital": round(capital, 2),
        "units_listed": units_listed,
        "units_sold": units_sold,
        "stock_value_at_cost": stock_cost,
        "stock_value_at_list": stock_list,
        "realized_profit": realized_profit,
        "avg_margin_pct": avg_margin_pct,
        "total_bought": total_bought,
        "total_revenue": total_revenue,
    }


def get_inventory_list(status: str = "all") -> list[dict]:
    apply_aging_discounts()
    now = datetime.now(timezone.utc)
    query = "SELECT * FROM inventory"
    params = ()

    if status == "listed":
        query += " WHERE status = 'listed'"
    elif status == "sold":
        query += " WHERE status = 'sold'"

    query += " ORDER BY bought_at DESC, id DESC"

    items = []
    with get_db_connection() as conn:
        cur = conn.execute(query, params)
        rows = cur.fetchall()
        for r in rows:
            try:
                bought_dt = datetime.fromisoformat(r["bought_at"])
                if bought_dt.tzinfo is None:
                    bought_dt = bought_dt.replace(tzinfo=timezone.utc)
                age_days = round((now - bought_dt).total_seconds() / 86400.0, 1)
            except Exception:
                age_days = 0.0

            try:
                defects = json.loads(r["defects"]) if r["defects"] else []
            except Exception:
                defects = []

            list_p = float(r["list_price"])
            cur_p = float(r["current_price"])

            items.append({
                "id": int(r["id"]),
                "item_id": r["item_id"],
                "name": r["name"],
                "image_url": r["image_url"],
                "condition_score": float(r["condition_score"]) if r["condition_score"] is not None else None,
                "defects": defects,
                "bought_price": float(r["bought_price"]),
                "list_price": list_p,
                "current_price": cur_p,
                "status": r["status"],
                "bought_at": r["bought_at"],
                "sold_at": r["sold_at"],
                "sold_price": float(r["sold_price"]) if r["sold_price"] is not None else None,
                "photo_sha": r["photo_sha"],
                "photo_phash": r["photo_phash"],
                "age_days": age_days,
                "discounted": bool(cur_p < list_p),
            })

    return items


def get_profit_series() -> list[dict]:
    apply_aging_discounts()
    with get_db_connection() as conn:
        cur = conn.execute(
            """
            SELECT sold_at, (sold_price - bought_price) AS profit
            FROM inventory
            WHERE status = 'sold' AND sold_at IS NOT NULL
            ORDER BY sold_at ASC
            """
        )
        rows = cur.fetchall()

    daily_profit: dict[str, float] = {}
    for r in rows:
        d_str = r["sold_at"][:10]
        daily_profit[d_str] = daily_profit.get(d_str, 0.0) + float(r["profit"])

    series = []
    cum = 0.0
    for d in sorted(daily_profit.keys()):
        p = daily_profit[d]
        cum += p
        series.append({
            "date": d,
            "profit": round(p, 2),
            "cumulative_profit": round(cum, 2),
        })

    return series


def get_risk_metrics() -> dict:
    apply_aging_discounts()
    now = datetime.now(timezone.utc)
    cutoff_30d = (now - timedelta(days=30)).isoformat()
    capital = get_capital()

    with get_db_connection() as conn:
        # Units by set top 10
        cur = conn.execute(
            """
            SELECT item_id, COUNT(*) AS cnt
            FROM inventory
            WHERE status = 'listed'
            GROUP BY item_id
            ORDER BY cnt DESC, item_id ASC
            LIMIT 10
            """
        )
        units_by_set = {r["item_id"]: int(r["cnt"]) for r in cur.fetchall()}

        # Listed items age metrics
        cur = conn.execute(
            "SELECT bought_at, bought_price FROM inventory WHERE status = 'listed'"
        )
        listed = cur.fetchall()
        units_listed = len(listed)

        ages = []
        units_over_14 = 0
        units_over_30 = 0
        stock_value_at_cost = 0.0

        for r in listed:
            stock_value_at_cost += float(r["bought_price"])
            try:
                b_dt = datetime.fromisoformat(r["bought_at"])
                if b_dt.tzinfo is None:
                    b_dt = b_dt.replace(tzinfo=timezone.utc)
                age = (now - b_dt).total_seconds() / 86400.0
            except Exception:
                age = 0.0
            ages.append(age)
            if age >= 14.0:
                units_over_14 += 1
            if age >= 30.0:
                units_over_30 += 1

        avg_age = round(sum(ages) / len(ages), 1) if ages else 0.0

        # Capital locked pct
        total_assets = capital + stock_value_at_cost
        capital_locked_pct = (
            round((stock_value_at_cost / total_assets) * 100.0, 2)
            if total_assets > 0
            else 0.0
        )

        # Sell through rate 30d
        cur_30 = conn.execute(
            "SELECT COUNT(*) AS cnt FROM inventory WHERE status = 'sold' AND sold_at >= ?",
            (cutoff_30d,),
        )
        sold_30d = int(cur_30.fetchone()["cnt"])
        denom = sold_30d + units_listed
        sell_through_rate_30d = round(sold_30d / denom, 3) if denom > 0 else 0.0

    return {
        "units_listed": units_listed,
        "units_by_set": units_by_set,
        "avg_age_days": avg_age,
        "units_over_14_days": units_over_14,
        "units_over_30_days": units_over_30,
        "capital_locked_pct": capital_locked_pct,
        "sell_through_rate_30d": sell_through_rate_30d,
    }


def get_active_settings() -> dict:
    return {
        "max_units_per_set": MAX_UNITS_PER_SET,
        "max_total_units": MAX_TOTAL_UNITS,
        "min_capital_reserve": MIN_CAPITAL_RESERVE,
        "start_capital": START_CAPITAL,
        "aging_days_1": AGING_DAYS_1,
        "aging_discount_1": AGING_DISCOUNT_1,
        "aging_days_2": AGING_DAYS_2,
        "aging_discount_2": AGING_DISCOUNT_2,
        "quote_valid_minutes": QUOTE_VALID_MINUTES,
        "duplicate_check": bool(DUPLICATE_CHECK),
        "allow_legacy_accept": bool(ALLOW_LEGACY_ACCEPT),
    }


# ── Simulation, Seeding, Reset ────────────────────────────────────────────────

def simulate_sale() -> dict:
    apply_aging_discounts()
    with get_db_connection() as conn:
        cur = conn.execute(
            "SELECT id, item_id, name, bought_price, current_price FROM inventory "
            "WHERE status = 'listed' ORDER BY RANDOM() LIMIT 1"
        )
        item = cur.fetchone()
        if not item:
            raise KeyError("No listed items available to simulate sale")

        sold_price = float(item["current_price"])
        bought_price = float(item["bought_price"])
        profit = round(sold_price - bought_price, 2)
        now_iso = datetime.now(timezone.utc).isoformat()

        conn.execute(
            "UPDATE inventory SET status = 'sold', sold_at = ?, sold_price = ? WHERE id = ?",
            (now_iso, sold_price, item["id"]),
        )
        conn.execute(
            "UPDATE state SET value = value + ? WHERE key = 'capital'",
            (sold_price,),
        )
        cap_cur = conn.execute("SELECT value FROM state WHERE key = 'capital'")
        new_cap = round(float(cap_cur.fetchone()["value"]), 2)
        conn.commit()

    return {
        "item_id": item["item_id"],
        "name": item["name"],
        "sold_price": sold_price,
        "profit": profit,
        "capital": new_cap,
    }


def seed_database() -> dict:
    """Seed exactly 12 realistic rows from catalog: 6 listed and 6 sold with mixed profits."""
    with get_db_connection() as conn:
        cnt_cur = conn.execute("SELECT COUNT(*) AS cnt FROM inventory")
        if cnt_cur.fetchone()["cnt"] > 0:
            raise ValueError("Inventory is not empty; cannot seed")

    # Fetch 12 items from market.db catalog
    with common.db.connect() as c:
        cur = c.execute(
            """
            SELECT item_id, name, image_url, new_price_inr, used_price_inr
            FROM catalog
            WHERE (new_price_inr > 0 OR used_price_inr > 0)
            LIMIT 12
            """
        )
        cat_items = cur.fetchall()

    if len(cat_items) < 12:
        raise RuntimeError("Not enough catalog items in market.db to seed 12 rows")

    now = datetime.now(timezone.utc)
    total_bought = 0.0
    total_revenue = 0.0

    with get_db_connection() as conn:
        # Seed 6 listed items (indices 0 to 5)
        # We spread bought_at: 2d, 5d, 8d, 16d, 24d, 35d ago so aging rules trigger!
        listed_ages = [2, 5, 8, 16, 24, 35]
        listed_scores = [8.5, 9.0, 7.8, 8.2, 9.5, 8.0]

        for i in range(6):
            cat = cat_items[i]
            base_p = float(cat[4]) if (cat[4] and cat[4] > 0) else float(cat[3] or 1000.0)
            bought_p = round(base_p * 0.75, 2)
            list_p = round(base_p * 1.10, 2)
            bought_at_dt = now - timedelta(days=listed_ages[i], hours=i * 2)
            bought_at_iso = bought_at_dt.isoformat()
            sha = hashlib.sha256(f"seed_listed_{i}".encode()).hexdigest()
            phash = f"{i + 1:016x}"
            defects = ["minor box crease"] if i % 2 == 1 else []

            conn.execute(
                """
                INSERT INTO inventory (
                    item_id, name, image_url, condition_score, defects,
                    bought_price, list_price, current_price, status,
                    bought_at, sold_at, sold_price, photo_sha, photo_phash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'listed', ?, NULL, NULL, ?, ?)
                """,
                (
                    cat[0],
                    cat[1],
                    cat[2],
                    listed_scores[i],
                    json.dumps(defects),
                    bought_p,
                    list_p,
                    list_p,
                    bought_at_iso,
                    sha,
                    phash,
                ),
            )
            total_bought += bought_p

        # Seed 6 sold items (indices 6 to 11)
        # Sold spread over the last 14 days: 1, 3, 5, 8, 11, 13 days ago
        # 4 positive profits, 2 negative profits
        sold_days = [1, 3, 5, 8, 11, 13]
        sold_multipliers = [1.25, 1.20, 1.15, 1.30, 0.85, 0.80]  # last 2 are negative profit
        sold_scores = [8.0, 7.5, 8.8, 9.2, 6.8, 6.2]

        for j in range(6):
            cat = cat_items[6 + j]
            base_p = float(cat[4]) if (cat[4] and cat[4] > 0) else float(cat[3] or 1000.0)
            bought_p = round(base_p * 0.75, 2)
            list_p = round(base_p * 1.10, 2)
            sold_p = round(bought_p * sold_multipliers[j], 2)

            sold_at_dt = now - timedelta(days=sold_days[j], hours=j * 3)
            bought_at_dt = sold_at_dt - timedelta(days=4)
            sha = hashlib.sha256(f"seed_sold_{j}".encode()).hexdigest()
            phash = f"{j + 7:016x}"
            defects = ["corner wear"] if j >= 4 else []

            conn.execute(
                """
                INSERT INTO inventory (
                    item_id, name, image_url, condition_score, defects,
                    bought_price, list_price, current_price, status,
                    bought_at, sold_at, sold_price, photo_sha, photo_phash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'sold', ?, ?, ?, ?, ?)
                """,
                (
                    cat[0],
                    cat[1],
                    cat[2],
                    sold_scores[j],
                    json.dumps(defects),
                    bought_p,
                    list_p,
                    list_p,
                    bought_at_dt.isoformat(),
                    sold_at_dt.isoformat(),
                    sold_p,
                    sha,
                    phash,
                ),
            )
            total_bought += bought_p
            total_revenue += sold_p

        # Net capital after purchases and sales
        seeded_capital = round(START_CAPITAL - total_bought + total_revenue, 2)
        conn.execute("UPDATE state SET value = ? WHERE key = 'capital'", (seeded_capital,))
        conn.commit()

    # Apply aging immediately on the newly seeded listed items
    apply_aging_discounts()

    return {
        "ok": True,
        "seeded": 12,
        "units_listed": 6,
        "units_sold": 6,
        "capital": seeded_capital,
    }


def reset_database() -> dict:
    """Clear inventory, clear quotes, and reset capital to START_CAPITAL."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM inventory")
        conn.execute("DELETE FROM quotes")
        conn.execute(
            "INSERT OR REPLACE INTO state (key, value) VALUES ('capital', ?)",
            (float(START_CAPITAL),),
        )
        conn.commit()
    return {
        "ok": True,
        "message": "Inventory and quotes cleared, capital reset",
        "capital": float(START_CAPITAL),
    }


# Auto-initialize on import
init_ops_db()
