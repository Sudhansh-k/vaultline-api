"""pages/how_it_works.py — Vaultline How it works tab."""
import streamlit as st
from ui import BRASS, BORDER, TEXT, MUTED, PANEL


def render_how_it_works() -> None:

    st.markdown(
        f'<h2 style="font-family:\'Bricolage Grotesque\',sans-serif;'
        f'font-size:1.6rem;font-weight:700;color:{TEXT};'
        f'margin-bottom:0.4rem;">How it works</h2>'
        f'<p style="color:{MUTED};font-size:0.95rem;margin-bottom:1.75rem;">'
        f'Three steps, no paperwork, no waiting.</p>',
        unsafe_allow_html=True,
    )

    # ── Step 1: Photo check ────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            f'<div style="display:flex;align-items:baseline;gap:0.75rem;margin-bottom:0.5rem;">'
            f'<span style="font-family:\'Bricolage Grotesque\',sans-serif;'
            f'font-size:1.75rem;font-weight:700;color:{BRASS};">1</span>'
            f'<span style="font-family:\'Bricolage Grotesque\',sans-serif;'
            f'font-size:1.1rem;font-weight:600;color:{TEXT};">Photo check</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<p style="color:{MUTED};font-size:0.92rem;line-height:1.7;margin:0;">'
            f'You upload a photo of your item. Our AI reads the image and looks for signs of wear. '
            f'Specifically, it checks for:</p>'
            f'<ul style="color:{MUTED};font-size:0.9rem;line-height:1.8;margin-top:0.5rem;">'
            f'<li>Box creases, dents, and corner damage</li>'
            f'<li>Tears or punctures in the packaging</li>'
            f'<li>Surface scratches and fading</li>'
            f'<li>Whether the original factory seal is intact</li>'
            f'<li>General handling wear</li>'
            f'</ul>'
            f'<p style="color:{MUTED};font-size:0.92rem;line-height:1.7;margin-top:0.5rem;">'
            f'The result is a condition score from 1 (heavily damaged) to 10 (mint and sealed). '
            f'A better score means a higher offer.</p>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

    # ── Step 2: Market comparison ──────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            f'<div style="display:flex;align-items:baseline;gap:0.75rem;margin-bottom:0.5rem;">'
            f'<span style="font-family:\'Bricolage Grotesque\',sans-serif;'
            f'font-size:1.75rem;font-weight:700;color:{BRASS};">2</span>'
            f'<span style="font-family:\'Bricolage Grotesque\',sans-serif;'
            f'font-size:1.1rem;font-weight:600;color:{TEXT};">Market comparison</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<p style="color:{MUTED};font-size:0.92rem;line-height:1.7;margin:0;">'
            f'We look up your item in our database of real past sales and compare it '
            f'with current market conditions — how many similar listings are active, '
            f'how much collector interest there is right now, and what season it is. '
            f'From that, we estimate a fair market value: what an informed buyer would '
            f'pay on the open market today.</p>'
            f'<p style="color:{MUTED};font-size:0.92rem;line-height:1.7;margin-top:0.5rem;">'
            f'We also calculate how long it typically takes to sell that item, which '
            f'affects how much risk we take on and therefore the spread we quote.</p>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

    # ── Step 3: Pricing ────────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown(
            f'<div style="display:flex;align-items:baseline;gap:0.75rem;margin-bottom:0.5rem;">'
            f'<span style="font-family:\'Bricolage Grotesque\',sans-serif;'
            f'font-size:1.75rem;font-weight:700;color:{BRASS};">3</span>'
            f'<span style="font-family:\'Bricolage Grotesque\',sans-serif;'
            f'font-size:1.1rem;font-weight:600;color:{TEXT};">Instant offer</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<p style="color:{MUTED};font-size:0.92rem;line-height:1.7;margin:0;">'
            f'We give you two numbers: our cash offer (what we pay you now) and '
            f'our resale price (what we list it for afterwards). '
            f'The gap between them covers storage, handling, and the risk that '
            f'the item takes longer to sell than expected. '
            f'There is no obligation — you can walk away at any point.</p>',
            unsafe_allow_html=True,
        )

    st.markdown(f"<hr style='border-color:{BORDER};margin:1.75rem 0;'>", unsafe_allow_html=True)

    # ── Technically curious expander ───────────────────────────────────────────
    with st.expander("For the technically curious"):
        st.markdown(
            f"""
<div style="font-size:0.88rem;color:{MUTED};line-height:1.7;">

**Condition scoring** is done by Gemini Vision with structured JSON output.
The model returns a `condition_score` (float, 1–10) and a list of `defects`
(short strings). Temperature is 0 for deterministic results.

**Fair market value** is predicted by an XGBoost regression model trained on
historical sale prices from the database. Features include the item's rolling
median sale price (lagged to avoid leakage), the condition score, month
seasonality (sin/cos encoding), search volume index, total active listings,
and average days on market — all joined from a market trends table.

**Liquidity** (expected days to sell) comes from a Weibull AFT survival model
fitted with lifelines. It handles censored observations (items still unsold)
and returns survival probabilities at 14, 30, and 60 days as well as an
expected sell duration.

**Spread quoting** is handled by a PPO reinforcement learning agent trained
in a custom Gymnasium environment. The agent observes inventory depth,
remaining capital, fair market value, and expected sell duration, then outputs
bid and ask spreads in [1%, 40%] around fair value. When no trained model is
present, a rule-based heuristic is used instead.

</div>
""",
            unsafe_allow_html=True,
        )
