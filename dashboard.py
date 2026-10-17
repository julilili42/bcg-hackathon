"""Run: streamlit run dashboard.py. Registry reads go directly to PostgreSQL."""
import os
from html import escape
from pathlib import Path
from time import monotonic
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pandas as pd
import streamlit as st

import infrastructure as db

st.set_page_config(page_title="WaterLine · Community water access", page_icon="💧", layout="wide")
st.html("<style>" + Path(__file__).with_name("web").joinpath("dashboard.css").read_text() + "</style>")
st.title("💧 WaterLine")
st.caption("One report helps the next village.")
st.info("FICTIONAL DEMO · All assets, villages, reports and map coordinates are synthetic. "
        "Statuses are community reports requiring verification. Operational does not mean safe to drink.")

st.link_button("🎙 Open voice demo", os.getenv("WATERLINE_API_URL", "http://localhost:8000").rstrip("/") + "/demo")

monitor, contribute = st.tabs(["Infrastructure", "Ask & report"])
with contribute:
    st.subheader("Share what you know. Find what works.")
    st.caption("Your observations are stored and may help other residents. Use fictional reports and opaque demo user IDs.")
    with st.form("community-message"):
        user_id = st.selectbox("Demo resident", ["demo-user-a", "demo-user-b"])
        message = st.text_area("Message", placeholder="The Alero Market Water Point stopped working today. Where else can we go?", max_chars=5000)
        submitted = st.form_submit_button("Send message", type="primary")
    if submitted and message.strip():
        # Preserve the ID on uncertain network outcomes, so retry cannot duplicate reports.
        fingerprint = (message, user_id)
        if st.session_state.get("pending_message") != fingerprint:
            st.session_state.pending_message = fingerprint
            st.session_state.pending_turn_id = str(uuid4())
        try:
            with st.spinner("Recording reports and finding evidence…"):
                response = httpx.post(os.getenv("WATERLINE_API_URL", "http://localhost:8000") + "/interact",
                    json=dict(message=message, user_id=user_id, turn_id=st.session_state.pending_turn_id), timeout=150)
                response.raise_for_status()
                st.session_state.result = response.json()
                st.session_state.sent_message = message
            st.session_state.pop("pending_message", None)
        except (httpx.HTTPError, ValueError):
            st.error("The agent is unavailable. Start uvicorn app:app and check its logs. "
                     "Your report may already be saved; sending this message again keeps the same turn ID.")
    if "result" in st.session_state:
        result = st.session_state.result
        st.write(st.session_state.sent_message)
        st.caption("Detected intent: " + result["intent"])
        st.success(result["answer"])
        with st.expander("Saved reports & retrieved evidence", expanded=True):
            st.json({k: result.get(k) for k in ("turn_id", "interpretation", "reports", "sources")})
        st.caption("The Infrastructure view updates automatically every three seconds.")

