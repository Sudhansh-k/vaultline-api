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

@app.get("/catalog")
def catalog():
    with connect() as c:
        cur = c.execute("SELECT item_id, item_no, name, image_url, new_price_inr, "
                        "used_price_inr, new_lots, used_lots FROM catalog")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
