"""pages/sell.py — Vaultline Sell an item tab."""
import sqlite3
import requests
import pandas as pd
import streamlit as st
from ui import (
    BRAND, BRASS, BRASS_TEXT, BG, PANEL, BORDER, TEXT, MUTED, GREEN,
    inject_css, render_footer, fmt_inr, render_offer_card, render_error,
)

API_URL = "http://127.0.0.1:8000/offer"


# ──────────────────────────────────────────────────────────────────────────────
# Data
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _get_catalog() -> pd.DataFrame:
    conn = sqlite3.connect("market.db")
    df = pd.read_sql_query(
        """
        SELECT l.item_id,
               ROUND(AVG(l.sale_price), 2) AS sale_price,
               c.name                      AS name,
               c.image_url                 AS image_path
        FROM listings l
        LEFT JOIN catalog c ON c.item_id = l.item_id
        WHERE l.sale_price > 0
        GROUP BY l.item_id
        ORDER BY l.item_id
        """,
        conn,
    )
    conn.close()
    return df

# ──────────────────────────────────────────────────────────────────────────────
# Sell page renderer
# ──────────────────────────────────────────────────────────────────────────────
def render_sell() -> None:
    catalog = _get_catalog()

    if catalog.empty:
        render_error(
            "No items found",
            "Run load_data.py first to populate market.db.",
        )
        return

    left, right = st.columns([1, 1], gap="large")

    # ── LEFT: Your item ───────────────────────────────────────────────────────
    with left:
        with st.container(border=True, key="sell_left_card"):
            st.markdown(
                f'<div style="font-family:\'Bricolage Grotesque\',sans-serif;'
                f'font-size:1.05rem;font-weight:600;color:{BRASS};'
                f'margin-bottom:1rem;padding-bottom:0.6rem;'
                f'border-bottom:1px solid {BORDER};">Your item</div>',
                unsafe_allow_html=True,
            )

            # Preselect from catalogue navigation
            preselected = st.session_state.get("preselected_item")
            item_list   = catalog["item_id"].tolist()
            default_idx = 0
            if preselected and preselected in item_list:
                default_idx = item_list.index(preselected)

            selected_item = st.selectbox(
                "Catalog item",
                options=item_list,
                index=default_idx,
                key="sell_item_select",
                label_visibility="visible",
            )
            # Clear preselected after first render
            if "preselected_item" in st.session_state:
                del st.session_state["preselected_item"]

            item_row = catalog[catalog["item_id"] == selected_item].iloc[0]

            # Reference image + meta side by side
            img_col, meta_col = st.columns([1, 1], gap="small")
            with img_col:
                img_path = item_row["image_path"]
                if img_path and str(img_path).startswith("http"):
                    st.image(img_path, caption="Reference image", use_container_width=True)
                else:
                    st.markdown(
                        f'<div style="height:140px;background:{BORDER};border-radius:6px;'
                        f'display:flex;align-items:center;justify-content:center;'
                        f'color:{MUTED};font-size:0.8rem;">No reference image</div>',
                        unsafe_allow_html=True,
                    )
            with meta_col:
                st.markdown(
                    f'<div style="margin-top:0.5rem;">'
                    f'<div style="font-size:0.73rem;color:{MUTED};margin-bottom:0.1rem;">Item ID</div>'
                    f'<div style="font-family:\'IBM Plex Mono\',monospace;font-size:0.82rem;'
                    f'background:{BORDER};padding:0.15rem 0.4rem;border-radius:4px;'
                    f'color:{TEXT};display:inline-block;margin-bottom:0.65rem;">'
                    f'{item_row["item_id"]}</div><br>'
                    f'<div style="font-size:0.73rem;color:{MUTED};margin-bottom:0.1rem;">Typical price</div>'
                    f'<div style="font-size:1rem;font-weight:600;color:{TEXT};">'
                    f'{fmt_inr(item_row["sale_price"], already_inr=True)}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            st.markdown(
                f"<hr style='border-color:{BORDER};margin:0.9rem 0;'>",
                unsafe_allow_html=True,
            )

            # Photo uploader
            uploaded_file = st.file_uploader(
                "Condition photo (jpg or png)",
                type=["jpg", "jpeg", "png"],
                key="sell_photo_upload",
                label_visibility="visible",
                help="A clear photo of the item and its packaging.",
            )
            if uploaded_file:
                st.image(
                    uploaded_file,
                    caption="Your submitted photo",
                    use_container_width=False,
                    width=200,
                )

            st.markdown("<div style='margin-top:1rem;'>", unsafe_allow_html=True)
            get_offer_btn = st.button(
                "Get my offer",
                type="primary",
                use_container_width=True,
                disabled=(uploaded_file is None),
                key="sell_get_offer",
            )
            st.markdown("</div>", unsafe_allow_html=True)

    # ── RIGHT: Your offer ─────────────────────────────────────────────────────
    with right:
        with st.container(border=True, key="sell_right_card"):
            st.markdown(
                f'<div style="font-family:\'Bricolage Grotesque\',sans-serif;'
                f'font-size:1.05rem;font-weight:600;color:{BRASS};'
                f'margin-bottom:1rem;padding-bottom:0.6rem;'
                f'border-bottom:1px solid {BORDER};">Your offer</div>',
                unsafe_allow_html=True,
            )

            if get_offer_btn:
                with st.spinner("Checking condition and value..."):
                    files = {
                        "image": (
                            uploaded_file.name,
                            uploaded_file.getvalue(),
                            uploaded_file.type,
                        )
                    }
                    data = {"item_id": selected_item}
                    try:
                        res = requests.post(API_URL, data=data, files=files, timeout=120)
                        if res.status_code == 200:
                            out = res.json()
                            render_offer_card(out)
                        else:
                            render_error(
                                "Appraisal failed",
                                f"The service returned an unexpected response ({res.status_code}). "
                                "Please try again in a moment.",
                            )
                    except requests.exceptions.ConnectionError:
                        render_error(
                            "Cannot reach the appraisal service",
                            "Make sure the backend is running: "
                            "<code>uvicorn api:app --reload</code>",
                        )
                    except requests.exceptions.Timeout:
                        render_error(
                            "The vision service is busy",
                            "The request took too long. Try again in a minute.",
                        )
                    except Exception as e:
                        render_error(
                            "Something went wrong",
                            str(e)[:200] + " — please check your setup and try again.",
                        )
            else:
                # Calm empty state
                st.markdown(
                    f"""
<div style="text-align:center;padding:4rem 1rem;color:{MUTED};">
  <svg width="44" height="44" viewBox="0 0 24 24" fill="none"
       stroke="{BORDER}" stroke-width="1.4" stroke-linecap="round"
       stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"
       style="margin-bottom:0.75rem;display:block;margin-left:auto;margin-right:auto;">
    <rect x="3" y="3" width="18" height="18" rx="2"/>
    <path d="M3 9h18M9 21V9"/>
  </svg>
  <p style="margin:0;font-size:0.9rem;">
    Your offer will appear here after evaluation.
  </p>
</div>
""",
                    unsafe_allow_html=True,
                )
