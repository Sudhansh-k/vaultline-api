"""app.py — Vaultline entry point.

Routes between landing page and app (sell / catalogue / how it works)
using st.session_state["view"]. run_project.bat calls: streamlit run app.py
"""
import streamlit as st

# ── Page config must be the very first st.* call ─────────────────────────────
st.set_page_config(
    page_title="Vaultline",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Shared CSS (always injected) ──────────────────────────────────────────────
from ui import inject_css, render_footer, render_topbar, BRAND, BRASS, BORDER, TEXT, MUTED, PANEL

inject_css()

# ── Session state defaults ────────────────────────────────────────────────────
if "view" not in st.session_state:
    st.session_state["view"] = "landing"
if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = "sell"

# ══════════════════════════════════════════════════════════════════════════════
# LANDING VIEW
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state["view"] == "landing":
    from pages.landing import render_landing
    render_landing()

# ══════════════════════════════════════════════════════════════════════════════
# APP VIEW
# ══════════════════════════════════════════════════════════════════════════════
else:
    # ── Top bar with brand (click → landing) ─────────────────────────────────
    bar_left, bar_right = st.columns([1, 4])
    with bar_left:
        if st.button(BRAND, key="topbar_brand", use_container_width=False):
            st.session_state["view"] = "landing"
            st.rerun()

    st.markdown(
        f"<hr style='border-color:{BORDER};margin:0 0 1.25rem 0;'>",
        unsafe_allow_html=True,
    )

    # ── Tabs ─────────────────────────────────────────────────────────────────
    # Map active_tab to tab index
    tab_names  = ["Sell an item", "Catalogue", "How it works"]
    tab_map    = {"sell": 0, "catalogue": 1, "how": 2}
    active_idx = tab_map.get(st.session_state.get("active_tab", "sell"), 0)

    tab_sell, tab_cat, tab_how = st.tabs(tab_names)

    # Track which tab is active via session state
    with tab_sell:
        st.session_state["active_tab"] = "sell"
        from pages.sell import render_sell
        render_sell()

    with tab_cat:
        st.session_state["active_tab"] = "catalogue"
        from pages.catalogue import render_catalogue
        render_catalogue()

    with tab_how:
        st.session_state["active_tab"] = "how"
        from pages.how_it_works import render_how_it_works
        render_how_it_works()

    render_footer()