@st.fragment(run_every="3s")
def infrastructure_view():
    heading, refresh = st.columns([5, 1])
    heading.subheader("Community infrastructure overview")
    refresh.button("Refresh now", width="stretch")
    try:
        pipes = db.get_pipes()
    except Exception:
        st.error("PostgreSQL is unavailable or the schema is missing. Start the database, then run "
                 "python infrastructure.py and python seed_infrastructure.py. Check DATABASE_URL.")
        return
    now = monotonic()
    clock = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    st.html(f'<div class="waterline-sync"><i></i><strong>LIVE</strong> Synced {clock} · checking every 3 seconds</div>')
    current = {str(p["id"]): p for p in pipes}
    previous = st.session_state.get("infrastructure_snapshot")
    events = st.session_state.get("infrastructure_activity", [])
    new_events = []
    # First load establishes a baseline; unchanged polling never creates an event.
    if previous is not None:
        for key, pipe in current.items():
            old = previous.get(key)
            if old == pipe:
                continue
            event = dict(id=uuid4().hex, pipe_id=key, name=pipe["name"], village=pipe["village"],
                before=old["status"] if old else None, after=pipe["status"], at=now, clock=clock,
                new_report=bool(old and pipe.get("report_count", 0) > old.get("report_count", 0)))
            new_events.append(event)
        for key in previous.keys() - current.keys():
            old = previous[key]
            new_events.append(dict(id=uuid4().hex, pipe_id=key, name=old["name"], village=old["village"],
                before=old["status"], after=None, at=now, clock=clock, new_report=False))
    events = (new_events + events)[:5]
    st.session_state.infrastructure_snapshot = current
    st.session_state.infrastructure_activity = events
    colors = {"operational": "#16806a", "broken": "#dc2626", "unsafe": "#dc2626",
              "low_flow": "#b7790e", "under_repair": "#b7790e", "unknown": "#6b7280"}
    fresh_ids = {e["pipe_id"] for e in events if now - e["at"] < 12}
    def totals(records):
        return (len(records), sum(p["status"] == "operational" for p in records),
                sum(p["status"] in {"broken", "unsafe"} for p in records),
                sum(p["needs_verification"] for p in records))
    values = totals(pipes)
    if new_events:
        before = totals(list(previous.values()))
        st.session_state.metric_changes = tuple(n - o for n, o in zip(values, before))
        st.session_state.metric_changed_at = now
    deltas = st.session_state.get("metric_changes", (0, 0, 0, 0))
    metric_recent = now - st.session_state.get("metric_changed_at", float("-inf")) < 12
    with st.container(key="live_metrics"):
        for column, label, value, delta in zip(st.columns(4),
                ("Registered assets", "Reported operational", "Reported broken / unsafe", "Require verification"), values, deltas):
            column.metric(label, value, delta=f"{delta:+d} since last update" if metric_recent and delta else None,
                          delta_color="off", border=True)
    metric_style = ".st-key-live_metrics [data-testid='stMetric']{animation:none}"
    if new_events:
        # Keep this render slot on idle polls; animate only when a real change is observed.
        animation = "waterline_metric_" + new_events[0]["id"]
        metric_style = (f"@keyframes {animation}{{from{{background:#14a39b25;transform:translateY(3px)}}to{{background:transparent;transform:translateY(0)}}}}"
                        f".st-key-live_metrics [data-testid='stMetric']{{animation:{animation} .85s ease-out}}")
    st.html("<style>" + metric_style + "@media(prefers-reduced-motion:reduce){.st-key-live_metrics [data-testid='stMetric']{animation:none!important}}</style>")
    if events:
        cards = []
        for event in events:
            # Expired cards stay in the activity feed, with no repeated entrance animation.
            animate = now - event["at"] < 2
            before = escape((event["before"] or "new asset").replace("_", " "))
            after = escape((event["after"] or "removed from registry").replace("_", " "))
            if event["before"] != event["after"]:
                note = "Current reported status changed · requires verification" if event["after"] else "Asset removed from the registry"
            else:
                note = "New community report received · current reported status unchanged" if event["new_report"] else "Asset information updated · current reported status unchanged"
            style = f"--change-color:{colors.get(event['after'], '#6b7280')};--elapsed:{now - event['at']:.2f}s;"
            status_markup = (f'<span class="waterline-status">{before}</span> → <span class="waterline-status new">{after}</span>'
                             if event["before"] != event["after"] else
                             f'<span class="waterline-status new">{after}</span><span>reported status unchanged</span>')
            cards.append(f'<article class="waterline-change{'' if animate else ' is-stale'}" data-event-id="{event["id"]}" style="{style}">'
                f'<div class="waterline-change-head"><strong>{escape(event["name"])}</strong><time>{event["clock"]}</time></div>'
                f'<div class="waterline-change-meta">{escape(event["village"])} · community infrastructure update</div>'
                f'<div class="waterline-change-status">{status_markup}</div>'
                f'<div class="waterline-change-note">{note}</div></article>')
        st.caption("LATEST CHANGES · this viewing session")
        st.html('<section class="waterline-feed" aria-label="Recent infrastructure changes" aria-live="polite">' + "".join(cards) + '</section>')
    if not pipes:
        st.warning("The registry is empty. Run python seed_infrastructure.py to add fictional demo assets.")
        return
    left, right = st.columns(2)
    village = left.selectbox("Village", ["All", *sorted({p["village"] for p in pipes})])
    status = right.selectbox("Reported status", ["All", *db.STATUSES])
    filtered = [p for p in pipes if (village == "All" or p["village"] == village)
                and (status == "All" or p["status"] == status)]
    if not filtered:
        st.info("No assets match these filters.")
    else:
        frame = pd.DataFrame([dict(Name=p["name"], Village=p["village"],
            **{"Reported status": p["status"], "Latest observation (UTC)": p["status_observed_at"],
               "Needs verification": p["needs_verification"]}) for p in filtered])
        fresh_rows = [index for index, pipe in enumerate(filtered) if str(pipe["id"]) in fresh_ids]
        styled = frame.style.apply(lambda row: ["background-color: #e0f2ec; color: #183e49" if row.name in fresh_rows else "" for _ in row], axis=1)
        styled = styled.map(lambda value: f"color: {colors[value]}; font-weight: bold", subset=["Reported status"])
        styled = styled.map(lambda value: "color: #d97706" if value else "", subset=["Needs verification"])
        st.dataframe(styled, hide_index=True, width="stretch")
        st.caption("Green indicates reported operation only. Amber verification flags require follow-up for every status.")
        points = [dict(latitude=p["latitude"], longitude=p["longitude"], color=colors[p["status"]])
                  for p in filtered if p["latitude"] is not None and p["longitude"] is not None
                  and -90 <= p["latitude"] <= 90 and -180 <= p["longitude"] <= 180]
        if points:
            with st.expander("Illustrative map · fictional coordinates"):
                st.map(pd.DataFrame(points), color="color", size=35)
        selected_id = st.selectbox("Inspect an asset", [str(p["id"]) for p in filtered],
            format_func=lambda key: next((p["name"] for p in filtered if str(p["id"]) == key), key), key="detail-asset")
        chosen = next(p for p in filtered if str(p["id"]) == selected_id)
        st.subheader(chosen["name"])
        st.write(f"{chosen['village']} · Reported **{chosen['status']}**")
        st.write(chosen["description"])
        st.caption(f"Latest applied observation: {chosen['status_observed_at'] or 'Unknown'} · "
                   f"Source report: {chosen['latest_report_id'] or 'None'} · "
                   f"Requires verification: {'Yes' if chosen['needs_verification'] else 'No'}")
        history = db.get_pipe_history(chosen["id"])
        st.write("Reporting history")
        st.dataframe(pd.DataFrame([{k: str(r[k]) if k == "id" else r[k] for k in (
            "id", "original_text", "reported_status", "observed_at", "reported_at",
            "applied_to_current_status", "resolution_status", "qdrant_indexed")} for r in history]),
            hide_index=True, width="stretch")


with monitor:
    infrastructure_view()
