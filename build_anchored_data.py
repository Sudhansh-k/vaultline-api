"""Rebuild LEGO listings from the BrickLink CSV, anchored to its real new/used prices.

Run from the project folder:   python build_anchored_data.py

What it does
- Reads dataset_bricklink-scraper_*.csv and drops placeholder rows and sets with fewer
  than MIN_LOTS listings (their average prices are unreliable outliers).
- For every set, creates SALES_PER_SET simulated sales whose price depends on condition:
  condition 10 sells near the real new price, condition 4 near the real used price.
- Converts USD to INR once, here (USD_TO_INR).
- Writes a `catalog` table (name, image url, prices) for the website's catalogue pages.
- Backs up market.db first. Keeps the three original synthetic items (rolex_16610,
  lego_75192, lego_10300) unless the CSV also contains them.
"""
import glob
import shutil
import sqlite3
import time

import numpy as np
import pandas as pd

USD_TO_INR = 88.0       # update to the current exchange rate
SALES_PER_SET = 40
MIN_LOTS = 5            # sets with fewer listings have unreliable average prices
SEED = 42
DB = "market.db"

rng = np.random.default_rng(SEED)

# ---- load and clean the CSV -------------------------------------------------
csv_path = sorted(glob.glob("dataset_bricklink-scraper_*.csv"))[-1]
df = pd.read_csv(csv_path)
df["itemNo"] = df["itemNo"].astype(str)
for col in ["newAvgPrice", "usedAvgPrice", "newLots", "usedLots"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")
df["newLots"] = df["newLots"].fillna(0)
df["usedLots"] = df["usedLots"].fillna(0)

df = df[(df["newLots"] + df["usedLots"]) >= MIN_LOTS]
df = df[df["newAvgPrice"].notna() | df["usedAvgPrice"].notna()]
df = df.drop_duplicates("itemNo")
print(f"{len(df)} usable sets in {csv_path}")

# ---- back up the database ---------------------------------------------------
backup = f"market_backup_{int(time.time())}.db"
shutil.copy(DB, backup)
print("Backup saved as", backup)

con = sqlite3.connect(DB)
dates = [r[0] for r in con.execute("SELECT DISTINCT sale_date FROM listings WHERE category='lego'")]
if not dates:
    dates = [r[0] for r in con.execute("SELECT DISTINCT sale_date FROM listings")]
if not dates:   # empty database: fall back to the last 600 days
    dates = [(pd.Timestamp.today() - pd.Timedelta(days=d)).strftime("%Y-%m-%d") for d in range(600)]
print(f"Sampling sale dates from {len(dates)} existing dates (keeps the trend join working)")

# ---- build rows -------------------------------------------------------------
listing_rows, catalog_rows, ids = [], [], []
for _, r in df.iterrows():
    new_p, used_p = r["newAvgPrice"], r["usedAvgPrice"]
    if pd.isna(new_p):
        new_p = used_p / 0.65
    if pd.isna(used_p):
        used_p = new_p * 0.65
    lo, hi = min(new_p, used_p), max(new_p, used_p)   # guards against outlier rows

    item_id = "lego_" + r["itemNo"].replace("-", "_")
    ids.append(item_id)
    lots = r["newLots"] + r["usedLots"]
    liquidity = lots / (lots + 50.0)
    base_days = 45.0 * (1 - 0.6 * liquidity)

    cond = np.clip(rng.normal(7.5, 1.8, SALES_PER_SET), 2.0, 10.0)
    frac = np.clip((cond - 4.0) / 6.0, 0.0, 1.0)
    usd = (lo + (hi - lo) * frac) * rng.lognormal(0, 0.06, SALES_PER_SET)
    inr = np.round(usd * USD_TO_INR, 2)
    days = np.round(base_days * rng.lognormal(0, 0.4, SALES_PER_SET) * (1 + (10 - cond) * 0.06), 1)

    for i in range(SALES_PER_SET):
        listing_rows.append((f"{item_id}_{i + 1:04d}", item_id, "lego", float(inr[i]),
                             str(rng.choice(dates)), float(days[i]), 1, None, round(float(cond[i]), 2)))

    img = r["imageUrl"] if isinstance(r["imageUrl"], str) else None
    catalog_rows.append((item_id, r["itemNo"], str(r["itemName"]), img,
                         round(float(hi * USD_TO_INR), 2) if not pd.isna(r["newAvgPrice"]) else None,
                         round(float(lo * USD_TO_INR), 2) if not pd.isna(r["usedAvgPrice"]) else None,
                         int(r["newLots"]), int(r["usedLots"])))

# ---- write to the database --------------------------------------------------
con.execute("DELETE FROM listings WHERE item_id IN "
            "(SELECT item_id FROM listings GROUP BY item_id HAVING COUNT(*) < 5)")
con.executemany("DELETE FROM listings WHERE item_id=?", [(i,) for i in ids])
con.executemany("INSERT INTO listings VALUES (?,?,?,?,?,?,?,?,?)", listing_rows)

con.execute("DROP TABLE IF EXISTS catalog")
con.execute("""CREATE TABLE catalog (item_id TEXT PRIMARY KEY, item_no TEXT, name TEXT,
               image_url TEXT, new_price_inr REAL, used_price_inr REAL,
               new_lots INTEGER, used_lots INTEGER)""")
con.executemany("INSERT INTO catalog VALUES (?,?,?,?,?,?,?,?)", catalog_rows)
con.commit()

print("listings:", con.execute("SELECT COUNT(*) FROM listings").fetchone()[0],
      "| items:", con.execute("SELECT COUNT(DISTINCT item_id) FROM listings").fetchone()[0],
      "| catalog rows:", con.execute("SELECT COUNT(*) FROM catalog").fetchone()[0])
con.close()
print("Done. Now retrain:  python -m valuation.appraiser train")
