"""Run: uvicorn api:app --reload   (docs at http://localhost:8000/docs)"""
from vision.gemini_vision import predict_condition
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from common.db import connect
from pipeline import instant_offer

app = FastAPI(title="Collectibles Instant Offer")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Warehouse state lives in memory for the demo; move it to a DB table later.
STATE = {"capital": 500_000.0, "inventory": {}}


@app.get("/items")
def items():
    """Whitelisted items the customer can pick from."""
    with connect() as c:
        return [r[0] for r in c.execute("SELECT DISTINCT item_id FROM listings")]

@app.post("/offer")
async def offer(item_id: str = Form(...), image: UploadFile = File(...)):
    try:
        return instant_offer(item_id, await image.read(),
                             STATE["inventory"].get(item_id, 0), STATE["capital"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        print("offer failed:", e)
        raise HTTPException(503, "The vision service is busy right now. Please try again in a moment.")


@app.post("/accept")
def accept(item_id: str = Form(...), price: float = Form(...)):
    """Customer accepted the offer: pay out and add to inventory."""
    if price > STATE["capital"]:
        raise HTTPException(400, "Insufficient capital")
    STATE["capital"] -= price
    STATE["inventory"][item_id] = STATE["inventory"].get(item_id, 0) + 1
    return STATE

@app.get("/health")
def health():
    return {"ok": True}
import glob
import pandas as pd
from fastapi import HTTPException

USD_TO_INR = 88.0

@app.get("/catalog")
def catalog():
    # 1) preferred: the catalog table in market.db
    try:
        with connect() as c:
            cur = c.execute("SELECT item_id, item_no, name, image_url, new_price_inr, "
                            "used_price_inr, new_lots, used_lots FROM catalog")
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        if rows:
            return rows
    except Exception as e:
        print("catalog table failed:", e)

    # 2) fallback: build it from the BrickLink CSV in the repo
    files = sorted(glob.glob("dataset_bricklink-scraper_*.csv"))
    if not files:
        raise HTTPException(500, "No catalogue data found on the server")
    df = pd.read_csv(files[-1])
    for col in ["newAvgPrice", "usedAvgPrice", "newLots", "usedLots"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df[["newLots", "usedLots"]] = df[["newLots", "usedLots"]].fillna(0)
    df = df[(df["newLots"] + df["usedLots"]) >= 5].drop_duplicates("itemNo")
    out = pd.DataFrame({
        "item_id": "lego_" + df["itemNo"].astype(str).str.replace("-", "_"),
        "item_no": df["itemNo"].astype(str),
        "name": df["itemName"].astype(str),
        "image_url": df["imageUrl"],
        "new_price_inr": (df["newAvgPrice"] * USD_TO_INR).round(2),
        "used_price_inr": (df["usedAvgPrice"] * USD_TO_INR).round(2),
        "new_lots": df["newLots"].astype(int),
        "used_lots": df["usedLots"].astype(int),
    })
    return out.astype(object).where(out.notna(), None).to_dict("records")


@app.get("/stats")
def stats():
    with connect() as c:
        total, items, avg_days = c.execute(
            "SELECT COUNT(*), COUNT(DISTINCT item_id), ROUND(AVG(days_to_sell),1) "
            "FROM listings WHERE sold=1").fetchone()
    return {"listings": total, "items": items, "avg_days_to_sell": avg_days}
