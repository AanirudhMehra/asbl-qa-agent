"""
ASBL QA Agent — Streamlit Dashboard
Run: streamlit run streamlit_app.py
"""

import os
import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient

# ── Env ──────────────────────────────────────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
MONGO_URI_QA = os.getenv("MONGO_URI_QA")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ASBL QA Dashboard",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
/* ---------- Global ---------- */
html, body, [class*="css"]  { font-family: 'Segoe UI', sans-serif; }

/* ---------- Metric cards ---------- */
[data-testid="metric-container"] {
    background: #ffffff;
    border: 1px solid #dde3ed;
    border-radius: 10px;
    padding: 16px 20px;
}
[data-testid="metric-container"] label {
    color: #5a6070;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    font-weight: 600;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #1a2d5a;
    font-size: 1.9rem;
    font-weight: 700;
}

/* ---------- Section headings ---------- */
.section-header {
    font-size: 1.05rem;
    font-weight: 700;
    color: #1a2d5a;
    border-bottom: 2.5px solid #e86219;
    padding-bottom: 6px;
    margin-bottom: 16px;
    display: inline-block;
}

/* ---------- PASS / FAIL / SKIPPED badges ---------- */
.badge-pass    { background:#d4edda; color:#155724; padding:2px 8px;
                 border-radius:4px; font-size:.75rem; font-weight:700; }
.badge-fail    { background:#f8d7da; color:#721c24; padding:2px 8px;
                 border-radius:4px; font-size:.75rem; font-weight:700; }
.badge-skipped { background:#e2e3e5; color:#383d41; padding:2px 8px;
                 border-radius:4px; font-size:.75rem; font-weight:700; }

/* ---------- Urgency / severity chips ---------- */
.chip-high   { background:#fde8e8; color:#c0392b; padding:2px 7px;
               border-radius:3px; font-size:.72rem; font-weight:700; }
.chip-medium { background:#fff3cd; color:#856404; padding:2px 7px;
               border-radius:3px; font-size:.72rem; font-weight:700; }
.chip-low    { background:#d4edda; color:#155724; padding:2px 7px;
               border-radius:3px; font-size:.72rem; font-weight:700; }

