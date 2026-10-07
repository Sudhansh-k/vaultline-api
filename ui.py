"""ui.py — Shared presentation layer for Vaultline.

All CSS lives here. No backend logic. No API keys. No hardcoded prices.
"""
import requests, streamlit as st

@st.cache_data(show_spinner=False, ttl=86400)
def fetch_image(url: str):
    try:
        r = requests.get(url, timeout=8, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.bricklink.com/",
        })
        r.raise_for_status()
        return r.content
    except Exception:
        return None
import streamlit as st

# ── Brand constant (change in one place) ──────────────────────────────────────
BRAND = "Vaultline"
USD_TO_INR = 84.0   # 1 USD → INR; update as needed

# ── Colour tokens ─────────────────────────────────────────────────────────────
BG         = "#0A1A22"
PANEL      = "#11303C"
BORDER     = "#1F4A5A"
TEXT       = "#EAF1F4"
MUTED      = "#8FA7B2"
BRASS      = "#D6A84F"
BRASS_TEXT = "#1A1405"
GREEN      = "#4FCB8B"
ERROR      = "#F2766B"


# ──────────────────────────────────────────────────────────────────────────────
# CSS injection (single call from every page)
# ──────────────────────────────────────────────────────────────────────────────
def inject_css() -> None:
    st.markdown(
        f"""
<style>
/* ── Google Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..60,400;12..60,600;12..60,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stSidebarNav"],
.stDeployButton {{ visibility: hidden; height: 0; overflow: hidden; }}
[data-testid="collapsedControl"] {{ display: none; }}
section[data-testid="stSidebar"] {{ display: none; }}

/* ── Global ── */
html, body, [class*="css"] {{
    font-family: 'IBM Plex Sans', system-ui, sans-serif;
    background-color: {BG};
    color: {TEXT};
}}

/* ── Content width cap ── */
.main .block-container {{
    max-width: 1200px;
    padding: 0 1.5rem 4rem;
    margin: 0 auto;
}}

/* ── Headings use Bricolage ── */
h1, h2, h3, h4 {{
    font-family: 'Bricolage Grotesque', sans-serif;
    color: {TEXT};
    letter-spacing: -0.02em;
}}

/* ── Custom scrollbar ── */
::-webkit-scrollbar {{ width: 6px; }}
::-webkit-scrollbar-track {{ background: {BG}; }}
::-webkit-scrollbar-thumb {{ background: {BORDER}; border-radius: 3px; }}

/* ── st.container(border=True) → card style ── */
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] > div {{
    background: {PANEL} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 10px !important;
    padding: 1.5rem !important;
}}

/* ── Dark inputs / selectbox / file uploader ── */
[data-testid="stSelectbox"] > div > div,
[data-baseweb="select"] > div {{
    background-color: {PANEL} !important;
    border-color: {BORDER} !important;
    color: {TEXT} !important;
}}
[data-baseweb="select"] svg {{ fill: {MUTED}; }}
[data-baseweb="popover"] ul li {{
    background: {PANEL} !important;
    color: {TEXT} !important;
}}
[data-testid="stFileUploader"] {{
    background: {PANEL};
    border: 1px dashed {BORDER};
    border-radius: 8px;
    padding: 0.75rem;
}}
[data-testid="stFileUploader"] label {{ color: {MUTED} !important; }}
[data-testid="stFileUploader"] button {{
    background: {PANEL};
    border: 1px solid {BORDER};
    color: {TEXT};
}}

/* ── Primary button → brass ── */
.stButton > button[kind="primary"] {{
    background: {BRASS} !important;
    color: {BRASS_TEXT} !important;
    border: none !important;
    font-weight: 600;
    border-radius: 8px;
    padding: 0.55rem 1.5rem;
    font-family: 'IBM Plex Sans', sans-serif;
    cursor: pointer;
}}
.stButton > button[kind="primary"]:disabled {{
    background: {BORDER} !important;
    color: {MUTED} !important;
    cursor: not-allowed;
}}
/* ── Secondary / default button ── */
.stButton > button:not([kind="primary"]) {{
    background: transparent !important;
    border: 1px solid {BORDER} !important;
    color: {TEXT} !important;
    border-radius: 8px;
}}
.stButton > button:not([kind="primary"]):hover {{
    border-color: {BRASS} !important;
    color: {BRASS} !important;
}}

/* ── Tabs ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{
    background: transparent;
    border-bottom: 1px solid {BORDER};
    gap: 0;
}}
[data-testid="stTabs"] [data-baseweb="tab"] {{
    background: transparent;
    color: {MUTED};
    border-bottom: 2px solid transparent;
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 500;
    padding: 0.6rem 1.25rem;
    transition: color .15s;
}}
[data-testid="stTabs"] [aria-selected="true"] {{
    color: {BRASS} !important;
    border-bottom-color: {BRASS} !important;
    background: transparent !important;
}}

/* ── Expander ── */
[data-testid="stExpander"] {{
    background: {PANEL};
    border: 1px solid {BORDER} !important;
    border-radius: 8px;
}}
[data-testid="stExpander"] summary {{
    color: {MUTED};
    font-size: 0.88rem;
}}

/* ── Divider ── */
hr {{ border-color: {BORDER}; margin: 1.25rem 0; }}

/* ── st.metric ── */
[data-testid="stMetric"] {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 1.1rem 1.25rem;
}}
[data-testid="stMetricLabel"] {{ color: {MUTED}; font-size: 0.78rem; }}
[data-testid="stMetricValue"] {{
    font-family: 'Bricolage Grotesque', sans-serif;
    color: {TEXT};
    font-size: 1.6rem;
}}

/* ── Spinner ── */
[data-testid="stSpinner"] {{ color: {BRASS}; }}

/* ── Progress bar (condition meter) ── */
[data-testid="stProgress"] > div > div > div {{
    background: {BRASS} !important;
}}
[data-testid="stProgress"] > div > div {{
    background: {BORDER} !important;
    border-radius: 99px;
}}

/* ── Image captions ── */
[data-testid="caption"] {{ color: {MUTED}; font-size: 0.78rem; }}

/* ── Tables inside expanders ── */
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 0.4rem 0.75rem; border-bottom: 1px solid {BORDER}; text-align: left; font-size: 0.88rem; }}
th {{ color: {MUTED}; font-weight: 500; }}

/* ── Focus visible ── */
button:focus-visible, input:focus-visible, select:focus-visible {{
    outline: 2px solid {BRASS};
    outline-offset: 2px;
}}

/* ── Hero fade-in ── */
@keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(18px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
.hero-fade {{ animation: fadeUp .55s ease both; }}

/* ── Responsive ── */
@media (max-width: 720px) {{
    .offer-hero-amount {{ font-size: 44px !important; }}
}}
</style>
""",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Topbar (app view only)
# ──────────────────────────────────────────────────────────────────────────────
def render_topbar() -> None:
    """Brand on the left; returns to landing when clicked."""
    st.markdown(
        f"""
<div style="
  display:flex; align-items:center; justify-content:space-between;
  padding: 0.9rem 0 0.9rem 0;
  border-bottom: 1px solid {BORDER};
  margin-bottom: 1.5rem;
">
  <span style="
    font-family:'Bricolage Grotesque',sans-serif;
    font-size:1.35rem; font-weight:700; color:{TEXT};
    letter-spacing:-0.03em; cursor:pointer;
  " onclick="void(0)">{BRAND}</span>
</div>
""",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Footer
# ──────────────────────────────────────────────────────────────────────────────
def render_footer() -> None:
    st.markdown(
        f"""
<div style="
  margin-top:3.5rem;
  padding: 1.25rem 0;
  border-top: 1px solid {BORDER};
  display:flex; align-items:center; justify-content:space-between;
  flex-wrap:wrap; gap:0.5rem;
">
  <span style="font-family:'Bricolage Grotesque',sans-serif;
               font-size:1rem; font-weight:700; color:{TEXT};">{BRAND}</span>
  <span style="font-size:0.78rem; color:{MUTED}; max-width:520px; text-align:right;">
    Offers are estimates from your photo and may change after in-person inspection.
  </span>
</div>
""",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Number formatting
# ──────────────────────────────────────────────────────────────────────────────
def fmt_inr(amount_usd: float, already_inr: bool = False) -> str:
    """Format as ₹ with Indian digit grouping. No decimals."""
    val = int(round(amount_usd if already_inr else amount_usd * USD_TO_INR))
    s = str(val)
    if len(s) <= 3:
        return f"₹{s}"
    last3 = s[-3:]
    rest = s[:-3]
    groups = []
    while len(rest) > 2:
        groups.append(rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.append(rest)
    return f"₹{','.join(reversed(groups))},{last3}"


# ──────────────────────────────────────────────────────────────────────────────
# Pill badge
# ──────────────────────────────────────────────────────────────────────────────
def pill_html(label: str) -> str:
    action = label.upper()
    if "NARROW" in action:
        bg, fg = "#1E3A5F", "#7EB8F7"
    elif "WIDE" in action or "WIDEN" in action:
        bg, fg = "#3D2900", "#D6A84F"
    elif "STOP" in action:
        bg, fg = "#3D0A00", "#F2766B"
    else:
        bg, fg = "#1F4A5A", "#8FA7B2"
    return (
        f'<span style="background:{bg};color:{fg};font-size:0.75rem;font-weight:600;'
        f'padding:0.2rem 0.7rem;border-radius:99px;display:inline-block;">{label}</span>'
    )


# ──────────────────────────────────────────────────────────────────────────────
# Condition meter
# ──────────────────────────────────────────────────────────────────────────────
def render_condition_meter(score: float) -> None:
    pct = int((score / 10) * 100)
    st.markdown(
        f"""
<div style="margin:0.25rem 0 0.75rem 0;">
  <div style="display:flex;justify-content:space-between;margin-bottom:0.3rem;">
    <span style="font-size:0.8rem;color:{MUTED};">Condition</span>
    <span style="font-size:0.8rem;font-weight:600;color:{TEXT};">{score}/10</span>
  </div>
  <div style="height:8px;background:{BORDER};border-radius:99px;overflow:hidden;">
    <div style="height:100%;width:{pct}%;background:{BRASS};border-radius:99px;"></div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Offer card (right column, post-evaluation)
# ──────────────────────────────────────────────────────────────────────────────
def render_offer_card(out: dict) -> None:
    cond   = out["condition"]
    val    = out["valuation"]
    score  = cond["condition_score"]
    defects = cond.get("defects", [])
    bid    = out["offer_to_customer"]
    ask    = out["list_price"]
    action = out["action"]
    fmv    = val["fair_market_value"]
    days   = val["expected_days_to_sell"]

    # Hero cash offer
    st.markdown(
        f"""
<div class="hero-fade" style="margin-bottom:1rem;">
  <div style="font-size:0.78rem;color:{MUTED};margin-bottom:0.2rem;">Instant cash offer</div>
  <div class="offer-hero-amount" style="
    font-family:'Bricolage Grotesque',sans-serif;
    font-size:64px;font-weight:700;color:{GREEN};
    line-height:1;letter-spacing:-0.03em;">
    {fmt_inr(bid, already_inr=True)}
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    render_condition_meter(score)

    # Defects
    if defects:
        items_html = "".join(
            f'<li style="color:{MUTED};font-size:0.87rem;padding:0.2rem 0;'
            f'border-bottom:1px solid {BORDER};list-style:none;">'
            f'<span style="color:#C95A00;margin-right:0.4rem;">&#9679;</span>{d}</li>'
            for d in defects
        )
        st.markdown(
            f'<ul style="padding:0;margin:0 0 1rem 0;">{items_html}</ul>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<p style="color:{GREEN};font-size:0.87rem;margin-bottom:1rem;">No visible defects detected.</p>',
            unsafe_allow_html=True,
        )

    st.markdown(f"<hr style='border-color:{BORDER};margin:0.75rem 0;'>", unsafe_allow_html=True)

    # Summary grid (2×2)
    g1, g2 = st.columns(2)
    with g1:
        st.markdown(
            f'<div style="font-size:0.73rem;color:{MUTED};margin-bottom:0.1rem;">Fair market value</div>'
            f'<div style="font-size:1rem;font-weight:600;color:{TEXT};">{fmt_inr(fmv, already_inr=True)}</div>',
            unsafe_allow_html=True,
        )
    with g2:
        st.markdown(
            f'<div style="font-size:0.73rem;color:{MUTED};margin-bottom:0.1rem;">Our resale price</div>'
            f'<div style="font-size:1rem;font-weight:600;color:{TEXT};">{fmt_inr(ask, already_inr=True)}</div>',
            unsafe_allow_html=True,
        )
    g3, g4 = st.columns(2)
    with g3:
        st.markdown(
            f'<div style="font-size:0.73rem;color:{MUTED};margin-bottom:0.1rem;">Expected days to sell</div>'
            f'<div style="font-size:1rem;font-weight:600;color:{TEXT};">{days} days</div>',
            unsafe_allow_html=True,
        )
    with g4:
        st.markdown(
            f'<div style="font-size:0.73rem;color:{MUTED};margin-bottom:0.1rem;">Spread action</div>'
            f'<div style="margin-top:0.15rem;">{pill_html(action)}</div>',
            unsafe_allow_html=True,
        )

    # Expander with raw numbers
    with st.expander("How we calculated this"):
        st.markdown(
            f"""
| Field | Value |
|---|---|
| Condition score | {score}/10 |
| Defects | {', '.join(defects) if defects else 'None'} |
| Fair market value | {fmt_inr(fmv, already_inr=True)} |
| Instant cash offer (bid) | {fmt_inr(bid, already_inr=True)} |
| Our resale price (ask) | {fmt_inr(ask, already_inr=True)} |
| Spread action | {action} |
| Expected days to sell | {days} |
"""
        )


# ──────────────────────────────────────────────────────────────────────────────
# Error display
# ──────────────────────────────────────────────────────────────────────────────
def render_error(title: str, body: str) -> None:
    st.markdown(
        f"""
<div style="background:#2A0A08;border:1px solid {ERROR};border-radius:8px;
            padding:1rem 1.25rem;margin-top:0.5rem;">
  <div style="font-weight:600;color:{ERROR};margin-bottom:0.2rem;">{title}</div>
  <div style="font-size:0.88rem;color:{MUTED};">{body}</div>
</div>
""",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Catalogue item card (used in catalogue page)
# ──────────────────────────────────────────────────────────────────────────────
def catalogue_card(item: dict, card_key: str) -> None:
    """
    item keys: item_no, item_name, image_url, new_price_usd, used_price_usd,
               new_lots, used_lots, year
    """
    with st.container(border=True, key=card_key):
        # Image
        img = item.get("image_url", "")
        if img and str(img).startswith("http"):
            st.image(img, use_container_width=True)
        else:
            # Neutral placeholder
            st.markdown(
                f'<div style="height:140px;background:{BORDER};border-radius:6px;'
                f'display:flex;align-items:center;justify-content:center;'
                f'color:{MUTED};font-size:0.8rem;">No image</div>',
                unsafe_allow_html=True,
            )

        # Name + ID
        name = item.get("item_name", item.get("item_no", "Unknown"))
        item_no = item.get("item_no", "")
        st.markdown(
            f'<div style="font-family:\'Bricolage Grotesque\',sans-serif;'
            f'font-size:0.95rem;font-weight:600;color:{TEXT};'
            f'margin:0.5rem 0 0.1rem 0;line-height:1.3;">{name}</div>'
            f'<div style="font-size:0.73rem;color:{MUTED};margin-bottom:0.5rem;">{item_no}</div>',
            unsafe_allow_html=True,
        )

        # Prices
        new_p  = item.get("new_price_usd")
        used_p = item.get("used_price_usd")
        price_parts = []
        if new_p:
            price_parts.append(f'<span style="color:{TEXT};font-weight:600;">{fmt_inr(new_p)}</span>'
                               f'<span style="color:{MUTED};font-size:0.75rem;"> new</span>')
        if used_p:
            price_parts.append(f'<span style="color:{MUTED};font-weight:500;">{fmt_inr(used_p)}</span>'
                               f'<span style="color:{MUTED};font-size:0.75rem;"> used</span>')
        if price_parts:
            st.markdown(
                '<div style="display:flex;gap:0.75rem;align-items:baseline;flex-wrap:wrap;margin-bottom:0.5rem;">'
                + " &nbsp;·&nbsp; ".join(price_parts) + "</div>",
                unsafe_allow_html=True,
            )

        # Year
        year = item.get("year")
        if year:
            st.markdown(
                f'<div style="font-size:0.73rem;color:{MUTED};margin-bottom:0.6rem;">Released {int(year)}</div>',
                unsafe_allow_html=True,
            )

        # Sell button
        item_id_db = f"lego_{str(item_no).replace('-', '_')}"
        if st.button("Sell this item", key=f"sell_{card_key}", use_container_width=True):
            st.session_state["preselected_item"] = item_id_db
            st.session_state["active_tab"]       = "sell"
            st.session_state["view"]             = "app"
            st.rerun()
