"""Person 3 - Fair Market Value (XGBoost) + liquidity (Weibull AFT survival).

  python -m valuation.appraiser train
  python -m valuation.appraiser appraise lego_75192 7.8
"""
import sys
import joblib
import numpy as np
import pandas as pd
from lifelines import WeibullAFTFitter
from xgboost import XGBRegressor

from common.db import load_listings, load_trends

MODEL_PATH = "valuation/valuation_bundle.joblib"
FEATURES = ["base_price", "condition_score", "month_sin", "month_cos", "search_volume_index",
            "total_active_listings", "avg_days_on_market", "category_code"]
SURV_FEATURES = ["condition_score", "search_volume_index", "total_active_listings",
                 "avg_days_on_market", "log_base_price"]
HORIZONS = [14, 30, 60]


def _prep(listings, trends):
    """Join Table A + B on sale_date/category and add leakage-safe base price + seasonality."""
    df = listings.copy()
    df["sale_date"] = pd.to_datetime(df["sale_date"])
    t = trends.copy()
    t["date"] = pd.to_datetime(t["date"])
    df = df.sort_values("sale_date").reset_index(drop=True)
    df = pd.merge_asof(df, t.sort_values("date"), left_on="sale_date", right_on="date",
                       by="category", direction="backward")
    # median of the item's previous 10 sales only (shift(1) prevents target leakage)
    df["base_price"] = df.groupby("item_id")["sale_price"].transform(
        lambda s: s.shift(1).rolling(10, min_periods=1).median())
    m = df["sale_date"].dt.month
    df["month_sin"], df["month_cos"] = np.sin(2 * np.pi * m / 12), np.cos(2 * np.pi * m / 12)
    return df


def train(db_path=None, out=MODEL_PATH):
    df = _prep(load_listings(db_path), load_trends(db_path))
    df = df.dropna(subset=["condition_score", "base_price", "search_volume_index"])
    cat_map = {c: i for i, c in enumerate(sorted(df["category"].unique()))}
    df["category_code"] = df["category"].map(cat_map)

    # --- Fair value: time-ordered split (never validate on the past) ---
    cut = int(0.8 * len(df))
    tr, te = df.iloc[:cut], df.iloc[cut:]
    xgb = XGBRegressor(n_estimators=500, learning_rate=0.05, max_depth=5, subsample=0.8,
                       colsample_bytree=0.8, early_stopping_rounds=30)
    xgb.fit(tr[FEATURES], np.log(tr["sale_price"]),
            eval_set=[(te[FEATURES], np.log(te["sale_price"]))], verbose=False)
    pred = np.exp(xgb.predict(te[FEATURES]))
    mape = float(np.mean(np.abs(pred - te["sale_price"]) / te["sale_price"]))
    print(f"FMV hold-out MAPE: {mape:.1%}")

    # --- Liquidity: Weibull AFT with censoring (sold=0 rows are still-unsold listings) ---
    s = df[df["days_to_sell"] > 0].copy()
    s["log_base_price"] = np.log(s["base_price"])
    stats = s[SURV_FEATURES].agg(["mean", "std"])
    Z = (s[SURV_FEATURES] - stats.loc["mean"]) / stats.loc["std"].replace(0, 1)
    Z["days_to_sell"], Z["sold"] = s["days_to_sell"], s["sold"].fillna(1)
    aft = WeibullAFTFitter(penalizer=0.01)
    aft.fit(Z, duration_col="days_to_sell", event_col="sold")
    print(f"Survival concordance: {aft.concordance_index_:.3f}")

    joblib.dump({"xgb": xgb, "aft": aft, "cat_map": cat_map, "stats": stats}, out)
    print(f"saved -> {out}")


_bundle = None


def appraise_item(item_id: str, condition_score: float, db_path=None) -> dict:
    """-> {"fair_market_value", "expected_days_to_sell", "p_sell_within": {14, 30, 60}}"""
    global _bundle
    if _bundle is None:
        _bundle = joblib.load(MODEL_PATH)
    b = _bundle

    hist = load_listings(db_path).query("item_id == @item_id").sort_values("sale_date")
    if hist.empty:
        raise ValueError(f"Unknown item_id {item_id!r} - not whitelisted / no sales history")
    cat = hist["category"].iloc[-1]
    base = float(hist["sale_price"].tail(10).median())
    tr = load_trends(db_path).query("category == @cat").sort_values("date")
    macro = tr.iloc[-1]
    month = pd.Timestamp.today().month

    row = pd.DataFrame([{
        "base_price": base, "condition_score": condition_score,
        "month_sin": np.sin(2 * np.pi * month / 12), "month_cos": np.cos(2 * np.pi * month / 12),
        "search_volume_index": macro["search_volume_index"],
        "total_active_listings": macro["total_active_listings"],
        "avg_days_on_market": macro["avg_days_on_market"],
        "category_code": b["cat_map"][cat]}])
    fmv = float(np.exp(b["xgb"].predict(row[FEATURES])[0]))

    sv = row.assign(log_base_price=np.log(base))[SURV_FEATURES]
    sv = (sv - b["stats"].loc["mean"]) / b["stats"].loc["std"].replace(0, 1)
    sf = b["aft"].predict_survival_function(sv, times=HORIZONS)
    days = float(np.clip(b["aft"].predict_expectation(sv).iloc[0], 1, 365))
    return {"fair_market_value": round(fmv, 2),
            "expected_days_to_sell": round(days, 1),
            "p_sell_within": {t: round(float(1 - sf.loc[t].iloc[0]), 3) for t in HORIZONS}}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "train":
        train()
    elif len(sys.argv) > 3 and sys.argv[1] == "appraise":
        print(appraise_item(sys.argv[2], float(sys.argv[3])))
    else:
        print(__doc__)
