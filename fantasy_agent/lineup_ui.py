"""Lineup page backed by the same service exposed to the conversational agent."""
import streamlit as st
from datetime import datetime
from .lineup_service import LineupService
from .integrations.sleeper import DataUnavailable
from .integrations.research import ProviderUnavailable
from .storage import BudgetExceeded
from . import ui
from .analysis import owned
from .lineup_cards import starting_cards, comparison_cards, render_evidence


def lineup_table(report,players):
    def name(pid):
        p=players.get(pid)
        return p.name if hasattr(p,"name") else p.get("name",pid) if isinstance(p,dict) else pid or "Unfilled"
    return [{"Slot":r.slot,"Saved starter":name(r.current_id),"Recommended":name(r.recommended_id),
             "Saved estimate":r.current_estimate,"Expected points":r.estimate,"Strategy score":r.objective,
             "Opponent":r.opponent,"Locked / unverified":r.locked,"Kickoff":r.kickoff,"Reason":r.reason} for r in report.slots]


def render_lineup(snapshot,roster_id,service,config,store):
    st.caption("League-scored statistical estimates · Exact slot assignment · Conservative kickoff locks · No lineup is submitted automatically")
    with st.form("lineup_controls"):
        left,right=st.columns([1,2])
        week=left.selectbox("Week",list(range(snapshot.week,19)))
        strategy=right.selectbox("Strategy",["expected","upside","floor"],format_func=lambda x:{"expected":"Maximize expected points","upside":"Favor upside","floor":"Favor floor"}[x])
        refresh=st.checkbox("Refresh statistical sources",value=False)
        roster=next(r for r in snapshot.rosters if r.roster_id==roster_id)
        excluded=st.multiselect("Exclude from unlocked slots (late inactives or your preference)",sorted(owned(roster)),format_func=lambda p:snapshot.players[p].name,key="lineup_excluded_players")
        submitted=st.form_submit_button("Optimize lineup",type="primary")
    identity=(snapshot.league_id,roster_id)
    if submitted or st.session_state.get("lineup_identity")!=identity:
        try:
            with st.spinner("Refreshing starters, schedule and statistical evidence…"):
                fresh,report=LineupService(config,store,service).find(snapshot,roster_id,week,strategy,refresh,excluded)
            st.session_state.update(snapshot=fresh,lineup_report=report,lineup_identity=identity)
            st.rerun()
        except (DataUnavailable,ProviderUnavailable,BudgetExceeded,ValueError) as exc:
            st.error(str(exc));st.caption("Resolve the source issue and use Optimize lineup to retry. No substitute data was used.")
    report=st.session_state.get("lineup_report")
    if not report or st.session_state.get("lineup_identity")!=identity:return
    st.caption(f"Week {report.week} · {report.strategy} · Ownership refreshed {ui.local_time(datetime.fromisoformat(report.snapshot_at))}")
    if report.expected_total is not None:
        st.metric("Estimated lineup points",f"{report.expected_total:.2f}",f"{report.expected_gain:+.2f} vs saved" if report.expected_gain is not None else None)
    else:
        st.info("A full-game total cannot be compared reliably because games have started or some slots lack supported evidence. Unlocked substitutions are shown below.")
    starters,comparison=st.tabs(["Starting lineup","Detailed comparison"])
    with starters:
        with st.container(border=True):
            st.subheader("◎  Your starting unit")
            left,right=st.columns(2)
            left.metric("Locked / unverified slots",sum(r.locked for r in report.slots))
            right.metric("Suggested substitutions",sum(r.current_id!=r.recommended_id for r in report.slots))
            st.caption("Player photos and injury flags reflect the dated Sleeper catalog. Open a slot’s reasoning before making a start/sit change.")
            st.html(starting_cards(report,snapshot.players))
            st.caption("Statistical estimates, not guaranteed outcomes. Review late injury reports before submitting in Sleeper.")
    with comparison:
        st.caption("Saved versus recommended by slot. Slot differences are unavailable for locked/unverified assignments; strategy scores remain separate from expected points.")
        st.html(comparison_cards(report,snapshot.players))
    render_evidence(report,snapshot.players)
    st.download_button("Export lineup analysis",report.model_dump_json(indent=2),file_name="lineup.json",mime="application/json")
