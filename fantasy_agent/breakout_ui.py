"""Production Breakout Radar using the shared measured-opportunity signal."""
import streamlit as st
from .analysis import owned
from .breakouts import BreakoutService
from .integrations.sleeper import DataUnavailable
from .storage import BudgetExceeded
from .models import utcnow
from . import ui


def render_breakouts(snapshot,roster_id,league_service,config,store):
    st.caption("Measured opportunity changes, not touchdown spikes or invented rankings.")
    scope=st.selectbox("Ownership",["Available players","My team","Entire league"])
    position=st.selectbox("Breakout position",["All","QB","RB","WR","TE"])
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
    def change(b,name):return next((c.change for c in b.changes if c.metric==name),None)
    st.caption("Ownership/statistical analysis: "+ui.local_time(run.snapshot_at))
    st.dataframe([{"Player":snapshot.players[b.player_id].name,"Position":run.evaluations[b.player_id].position,
        "Signal /100":b.score,"Confidence":b.confidence,"Evidence":b.label,"Opportunity change":change(b,"opportunities"),
        "Snap-share change":change(b,"snap_share"),"Target-share change":change(b,"target_share"),
        "Prior games":b.prior_games,"Recent games":b.recent_games} for b in signals],hide_index=True,width="stretch")
    if signals:
        pid=st.selectbox("Inspect opportunity evidence",[b.player_id for b in signals],format_func=lambda p:snapshot.players[p].name)
        signal=next(b for b in signals if b.player_id==pid)
        for reason in signal.reasons:st.write(reason)
        for limitation in signal.limitations:st.caption(limitation)
        st.dataframe(run.evaluations[pid].weekly_observed,hide_index=True,width="stretch")
        st.caption("Ask AI Analyst about this player for current injury/role reporting and roster-specific advice.")
    else:st.info("No positive opportunity signals meet these filters. No breakout was invented.")
    with st.expander("Sources and limitations"):
        for warning in run.warnings:st.write(warning)
        for source in run.sources:
            st.link_button(source.name,source.url);st.caption("Retrieved "+ui.local_time(source.retrieved_at))
    st.download_button("Export breakout evidence",run.model_dump_json(indent=2),"breakouts.json","application/json")
