"""api.py
========
Run: uvicorn api:app --reload   (docs at http://localhost:8000/docs)
"""

from __future__ import annotations

import glob
import logging
import os
import time

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

import common.db
import ops
from pipeline import instant_offer
from vision.fallback_cv import PhotoQualityError
from vision.gemini_vision import (
    MODELS,
    VISION_MODE,
    cache_size,
    predict_condition,
)

logger = logging.getLogger("api")

app = FastAPI(title="Autonomous Collectibles Market Maker")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

USD_TO_INR = 88.0


# ── helpers ───────────────────────────────────────────────────────────────────

def _to_python(obj):
    """Recursively convert numpy scalars / arrays to plain Python types."""
    if isinstance(obj, dict):
        return {k: _to_python(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_python(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def verify_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")):
    admin_key = os.getenv("ADMIN_KEY")
    if admin_key:
        if not x_admin_key or x_admin_key != admin_key:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: invalid or missing X-Admin-Key header",
            )
    else:
        logger.warning("ADMIN_KEY is not set; allowing unprotected admin operation")


# ── Existing Endpoints ────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True}


@app.get("/items")
def items():
    """Whitelisted items the customer can pick from."""
    with common.db.connect() as c:
        return [r[0] for r in c.execute("SELECT DISTINCT item_id FROM listings")]


@app.get("/catalog")
def catalog():
    # 1) preferred: the catalog table in market.db
    try:
        with common.db.connect() as c:
            cur = c.execute(
                "SELECT item_id, item_no, name, image_url, new_price_inr, "
                "used_price_inr, new_lots, used_lots FROM catalog"
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        if rows:
            return rows
    except Exception as e:
        logger.warning("catalog table failed: %s", e)

    # 2) fallback: build from the BrickLink CSV in the repo
    files = sorted(glob.glob("dataset_bricklink-scraper_*.csv"))
    if not files:
        raise HTTPException(500, detail="No catalogue data found on the server")
    df = pd.read_csv(files[-1])
    for col in ["newAvgPrice", "usedAvgPrice", "newLots", "usedLots"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df[["newLots", "usedLots"]] = df[["newLots", "usedLots"]].fillna(0)
    df = df[(df["newLots"] + df["usedLots"]) >= 5].drop_duplicates("itemNo")
    out = pd.DataFrame(
        {
            "item_id":        "lego_" + df["itemNo"].astype(str).str.replace("-", "_"),
            "item_no":        df["itemNo"].astype(str),
            "name":           df["itemName"].astype(str),
            "image_url":      df["imageUrl"],
            "new_price_inr":  (df["newAvgPrice"] * USD_TO_INR).round(2),
            "used_price_inr": (df["usedAvgPrice"] * USD_TO_INR).round(2),
            "new_lots":       df["newLots"].astype(int),
            "used_lots":      df["usedLots"].astype(int),
        }
    )
    return out.astype(object).where(out.notna(), None).to_dict("records")


@app.get("/stats")
def stats():
    with common.db.connect() as c:
        total, item_count, avg_days = c.execute(
            "SELECT COUNT(*), COUNT(DISTINCT item_id), ROUND(AVG(days_to_sell),1) "
            "FROM listings WHERE sold=1"
        ).fetchone()
    return {"listings": total, "items": item_count, "avg_days_to_sell": avg_days}


# ── Vision Endpoints ──────────────────────────────────────────────────────────

@app.get("/vision/status")
def vision_status():
    """Return current vision configuration. Never returns the API key."""
    api_key = (
        os.getenv("GOOGLE_API_KEY", "")
        or os.getenv("GEMINI_API_KEY", "")
    )
    return {
        "mode":              VISION_MODE,
        "models":            MODELS,
        "gemini_configured": bool(api_key),
        "cache_size":        cache_size(),
    }


@app.get("/vision/selftest")
def vision_selftest():
    import cv2

    img_arr = np.full((64, 64, 3), 128, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img_arr)
    if not ok:
        raise HTTPException(500, detail="Could not encode selftest image")
    img_bytes = buf.tobytes()

    t0 = time.perf_counter()
    try:
        original = os.environ.get("PHOTO_QUALITY_GATE")
        os.environ["PHOTO_QUALITY_GATE"] = "0"
        result = predict_condition(img_bytes, mime_type="image/png")
        if original is None:
            del os.environ["PHOTO_QUALITY_GATE"]
        else:
            os.environ["PHOTO_QUALITY_GATE"] = original
    except Exception as e:
        elapsed = round(time.perf_counter() - t0, 3)
        return {"ok": False, "error": str(e)[:200], "seconds": elapsed}

    elapsed = round(time.perf_counter() - t0, 3)
    return {
        "ok":      True,
        "source":  result.get("source", "unknown"),
        "seconds": elapsed,
    }


# ── Offer & Acceptance ────────────────────────────────────────────────────────

@app.post("/offer")
async def offer(item_id: str = Form(...), image: UploadFile = File(...)):
    image_bytes = await image.read()

    # 1. Read inventory stock for this set and capital from ops.db
    current_stock = ops.get_listed_count_for_set(item_id)
    total_listed = ops.get_total_listed_count()
    capital = ops.get_capital()

    try:
        result = instant_offer(
            item_id,
            image_bytes,
            current_stock,
            capital,
        )
    except PhotoQualityError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("instant_offer pipeline failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail="The vision service is busy right now. Please try again in a moment.",
        )

    # Calculate image hashes for duplicate check
    photo_sha, photo_phash = ops.compute_hashes(image_bytes)

    offer_amount = float(result.get("offer_to_customer", 0.0))
    cond = result.get("condition", {})
    condition_score = float(cond.get("condition_score", 0.0))
    defects = cond.get("defects", [])

    # Apply inventory risk rules in strict order:
    if total_listed >= ops.MAX_TOTAL_UNITS:
        result["offer_to_customer"] = 0.0
        result["action"] = "STOP_BUYING"
        result["reason"] = "STOCK_LIMIT"
    elif current_stock >= ops.MAX_UNITS_PER_SET:
        result["offer_to_customer"] = 0.0
        result["action"] = "STOP_BUYING"
        result["reason"] = "SET_LIMIT"
    elif (capital - offer_amount) < ops.MIN_CAPITAL_RESERVE:
        result["offer_to_customer"] = 0.0
        result["action"] = "STOP_BUYING"
        result["reason"] = "LOW_CAPITAL"
    elif ops.DUPLICATE_CHECK and ops.is_duplicate_photo(photo_sha, photo_phash):
        result["offer_to_customer"] = 0.0
        result["action"] = "STOP_BUYING"
        result["reason"] = "DUPLICATE_PHOTO"
    elif condition_score < 3.0 or len(defects) >= 4:
        result["offer_to_customer"] = 0.0
        result["action"] = "MANUAL_REVIEW"
        result["reason"] = "NEEDS_INSPECTION"
    else:
        result["reason"] = None

    # Quote storage
    if result["offer_to_customer"] > 0:
        quote_id, valid_until = ops.create_quote(
            item_id=item_id,
            offer_price=float(result["offer_to_customer"]),
            list_price=float(result["list_price"]),
            condition_score=condition_score,
            defects=defects,
            photo_sha=photo_sha,
            photo_phash=photo_phash,
        )
        result["quote_id"] = quote_id
        result["valid_until"] = valid_until
    else:
        result["quote_id"] = None
        result["valid_until"] = None

    return _to_python(result)


@app.post("/accept")
def accept(
    quote_id: str | None = Form(None),
    item_id: str | None = Form(None),
    price: float | None = Form(None),
):
    try:
        if quote_id:
            return _to_python(ops.accept_quote(quote_id))
        elif item_id and price is not None:
            return _to_python(ops.accept_legacy(item_id, price))
        else:
            raise HTTPException(status_code=400, detail="quote_id is required")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Shop Endpoints ────────────────────────────────────────────────────────────

@app.get("/shop")
def shop():
    return _to_python(ops.get_shop_items())


@app.post("/shop/{item_id}/buy")
def shop_buy(item_id: int):
    try:
        return _to_python(ops.buy_item(item_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="Item not found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ── Operations Endpoints ──────────────────────────────────────────────────────

@app.get("/ops/summary")
def ops_summary():
    return _to_python(ops.get_summary())


@app.get("/ops/inventory")
def ops_inventory(status: str = Query("all", pattern="^(listed|sold|all)$")):
    return _to_python(ops.get_inventory_list(status))


@app.get("/ops/profit_series")
def ops_profit_series():
    return _to_python(ops.get_profit_series())


@app.get("/ops/risk")
def ops_risk():
    return _to_python(ops.get_risk_metrics())


@app.get("/ops/settings")
def ops_settings():
    return _to_python(ops.get_active_settings())


@app.post("/ops/run_aging")
def ops_run_aging():
    updated = ops.apply_aging_discounts()
    return {"ok": True, "updated": updated}


@app.post("/ops/simulate_sale")
def ops_simulate_sale():
    try:
        return _to_python(ops.simulate_sale())
    except KeyError:
        raise HTTPException(status_code=404, detail="No listed items available to simulate sale")


@app.post("/ops/seed", dependencies=[Depends(verify_admin_key)])
def ops_seed():
    try:
        return _to_python(ops.seed_database())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ops/reset", dependencies=[Depends(verify_admin_key)])
def ops_reset():
    return _to_python(ops.reset_database())
