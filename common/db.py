"""Shared DB contract (Table A = listings, Table B = market_trends). SQLite for dev; swap the URL for Postgres later."""
import os
import sqlite3
import pandas as pd

DB_PATH = os.environ.get("MARKET_DB", "market.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (          -- Table A
    listing_id      TEXT PRIMARY KEY,          -- e.g. lego_001
    item_id         TEXT NOT NULL,             -- catalog item (e.g. LEGO set 75192)
    category        TEXT NOT NULL,
    sale_price      REAL NOT NULL,
    sale_date       TEXT NOT NULL,             -- ISO date
    days_to_sell    REAL,                      -- listing -> sale (or -> today if unsold)
    sold            INTEGER DEFAULT 1,         -- 0 = still unsold (censored) for survival model
    image_path      TEXT,                      -- images/lego_001.jpg
    condition_score REAL                       -- filled by Person 2
);
CREATE TABLE IF NOT EXISTS market_trends (     -- Table B
    date                  TEXT,
    category              TEXT,
    total_active_listings REAL,
    search_volume_index   REAL,
    avg_days_on_market    REAL,
    PRIMARY KEY (date, category)
);
"""


def connect(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def load_listings(db_path=None) -> pd.DataFrame:
    with connect(db_path) as c:
        return pd.read_sql("SELECT * FROM listings", c)


def load_trends(db_path=None) -> pd.DataFrame:
    with connect(db_path) as c:
        return pd.read_sql("SELECT * FROM market_trends", c)