/* ---------- Fix / problem cards ---------- */
.problem-card {
    background:#fff;
    border:1px solid #dde3ed;
    border-radius:8px;
    padding:14px 18px;
    margin-bottom:12px;
}
.fix-card {
    background:#f7f9fc;
    border:1px solid #dde3ed;
    border-left:4px solid #e86219;
    border-radius:6px;
    padding:12px 16px;
    margin-bottom:10px;
}
.fix-outcome { color:#1a7a45; font-size:.82rem; margin-top:4px; }

/* ---------- Refresh note ---------- */
.refresh-note {
    font-size:.73rem; color:#9ca3af; text-align:right;
    margin-bottom:8px;
}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
    background:#f7f9fc;
}
</style>
""",
    unsafe_allow_html=True,
)

# ═════════════════════════════════════════════════════════════════════════════
# MongoDB connection (cached resource — one connection for the session)
# ═════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def get_client() -> MongoClient:
    if not MONGO_URI_QA:
        st.error("MONGO_URI_QA not set. Add it to your .env file.")
        st.stop()
    return MongoClient(MONGO_URI_QA, serverSelectionTimeoutMS=8000)


def get_db():
    return get_client()["qa_results"]


# ═════════════════════════════════════════════════════════════════════════════
# Cached query helpers  (args are primitives so cache works correctly)
# ═════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def fetch_chatbot_qa(days: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    docs = list(
        get_db()["chatbot_qa"].find(
            {"evaluated_at": {"$gte": cutoff}},
            sort=[("evaluated_at", -1)],
            limit=5000,
        )
    )
    for d in docs:
        d.pop("_id", None)
    return docs


@st.cache_data(ttl=300)
def fetch_voice_qa(days: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    docs = list(
        get_db()["voice_qa"].find(
            {"evaluated_at": {"$gte": cutoff}},
            sort=[("evaluated_at", -1)],
            limit=5000,
        )
    )
    for d in docs:
        d.pop("_id", None)
    return docs


@st.cache_data(ttl=300)
def fetch_analytics_runs(days: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    docs = list(
        get_db()["analytics_runs"].find(
            {"run_at": {"$gte": cutoff}},
            sort=[("run_at", -1)],
            limit=500,
        )
    )
    for d in docs:
        d.pop("_id", None)
    return docs


@st.cache_data(ttl=300)
def fetch_feedback(days: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    docs = list(
        get_db()["feedback"].find(
            {"submitted_at": {"$gte": cutoff}},
            sort=[("submitted_at", -1)],
            limit=200,
        )
    )
    for d in docs:
        d.pop("_id", None)
    return docs


@st.cache_data(ttl=300)
def fetch_recommendations(days: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    docs = list(
        get_db()["recommendations"].find(
            {"generated_at": {"$gte": cutoff}},
            sort=[("generated_at", -1)],
            limit=100,
        )
    )
    for d in docs:
        d.pop("_id", None)
    return docs


# ═════════════════════════════════════════════════════════════════════════════
# Helper utilities
# ═════════════════════════════════════════════════════════════════════════════

def avg_score(docs: list[dict]) -> float | None:
    """Average score of PASS/FAIL docs (excludes SKIPPED)."""
    scores = [
        d.get("score")
        for d in docs
        if d.get("status") in ("PASS", "FAIL") and isinstance(d.get("score"), (int, float))
    ]
    return round(sum(scores) / len(scores), 1) if scores else None


def health_color(score) -> str:
    if score is None:
        return "#9ca3af"
    if score >= 7:
        return "#1a7a45"
    if score >= 5:
        return "#d68910"
    return "#c0392b"


def fmt_score(score) -> str:
    return f"{score}/10" if score is not None else "–/10"


def parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def issue_types_from_docs(docs: list[dict]) -> list[str]:
    types: set[str] = set()
    for d in docs:
        for iss in d.get("issues") or []:
            t = iss.get("type")
            if t:
                types.add(t)
    return sorted(types)


def severity_badge(sev: str) -> str:
    sev = (sev or "").upper()
    cls = {"HIGH": "chip-high", "MEDIUM": "chip-medium", "LOW": "chip-low"}.get(sev, "chip-low")
    return f'<span class="{cls}">{sev}</span>'


def status_badge(status: str) -> str:
    s = (status or "").upper()
    cls = {"PASS": "badge-pass", "FAIL": "badge-fail", "SKIPPED": "badge-skipped"}.get(s, "badge-skipped")
    return f'<span class="{cls}">{s}</span>'


def row_color_pass_fail(status: str) -> str:
    """Return a background hex for dataframe row styling."""
    if status == "FAIL":
        return "#fdf2f2"
    if status == "PASS":
        return "#f0faf4"
    return "#ffffff"


# ═════════════════════════════════════════════════════════════════════════════
# Sidebar
# ═════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.image(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/ASBL_logo.png/120px-ASBL_logo.png",
        width=90,
        use_container_width=False,
    )
    st.markdown("## ASBL QA Monitor")
    st.markdown("---")

    days_map = {"Last 24 hours": 1, "Last 3 days": 3, "Last 7 days": 7, "Last 14 days": 14}
    days_label = st.selectbox("Time window", list(days_map.keys()), index=2)
    days = days_map[days_label]

    if st.button("Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.caption(f"Data cached 5 min · Last load: {datetime.now().strftime('%H:%M:%S')}")
    st.caption("Auto-refresh: reload page every 5 min for live data.")


# ═════════════════════════════════════════════════════════════════════════════
# Load data
# ═════════════════════════════════════════════════════════════════════════════

with st.spinner("Loading data from MongoDB…"):
    cb_docs   = fetch_chatbot_qa(days)
    vc_docs   = fetch_voice_qa(days)
    an_runs   = fetch_analytics_runs(days)
    fb_docs   = fetch_feedback(days)
    rec_docs  = fetch_recommendations(days)

# ── Derived counts ─────────────────────────────────────────────────────────
cb_evaluated = sum(1 for d in cb_docs if d.get("status") in ("PASS", "FAIL"))
vc_evaluated = sum(1 for d in vc_docs if d.get("status") in ("PASS", "FAIL"))
cb_health    = avg_score(cb_docs)
vc_health    = avg_score(vc_docs)

# Open recommendations = total fix items in latest rec doc
open_recs = 0
if rec_docs:
    open_recs = len(rec_docs[0].get("fixes") or [])

# ═════════════════════════════════════════════════════════════════════════════
# Header
# ═════════════════════════════════════════════════════════════════════════════

st.markdown(
    '<h1 style="color:#1a2d5a;font-size:1.6rem;font-weight:800;margin-bottom:4px;">'
    "ASBL QA Agent — Live Dashboard</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    f'<div class="refresh-note">Window: <b>{days_label}</b> &nbsp;·&nbsp; '
    f'Loaded at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>',
    unsafe_allow_html=True,
)

# ═════════════════════════════════════════════════════════════════════════════
# Top row — 5 metric cards
# ═════════════════════════════════════════════════════════════════════════════

m1, m2, m3, m4, m5 = st.columns(5)

with m1:
    val = fmt_score(cb_health)
    delta_color = "normal" if cb_health and cb_health >= 7 else "inverse"
    st.metric(
        "Chatbot Health",
        val,
        delta=f"{'above' if cb_health and cb_health >= 7 else 'below'} threshold",
        delta_color=delta_color,
    )

with m2:
    val = fmt_score(vc_health)
    delta_color = "normal" if vc_health and vc_health >= 7 else "inverse"
    st.metric(
        "Voice Health",
        val,
        delta=f"{'above' if vc_health and vc_health >= 7 else 'below'} threshold",
        delta_color=delta_color,
    )

with m3:
    st.metric("CB Evaluated", cb_evaluated)

with m4:
    st.metric("VC Evaluated", vc_evaluated)

with m5:
    st.metric("Open Recommendations", open_recs)

st.markdown("<br>", unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
# Section 1 — Recent Cron Runs
# ═════════════════════════════════════════════════════════════════════════════

st.markdown('<span class="section-header">Recent Cron Runs</span>', unsafe_allow_html=True)

# Group chatbot_qa and voice_qa by evaluated_at hour slot
def build_cron_table(cb: list[dict], vc: list[dict]) -> pd.DataFrame:
    def slot(doc):
        ts = doc.get("evaluated_at", "")
        dt = parse_iso(ts)
        if dt:
            return dt.strftime("%Y-%m-%d %H:00")
        return "Unknown"

    cb_slots: dict[str, dict] = {}
    for d in cb:
        s = slot(d)
        if s not in cb_slots:
            cb_slots[s] = {"cb_evaluated": 0, "cb_pass": 0, "cb_fail": 0}
        st_ = d.get("status", "")
        if st_ in ("PASS", "FAIL"):
            cb_slots[s]["cb_evaluated"] += 1
        if st_ == "PASS":
            cb_slots[s]["cb_pass"] += 1
        if st_ == "FAIL":
            cb_slots[s]["cb_fail"] += 1

    vc_slots: dict[str, dict] = {}
    for d in vc:
        s = slot(d)
        if s not in vc_slots:
            vc_slots[s] = {"vc_evaluated": 0, "vc_pass": 0, "vc_fail": 0}
        st_ = d.get("status", "")
        if st_ in ("PASS", "FAIL"):
            vc_slots[s]["vc_evaluated"] += 1
        if st_ == "PASS":
            vc_slots[s]["vc_pass"] += 1
        if st_ == "FAIL":
            vc_slots[s]["vc_fail"] += 1

    all_slots = sorted(set(list(cb_slots.keys()) + list(vc_slots.keys())), reverse=True)
    rows = []
    for s in all_slots:
        cb_s = cb_slots.get(s, {"cb_evaluated": 0, "cb_pass": 0, "cb_fail": 0})
        vc_s = vc_slots.get(s, {"vc_evaluated": 0, "vc_pass": 0, "vc_fail": 0})
        rows.append(
            {
                "Time Slot": s,
                "CB Evaluated": cb_s["cb_evaluated"],
                "CB Pass": cb_s["cb_pass"],
                "CB Fail": cb_s["cb_fail"],
                "VC Evaluated": vc_s["vc_evaluated"],
                "VC Pass": vc_s["vc_pass"],
                "VC Fail": vc_s["vc_fail"],
            }
        )
    return pd.DataFrame(rows)


cron_df = build_cron_table(cb_docs, vc_docs)

if cron_df.empty:
    st.info("No cron run data available for this time window.")
else:
    def highlight_cron_row(row):
        has_fail = (row["CB Fail"] > 0) or (row["VC Fail"] > 0)
        bg = "#fdf2f2" if has_fail else "#f0faf4"
        return [f"background-color: {bg}"] * len(row)

    styled_cron = (
        cron_df.style
        .apply(highlight_cron_row, axis=1)
        .format(
            {
                "CB Evaluated": "{:,}",
                "CB Pass": "{:,}",
                "CB Fail": "{:,}",
                "VC Evaluated": "{:,}",
                "VC Pass": "{:,}",
                "VC Fail": "{:,}",
            }
        )
    )
    st.dataframe(styled_cron, use_container_width=True, hide_index=True)

st.markdown("<br>", unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
# Section 2 — Tabs
# ═════════════════════════════════════════════════════════════════════════════

tab_cb, tab_vc, tab_trends, tab_recs = st.tabs(
    ["Chatbot QA", "Voice QA", "Trends", "Recommendations"]
)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — Chatbot QA
# ─────────────────────────────────────────────────────────────────────────────

with tab_cb:
    st.markdown('<span class="section-header">Chatbot QA Results</span>', unsafe_allow_html=True)

    if not cb_docs:
        st.info("No chatbot QA results in this time window.")
    else:
        # ── Filters ────────────────────────────────────────────────────────
        cb_all_issue_types = issue_types_from_docs(cb_docs)
        fc1, fc2 = st.columns([2, 3])
        with fc1:
            cb_status_filter = st.selectbox(
                "Filter by status", ["All", "PASS", "FAIL", "SKIPPED"], key="cb_status"
            )
        with fc2:
            cb_issue_filter = st.multiselect(
                "Filter by issue type", cb_all_issue_types, key="cb_issue_type"
            )

        # ── Apply filters ──────────────────────────────────────────────────
        filtered_cb = cb_docs
        if cb_status_filter != "All":
            filtered_cb = [d for d in filtered_cb if d.get("status") == cb_status_filter]
        if cb_issue_filter:
            def has_issue_type(doc, types):
                for iss in doc.get("issues") or []:
                    if iss.get("type") in types:
                        return True
                return False
            filtered_cb = [d for d in filtered_cb if has_issue_type(d, set(cb_issue_filter))]

        st.caption(f"Showing {len(filtered_cb)} of {len(cb_docs)} results")

        # ── Build dataframe ────────────────────────────────────────────────
        cb_rows = []
        for d in filtered_cb:
            issue_summary = ", ".join(
                f"{i.get('type','?')} ({i.get('severity','?')})"
                for i in (d.get("issues") or [])
            )
            kb_refs = ", ".join(
                str(i.get("kb_reference", ""))
                for i in (d.get("issues") or [])
                if i.get("kb_reference")
            )
            cb_rows.append(
                {
                    "Status": d.get("status", "?"),
                    "Score": d.get("score", ""),
                    "Conv ID": str(d.get("conversation_id", ""))[:30],
                    "Turns": d.get("turn_count", ""),
                    "Issues": issue_summary or "—",
                    "KB Refs": kb_refs or "—",
                    "Evaluated At": str(d.get("evaluated_at", ""))[:16].replace("T", " "),
                }
            )

        cb_df = pd.DataFrame(cb_rows)

        def highlight_cb_status(row):
            bg = row_color_pass_fail(row["Status"])
            return [f"background-color: {bg}"] * len(row)

        styled_cb = cb_df.style.apply(highlight_cb_status, axis=1)
        st.dataframe(styled_cb, use_container_width=True, hide_index=True, height=400)

        # ── Issue type bar chart ───────────────────────────────────────────
        st.markdown("#### Issue Type Breakdown")
        type_counts: dict[str, int] = {}
        for d in filtered_cb:
            for iss in d.get("issues") or []:
                t = iss.get("type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1

        if type_counts:
            tc_df = (
                pd.DataFrame(list(type_counts.items()), columns=["Issue Type", "Count"])
                .sort_values("Count", ascending=False)
            )
            fig_bar = px.bar(
                tc_df,
                x="Issue Type",
                y="Count",
                color="Count",
                color_continuous_scale=[[0, "#f9c784"], [0.5, "#e86219"], [1, "#c0392b"]],
                title="Chatbot Issue Types",
                template="plotly_white",
            )
            fig_bar.update_layout(
                title_font_color="#1a2d5a",
                coloraxis_showscale=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=40, b=20, l=0, r=0),
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No issues found in this filtered set.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — Voice QA
# ─────────────────────────────────────────────────────────────────────────────

with tab_vc:
    st.markdown('<span class="section-header">Voice QA Results</span>', unsafe_allow_html=True)

    if not vc_docs:
        st.info("No voice QA results in this time window.")
    else:
        # ── Build dataframe ────────────────────────────────────────────────
        vc_rows = []
        for d in vc_docs:
            issue_summary = ", ".join(
                f"{i.get('type','?')} ({i.get('severity','?')})"
                for i in (d.get("issues") or [])
            )
            vc_rows.append(
                {
                    "Status": d.get("status", "?"),
                    "Score": d.get("score", ""),
                    "Call SID": str(d.get("call_sid", ""))[:30],
                    "Language": d.get("language_used", "—"),
                    "Lang Compliance": d.get("language_compliance", "—"),
                    "Direction": d.get("call_direction", "—"),
                    "Phone": str(d.get("phone_number", "—")),
                    "Issues": issue_summary or "—",
                    "Evaluated At": str(d.get("evaluated_at", ""))[:16].replace("T", " "),
                }
            )

        vc_df = pd.DataFrame(vc_rows)

        def highlight_vc_row(row):
            if row["Status"] == "FAIL":
                return ["background-color: #fdf2f2"] * len(row)
            if row["Status"] == "PASS":
                return ["background-color: #f0faf4"] * len(row)
            return [""] * len(row)

        def highlight_lang_compliance(row):
            styles = [""] * len(row)
            col_idx = list(vc_df.columns).index("Lang Compliance")
            if row["Lang Compliance"] == "PASS":
                styles[col_idx] = "background-color: #d4edda; color: #155724; font-weight: 700"
            elif row["Lang Compliance"] == "FAIL":
                styles[col_idx] = "background-color: #f8d7da; color: #721c24; font-weight: 700"
            return styles

        def combined_style(row):
            base = highlight_vc_row(row)
            lc = highlight_lang_compliance(row)
            # merge: lang compliance cell overrides row bg on its column
            return [lc[i] if lc[i] else base[i] for i in range(len(row))]

        styled_vc = vc_df.style.apply(combined_style, axis=1)
        st.dataframe(styled_vc, use_container_width=True, hide_index=True, height=400)

        # ── Two pie charts side by side ────────────────────────────────────
        pc1, pc2 = st.columns(2)

        with pc1:
            # Issue type breakdown
            vc_type_counts: dict[str, int] = {}
            for d in vc_docs:
                for iss in d.get("issues") or []:
                    t = iss.get("type", "unknown")
                    vc_type_counts[t] = vc_type_counts.get(t, 0) + 1

            if vc_type_counts:
                pie_df = pd.DataFrame(
                    list(vc_type_counts.items()), columns=["Issue Type", "Count"]
                )
                fig_pie1 = px.pie(
                    pie_df,
                    names="Issue Type",
                    values="Count",
                    title="Issue Type Distribution",
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    template="plotly_white",
                )
                fig_pie1.update_layout(
                    title_font_color="#1a2d5a",
                    paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(t=40, b=10, l=0, r=0),
                )
                st.plotly_chart(fig_pie1, use_container_width=True)
            else:
                st.info("No issues to chart.")

        with pc2:
            # Language distribution
            lang_counts: dict[str, int] = {}
            for d in vc_docs:
                lang = d.get("language_used") or "Unknown"
                lang_counts[lang] = lang_counts.get(lang, 0) + 1

            if lang_counts:
                lang_df = pd.DataFrame(
                    list(lang_counts.items()), columns=["Language", "Count"]
                )
                fig_pie2 = px.pie(
                    lang_df,
                    names="Language",
                    values="Count",
                    title="Language Distribution",
                    color_discrete_sequence=["#1a2d5a", "#e86219", "#1a7a45", "#d68910", "#5a6070"],
                    template="plotly_white",
                )
                fig_pie2.update_layout(
                    title_font_color="#1a2d5a",
                    paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(t=40, b=10, l=0, r=0),
                )
                st.plotly_chart(fig_pie2, use_container_width=True)
            else:
                st.info("No language data to chart.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Trends
# ─────────────────────────────────────────────────────────────────────────────

with tab_trends:
    st.markdown('<span class="section-header">Health Score Trends</span>', unsafe_allow_html=True)

    def build_trend_series(docs: list[dict], label: str) -> pd.DataFrame:
        """
        Group docs by date, compute average score per day.
        Returns DataFrame with columns: date, score, source
        """
        day_data: dict[str, list[float]] = {}
        for d in docs:
            if d.get("status") not in ("PASS", "FAIL"):
                continue
            sc = d.get("score")
            if not isinstance(sc, (int, float)):
                continue
            ts = parse_iso(d.get("evaluated_at", ""))
            if ts is None:
                continue
            day = ts.strftime("%Y-%m-%d")
            day_data.setdefault(day, []).append(float(sc))

        rows = []
        for day, scores in sorted(day_data.items()):
            rows.append(
                {"Date": day, "Avg Score": round(sum(scores) / len(scores), 2), "Source": label}
            )
        return pd.DataFrame(rows)

    cb_trend = build_trend_series(cb_docs, "Chatbot")
    vc_trend = build_trend_series(vc_docs, "Voice")
    trend_df = pd.concat([cb_trend, vc_trend], ignore_index=True)

    if trend_df.empty:
        st.info("Not enough data to show trends. Try expanding the time window.")
    else:
        fig_trend = px.line(
            trend_df,
            x="Date",
            y="Avg Score",
            color="Source",
            markers=True,
            color_discrete_map={"Chatbot": "#1a2d5a", "Voice": "#e86219"},
            title="Daily Average Health Score (Chatbot vs Voice)",
            template="plotly_white",
        )
        # Threshold line at 7
        fig_trend.add_hline(
            y=7,
            line_dash="dash",
            line_color="#c0392b",
            annotation_text="Threshold: 7.0",
            annotation_position="top left",
            annotation_font_color="#c0392b",
        )
        fig_trend.update_yaxes(range=[0, 10.5], title="Score (0–10)")
        fig_trend.update_xaxes(title="Date")
        fig_trend.update_layout(
            title_font_color="#1a2d5a",
            legend_title_text="Channel",
            plot_bgcolor="rgba(247,249,252,1)",
            paper_bgcolor="rgba(0,0,0,0)",
            hovermode="x unified",
            margin=dict(t=50, b=30, l=0, r=0),
        )
        st.plotly_chart(fig_trend, use_container_width=True)

        # Summary stats below chart
        sc1, sc2 = st.columns(2)
        with sc1:
            st.markdown("**Chatbot — Score Summary**")
            if not cb_trend.empty:
                st.dataframe(
                    cb_trend[["Date", "Avg Score"]].rename(columns={"Avg Score": "Score"}),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No chatbot trend data.")
        with sc2:
            st.markdown("**Voice — Score Summary**")
            if not vc_trend.empty:
                st.dataframe(
                    vc_trend[["Date", "Avg Score"]].rename(columns={"Avg Score": "Score"}),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No voice trend data.")

    # Analytics flags bar (bonus insight in Trends)
    if an_runs:
        st.markdown("---")
        st.markdown("#### Analytics Flag Severity Over Time")
        flag_rows = []
        for run in an_runs:
            ts = parse_iso(run.get("run_at", ""))
            if ts is None:
                continue
            day = ts.strftime("%Y-%m-%d")
            for f in run.get("flags") or []:
                flag_rows.append({"Date": day, "Severity": f.get("severity", "?")})
        if flag_rows:
            flag_df = (
                pd.DataFrame(flag_rows)
                .groupby(["Date", "Severity"])
                .size()
                .reset_index(name="Count")
            )
            fig_flags = px.bar(
                flag_df,
                x="Date",
                y="Count",
                color="Severity",
                color_discrete_map={
                    "HIGH": "#c0392b",
                    "MEDIUM": "#d68910",
                    "LOW": "#1a7a45",
                },
                title="Analytics Flags per Day",
                template="plotly_white",
                barmode="stack",
            )
            fig_flags.update_layout(
                title_font_color="#1a2d5a",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(247,249,252,1)",
                margin=dict(t=50, b=30, l=0, r=0),
            )
            st.plotly_chart(fig_flags, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — Recommendations
# ─────────────────────────────────────────────────────────────────────────────

with tab_recs:
    st.markdown(
        '<span class="section-header">Recommendations & Feedback</span>',
        unsafe_allow_html=True,
    )

    URGENCY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

    # ── Problems from feedback ─────────────────────────────────────────────
    st.markdown("### Problems Found (Feedback Agent)")

    all_problems = []
    for fb in fb_docs:
        for p in fb.get("problems") or []:
            all_problems.append(
                {
                    "urgency": p.get("urgency", "MEDIUM"),
                    "title": p.get("title", "(untitled)"),
                    "what_is_wrong": p.get("what_is_wrong", ""),
                    "what_is_not_wrong": p.get("what_is_not_wrong", ""),
                    "evidence": p.get("evidence") or [],
                    "source": fb.get("source", ""),
                    "submitted_at": str(fb.get("submitted_at", ""))[:16].replace("T", " "),
                }
            )

    if not all_problems:
        st.info("No feedback problems found in this time window.")
    else:
        all_problems.sort(key=lambda x: URGENCY_ORDER.get(x["urgency"], 9))

        URGENCY_COLORS = {
            "HIGH": ("#f8d7da", "#721c24", "#c0392b"),
            "MEDIUM": ("#fff3cd", "#856404", "#d68910"),
            "LOW": ("#d4edda", "#155724", "#1a7a45"),
        }

        for p in all_problems:
            bg, txt, border = URGENCY_COLORS.get(p["urgency"], ("#f7f9fc", "#1a1a2e", "#dde3ed"))
            with st.expander(
                f"[{p['urgency']}] {p['title']}  —  {p['submitted_at']}",
                expanded=(p["urgency"] == "HIGH"),
            ):
                st.markdown(
                    f"""
