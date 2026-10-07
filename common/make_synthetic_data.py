"""Fake Table A / Table B so Persons 2-4 can develop before real scrapes exist.
Usage: python -m common.make_synthetic_data
"""
import numpy as np
import pandas as pd
from common.db import connect

rng = np.random.default_rng(42)
ITEMS = {"lego_75192": ("lego", 60000), "rolex_16610": ("watch", 650000), "lego_10300": ("lego", 18000)}
dates = pd.date_range("2024-01-01", "2026-09-30", freq="D")


def season(d):
    return 1 + 0.15 * np.sin(2 * np.pi * (d.dayofyear - 300) / 365)  # Q4 bump


trend_rows = []
for cat in {"lego", "watch"}:
    for d in dates:
        s = season(d) * rng.normal(1, 0.05)
        trend_rows.append((d.date().isoformat(), cat, 800 * rng.normal(1, 0.05) / s,
                           100 * s, 30 / s * rng.normal(1, 0.1)))

rows = []
n = 0
for item, (cat, base) in ITEMS.items():
    for d in rng.choice(dates, 500):
        d = pd.Timestamp(d)
        cond = float(np.clip(rng.normal(7, 1.8), 1, 10))
        price = base * season(d) * (0.55 + 0.05 * cond) * rng.normal(1, 0.04)
        days = float(np.clip(rng.weibull(1.3) * (30 / season(d)) * (1.6 - cond / 10 * 0.8), 1, 365))
        n += 1
        rows.append((f"{item}_{n:04d}", item, cat, round(price, 2), d.date().isoformat(), round(days, 1), 1,
                     None, round(cond, 2)))

with connect() as c:
    c.executemany("INSERT OR REPLACE INTO market_trends VALUES (?,?,?,?,?)", trend_rows)
    c.executemany("INSERT OR REPLACE INTO listings VALUES (?,?,?,?,?,?,?,?,?)", rows)
print(f"Inserted {len(rows)} listings, {len(trend_rows)} trend rows")
