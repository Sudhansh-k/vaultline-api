"""pages/landing.py — Vaultline landing page (session_state["view"] == "landing")."""
import sqlite3
import glob
import pandas as pd
import streamlit as st
from ui import (
    BRAND, BRASS, BRASS_TEXT, BG, PANEL, BORDER, TEXT, MUTED, GREEN,
    USD_TO_INR, inject_css, render_footer, fmt_inr,
)


# ──────────────────────────────────────────────────────────────────────────────
# Data helpers
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _live_stats() -> dict:
    conn = sqlite3.connect("market.db")
    row = pd.read_sql_query(
        "SELECT COUNT(*) as total, COUNT(DISTINCT item_id) as types, "
        "ROUND(AVG(days_to_sell),1) as avg_days FROM listings WHERE sold=1",
        conn,
    ).iloc[0]
    conn.close()
    return {
        "total":    int(row["total"]),
        "types":    int(row["types"]),
        "avg_days": float(row["avg_days"]),
    }


@st.cache_data(show_spinner=False)
def _featured_items(n: int = 5) -> list[dict]:
    """Return n catalogue items that have real images and decent prices."""
    csv_files = glob.glob("dataset_bricklink-scraper*.csv")
    if not csv_files:
        return []
    df = pd.read_csv(csv_files[0])
    # Filter: must have at least one lot and one price
    mask = (
        ((df["newLots"].fillna(0) + df["usedLots"].fillna(0)) > 0) &
        (
            (df["newAvgPrice"].notna() & (df["newAvgPrice"] > 0)) |
            (df["usedAvgPrice"].notna() & (df["usedAvgPrice"] > 0))
        ) &
        df["imageUrl"].notna() &
        (df["imageUrl"].str.startswith("http", na=False))
    )
    df = df[mask].copy()
    # Prefer items with higher new price (more recognisable sets)
    df["best_price"] = df["newAvgPrice"].fillna(df["usedAvgPrice"])
    df = df.sort_values("best_price", ascending=False).head(n)
    out = []
    for _, r in df.iterrows():
        out.append({
            "item_no":   r["itemNo"],
            "item_name": r["itemName"],
            "image_url": r["imageUrl"],
            "new_price_usd":  r["newAvgPrice"]  if pd.notna(r["newAvgPrice"])  else None,
            "used_price_usd": r["usedAvgPrice"] if pd.notna(r["usedAvgPrice"]) else None,
            "year": r["yearReleased"] if pd.notna(r.get("yearReleased")) else None,
        })
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Landing page renderer
# ──────────────────────────────────────────────────────────────────────────────
def render_landing() -> None:
    inject_css()

    # ── 1. HERO ───────────────────────────────────────────────────────────────
    featured = _featured_items(5)
    hero_image = featured[0] if featured else None

    hero_left, hero_right = st.columns([3, 2], gap="large")
    with hero_left:
        st.markdown(
            f"""
<div class="hero-fade">
  <div style="font-family:'Bricolage Grotesque',sans-serif;
              font-size:3rem;font-weight:700;color:{TEXT};
              line-height:1.1;letter-spacing:-0.03em;margin-bottom:0.75rem;">
    Know what your collectible is worth in seconds.
  </div>
  <div style="font-size:1.05rem;color:{MUTED};margin-bottom:2rem;max-width:480px;">
    Upload a photo, and our AI inspects condition and market data to give you
    an instant cash offer — no waiting, no haggling.
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
        if st.button("Start — get an offer", type="primary", key="hero_cta"):
            st.session_state["view"] = "app"
            st.rerun()

    with hero_right:
        if hero_image and hero_image["image_url"]:
            st.image(
                hero_image["image_url"],
                caption=hero_image["item_name"],
                use_container_width=True,
            )

    st.markdown(f"<hr style='border-color:{BORDER};margin:2.5rem 0;'>", unsafe_allow_html=True)

    # ── 2. WHAT IT DOES ───────────────────────────────────────────────────────
    st.markdown(
        f'<h2 style="font-family:\'Bricolage Grotesque\',sans-serif;'
        f'font-size:1.5rem;margin-bottom:1.25rem;">What it does</h2>',
        unsafe_allow_html=True,
    )
    feats = [
        ("AI condition check",
         "Gemini Vision inspects your photo for creases, tears, scratches and seal wear."),
        ("Fair market value",
         "An XGBoost model trained on real sale history estimates what your item is worth today."),
        ("Instant cash offer",
         "We quote you a bid price immediately — no negotiation, money arrives fast."),
        ("Expected time to sell",
         "A survival model tells us how long it typically takes to resell your item."),
    ]
    fc1, fc2, fc3, fc4 = st.columns(4, gap="small")
    for col, (title, body) in zip([fc1, fc2, fc3, fc4], feats):
        with col:
            with st.container(border=True):
                st.markdown(
                    f'<div style="font-family:\'Bricolage Grotesque\',sans-serif;'
                    f'font-size:0.95rem;font-weight:600;color:{TEXT};margin-bottom:0.4rem;">'
                    f'{title}</div>'
                    f'<div style="font-size:0.85rem;color:{MUTED};line-height:1.5;">{body}</div>',
                    unsafe_allow_html=True,
                )

    st.markdown(f"<hr style='border-color:{BORDER};margin:2.5rem 0;'>", unsafe_allow_html=True)

    # ── 3. HOW IT WORKS ───────────────────────────────────────────────────────
    st.markdown(
        f'<h2 style="font-family:\'Bricolage Grotesque\',sans-serif;'
        f'font-size:1.5rem;margin-bottom:1.25rem;">How it works</h2>',
        unsafe_allow_html=True,
    )
    steps = [
        ("1", "Pick the item",
         "Choose your LEGO set from the catalogue. We show the reference image and typical market price."),
        ("2", "Upload a photo",
         "Take a clear photo of your item. Show the box, packaging, and any visible wear."),
        ("3", "Get an offer",
         "Our AI checks condition and calculates an instant cash offer. Accept or walk away — no obligation."),
    ]
    s1, s2, s3 = st.columns(3, gap="medium")
    for col, (num, title, body) in zip([s1, s2, s3], steps):
        with col:
            with st.container(border=True):
                st.markdown(
                    f'<div style="font-family:\'Bricolage Grotesque\',sans-serif;'
                    f'font-size:2rem;font-weight:700;color:{BRASS};margin-bottom:0.35rem;">{num}</div>'
                    f'<div style="font-family:\'Bricolage Grotesque\',sans-serif;'
                    f'font-size:1rem;font-weight:600;color:{TEXT};margin-bottom:0.4rem;">{title}</div>'
                    f'<div style="font-size:0.85rem;color:{MUTED};line-height:1.5;">{body}</div>',
                    unsafe_allow_html=True,
                )

    st.markdown(f"<hr style='border-color:{BORDER};margin:2.5rem 0;'>", unsafe_allow_html=True)

    # ── 4. LIVE STATS ─────────────────────────────────────────────────────────
    stats = _live_stats()
    st.markdown(
        f'<h2 style="font-family:\'Bricolage Grotesque\',sans-serif;'
        f'font-size:1.5rem;margin-bottom:1.25rem;">By the numbers</h2>',
        unsafe_allow_html=True,
    )
    m1, m2, m3 = st.columns(3, gap="medium")
    m1.metric("Listings tracked", f"{stats['total']:,}")
    m2.metric("Item types", f"{stats['types']}")
    m3.metric("Average days to sell", f"{stats['avg_days']}")

    st.markdown(f"<hr style='border-color:{BORDER};margin:2.5rem 0;'>", unsafe_allow_html=True)

    # ── 5. WHAT WE BUY ────────────────────────────────────────────────────────
    st.markdown(
        f'<h2 style="font-family:\'Bricolage Grotesque\',sans-serif;'
        f'font-size:1.5rem;margin-bottom:1.25rem;">What we buy</h2>',
        unsafe_allow_html=True,
    )
    strip_items = featured  # already fetched
    if strip_items:
        cols = st.columns(len(strip_items), gap="small")
        for col, item in zip(cols, strip_items):
            with col:
                if item["image_url"] and str(item["image_url"]).startswith("http"):
                    st.image(item["image_url"], use_container_width=True)
                else:
                    st.markdown(
                        f'<div style="height:120px;background:{BORDER};border-radius:6px;'
                        f'display:flex;align-items:center;justify-content:center;'
                        f'color:{MUTED};font-size:0.8rem;">No image</div>',
                        unsafe_allow_html=True,
                    )
                price = item.get("new_price_usd") or item.get("used_price_usd")
                label = item["item_name"][:32] + ("…" if len(item["item_name"]) > 32 else "")
                price_str = f" · {fmt_inr(price)}" if price else ""
                st.markdown(
                    f'<div style="font-size:0.8rem;color:{TEXT};font-weight:500;'
                    f'margin-top:0.3rem;line-height:1.3;">{label}</div>'
                    f'<div style="font-size:0.75rem;color:{MUTED};">{price_str}</div>',
                    unsafe_allow_html=True,
                )

    st.markdown(f"<hr style='border-color:{BORDER};margin:2.5rem 0;'>", unsafe_allow_html=True)

    # ── 6. FAQ ────────────────────────────────────────────────────────────────
    st.markdown(
        f'<h2 style="font-family:\'Bricolage Grotesque\',sans-serif;'
        f'font-size:1.5rem;margin-bottom:1rem;">Common questions</h2>',
        unsafe_allow_html=True,
    )
    faqs = [
        (
            "How does the AI check condition?",
            "We send your photo to a vision model that looks for box creases, tears, dents, "
            "scratches, fading, and whether the original seal is intact. It returns a score "
            "from 1 (heavily damaged) to 10 (mint, sealed).",
        ),
        (
            "Why is the cash offer below the market price?",
            "Our offer is what we pay you instantly in cash. We then resell the item at a "
            "higher price to cover our costs and risk. The spread between our bid and our "
            "ask is how we operate sustainably.",
        ),
        (
            "How long does selling usually take?",
            f"Based on our sales data, the average time from listing to sale is "
            f"{stats['avg_days']} days. Fast-moving items sell in under two weeks; "
            f"rarer pieces can take longer.",
        ),
    ]
    for q, a in faqs:
        with st.expander(q):
            st.markdown(
                f'<p style="font-size:0.9rem;color:{MUTED};line-height:1.6;">{a}</p>',
                unsafe_allow_html=True,
            )

    render_footer()
