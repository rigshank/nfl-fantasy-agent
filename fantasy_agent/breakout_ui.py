"""Production Breakout Radar using the shared measured-opportunity signal."""
import streamlit as st
from .analysis import owned
from .breakouts import BreakoutService
from .integrations.sleeper import DataUnavailable
from .storage import BudgetExceeded
from .models import utcnow
from .waiver_cards import page, signal_cards, render_player_evidence
from .evidence_ui import render_sources
from . import ui


def render_breakouts(snapshot,roster_id,league_service,config,store):
    st.caption("Measured opportunity changes, not touchdown spikes or invented rankings.")
    scout,filter_col=st.columns([2,1])
    scope=scout.selectbox("Ownership",["Available players","My team","Entire league"])
    position=filter_col.selectbox("Breakout position",["All","QB","RB","WR","TE"])
    refresh_stats=st.checkbox("Refresh statistical sources",value=False,key="breakout_refresh_stats")
    refresh=st.button("Refresh Breakout Radar",type="primary")
    identity=(snapshot.league_id,roster_id)
    if refresh or st.session_state.get("breakout_identity")!=identity:
        try:
            with st.spinner("Refreshing ownership and measuring opportunity trends…"):
                fresh,run=BreakoutService(config,store,league_service).find(snapshot,refresh_stats)
            st.session_state.update(snapshot=fresh,breakout_run=run,breakout_identity=identity)
            st.rerun()
        except (DataUnavailable,BudgetExceeded,ValueError) as exc:
            st.error(str(exc));st.caption("Retry Refresh Breakout Radar when the source is available.");return
    run=st.session_state.get("breakout_run")
    if not run:return
    if run.week!=snapshot.week or (utcnow()-run.snapshot_at).total_seconds()>config.league_cache_seconds:
        st.warning("This opportunity analysis is dated. Refresh Breakout Radar before using it.")
    owners={p:r.roster_id for r in snapshot.rosters for p in owned(r)}
    signals=[b for b in run.signals if (position=="All" or run.evaluations[b.player_id].position==position) and
        (scope=="Entire league" or scope=="Available players" and b.player_id not in owners or scope=="My team" and owners.get(b.player_id)==roster_id)]
    a,b,c=st.columns(3)
    a.metric("Matching signals",len(signals))
    b.metric("Medium confidence",sum(x.confidence=="medium" for x in signals))
    c.metric("Observed week",run.week)
    st.subheader("Opportunity leaderboard")
    st.caption("Ownership/statistical analysis: "+ui.local_time(run.snapshot_at))
    st.caption("Opportunity scores rank measured role changes, not breakout probabilities. Headshots and injury flags reflect the dated Sleeper catalog. Expand a card for its reasoning and uncertainty.")
    if signals:
        shown,offset=page(signals,'radar_signal_page','Candidates')
        st.html(signal_cards(snapshot,shown,offset))
        st.subheader("Player evidence")
        pid=st.selectbox("Inspect opportunity evidence",[b.player_id for b in signals],format_func=lambda p:snapshot.players[p].name)
        signal=next(b for b in signals if b.player_id==pid)
        with st.container(border=True):
            render_player_evidence(snapshot,pid,run.evaluations[pid],signal,key_prefix='radar')
            with st.expander("Why this player is on the radar",expanded=True):
                for reason in signal.reasons:st.write(reason)
        st.caption("Ask AI Analyst about this player for current injury/role reporting and roster-specific advice.")
    else:st.info("No positive opportunity signals meet these filters. No breakout was invented.")
    render_sources(run.sources,run.warnings,'radar')
    st.download_button("Export breakout evidence",run.model_dump_json(indent=2),"breakouts.json","application/json")