<div style="border-left: 4px solid {border}; padding: 10px 14px; background:{bg}; border-radius: 0 6px 6px 0; margin-bottom:8px;">
  <b style="color:{txt}">What is wrong:</b><br>
  <span style="color:#1a1a2e">{p['what_is_wrong'] or '—'}</span>
</div>
""",
                    unsafe_allow_html=True,
                )
                if p["what_is_not_wrong"]:
                    st.markdown(
                        f"**What is NOT wrong:** {p['what_is_not_wrong']}",
                        unsafe_allow_html=False,
                    )
                if p["evidence"]:
                    st.markdown("**Evidence:**")
                    for ev in p["evidence"]:
                        st.markdown(f"- {ev}")

    # ── Fixes from recommendations ─────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Recommended Fixes")

    all_fixes = []
    for rec in rec_docs:
        gen_at = str(rec.get("generated_at", ""))[:16].replace("T", " ")
        for f in rec.get("fixes") or []:
            all_fixes.append(
                {
                    "rank": f.get("rank", "?"),
                    "problem": f.get("problem", "(no problem description)"),
                    "fix": f.get("fix", ""),
                    "where": f.get("where", ""),
                    "change_type": f.get("change_type", ""),
                    "expected_outcome": f.get("expected_outcome", ""),
                    "generated_at": gen_at,
                }
            )

    if not all_fixes:
        st.info("No recommendations found in this time window.")
    else:
        for f in all_fixes:
            with st.expander(
                f"#{f['rank']} — {f['problem'][:80]}",
                expanded=False,
            ):
                st.markdown(
                    f"""
<div class="fix-card">
  <b>Fix:</b> {f['fix']}<br><br>
  <b style="color:#5a6070;">Where:</b> <code>{f['where']}</code><br>
  <b style="color:#5a6070;">Change type:</b> {f['change_type']}<br>
  <div class="fix-outcome">&#x2192; Expected: {f['expected_outcome']}</div>
</div>
""",
                    unsafe_allow_html=True,
                )
                st.caption(f"Generated at: {f['generated_at']}")

# ═════════════════════════════════════════════════════════════════════════════
# Footer
# ═════════════════════════════════════════════════════════════════════════════

st.markdown("---")
st.markdown(
    '<p style="color:#9ca3af;font-size:.73rem;text-align:center;">'
    "ASBL QA Agent Dashboard &nbsp;·&nbsp; "
    "Data refreshes every 5 minutes &nbsp;·&nbsp; "
    "Built with Streamlit + MongoDB Atlas"
    "</p>",
    unsafe_allow_html=True,
)
