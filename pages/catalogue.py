"""pages/catalogue.py — Vaultline Catalogue tab."""
import glob
import pandas as pd
import streamlit as st
from ui import (
    BRASS, BORDER, TEXT, MUTED, GREEN, PANEL,
    fmt_inr, catalogue_card,
)


# ──────────────────────────────────────────────────────────────────────────────
# Data
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _load_catalogue() -> pd.DataFrame:
    csv_files = glob.glob("dataset_bricklink-scraper*.csv")
    if not csv_files:
        return pd.DataFrame()
    df = pd.read_csv(csv_files[0])

    # Keep only rows with at least one lot and at least one price
    mask = (
        ((df["newLots"].fillna(0) + df["usedLots"].fillna(0)) > 0) &
        (
            (df["newAvgPrice"].notna() & (df["newAvgPrice"] > 0)) |
            (df["usedAvgPrice"].notna() & (df["usedAvgPrice"] > 0))
        )
    )
    df = df[mask].copy()

    # Normalise
    df["new_price_usd"]  = pd.to_numeric(df["newAvgPrice"],  errors="coerce")
    df["used_price_usd"] = pd.to_numeric(df["usedAvgPrice"], errors="coerce")
    df["new_lots"]       = pd.to_numeric(df["newLots"],  errors="coerce").fillna(0)
    df["used_lots"]      = pd.to_numeric(df["usedLots"], errors="coerce").fillna(0)
    df["year"]           = pd.to_numeric(df["yearReleased"], errors="coerce")
    df["image_url"]      = df["imageUrl"].fillna("")
    df["item_no"]        = df["itemNo"].astype(str)
    df["item_name"]      = df["itemName"].astype(str)
    # Category tag — all CSV items are LEGO
    df["category"]       = "lego"
    # Best price for sort
    df["best_price"]     = df["new_price_usd"].fillna(df["used_price_usd"])

    return df.reset_index(drop=True)


# ──────────────────────────────────────────────────────────────────────────────
# Catalogue page renderer
# ──────────────────────────────────────────────────────────────────────────────
def render_catalogue() -> None:
    df = _load_catalogue()

    if df.empty:
        st.markdown(
            f'<p style="color:{MUTED};">No catalogue data found. '
            f'Check that the BrickLink CSV is in the project folder.</p>',
            unsafe_allow_html=True,
        )
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    filter_col, search_col = st.columns([1, 2], gap="medium")
    with filter_col:
        cat_choice = st.radio(
            "Category",
            options=["All", "LEGO", "Watch"],
            horizontal=True,
            key="cat_filter",
            label_visibility="visible",
        )
    with search_col:
        search_query = st.text_input(
            "Search items",
            placeholder="Search by name or item number…",
            key="cat_search",
            label_visibility="visible",
        )

    # Apply filters
    filtered = df.copy()
    if cat_choice == "Watch":
        # CSV has no watch data; show message
        st.markdown(
            f'<p style="color:{MUTED};margin-top:1rem;">No watch data in the current catalogue CSV.</p>',
            unsafe_allow_html=True,
        )
        return

    if search_query:
        q = search_query.lower()
        filtered = filtered[
            filtered["item_name"].str.lower().str.contains(q, na=False) |
            filtered["item_no"].str.lower().str.contains(q, na=False)
        ]

    # Sort: highest price first (shows iconic sets at top)
    filtered = filtered.sort_values("best_price", ascending=False).reset_index(drop=True)

    st.markdown(
        f'<div style="font-size:0.82rem;color:{MUTED};margin:0.5rem 0 1.25rem 0;">'
        f'Showing {len(filtered)} items</div>',
        unsafe_allow_html=True,
    )

    if filtered.empty:
        st.markdown(
            f'<p style="color:{MUTED};">No items match your search.</p>',
            unsafe_allow_html=True,
        )
        return

    # ── Grid: 3 per row ───────────────────────────────────────────────────────
    n_cols = 3
    rows = [filtered.iloc[i:i + n_cols] for i in range(0, len(filtered), n_cols)]

    for row_idx, row_df in enumerate(rows):
        cols = st.columns(n_cols, gap="medium")
        for col_idx, (_, item_row) in enumerate(row_df.iterrows()):
            with cols[col_idx]:
                card_key = f"cat_{row_idx}_{col_idx}"
                item_dict = {
                    "item_no":        item_row["item_no"],
                    "item_name":      item_row["item_name"],
                    "image_url":      item_row["image_url"],
                    "new_price_usd":  item_row["new_price_usd"]  if pd.notna(item_row["new_price_usd"])  else None,
                    "used_price_usd": item_row["used_price_usd"] if pd.notna(item_row["used_price_usd"]) else None,
                    "year":           item_row["year"] if pd.notna(item_row["year"]) else None,
                    "new_lots":       int(item_row["new_lots"]),
                    "used_lots":      int(item_row["used_lots"]),
                }
                catalogue_card(item_dict, card_key)
