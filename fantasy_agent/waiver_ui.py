"""Waiver Wire: actual roster upgrades, opportunity watch list and sourced analysis."""
import streamlit as st
from .analysis import owned
from .integrations.research import ProviderUnavailable
from .integrations.sleeper import DataUnavailable
from .storage import BudgetExceeded
from .waiver_service import WaiverService
from . import ui


def _name(snapshot, pid):
    return snapshot.players[pid].name if pid else "No drop needed"


def render_waivers(snapshot, roster_id, league_service, config, store):
    st.subheader("Pickups that fit your roster")
    st.caption("Every evaluated free agent is compared with legal roster changes. Projections begin next full NFL week; current ownership is refreshed before analysis.")
    if snapshot.week >= 18:
        st.info("No future regular-season projection weeks remain. The available-player directory is still usable below.")
        ui.waivers(snapshot)
        return
    roster = next(r for r in snapshot.rosters if r.roster_id == roster_id)
    identity = (snapshot.league_id, roster_id)
    if st.session_state.get("waiver_identity") != identity:
        for key in ("waiver_run", "waiver_snapshot", "waiver_answers", "waiver_protected_players"):
            st.session_state.pop(key, None)
        st.session_state["waiver_identity"] = identity
    with st.form("waiver_options"):
        left, right = st.columns(2)
        position = left.selectbox("Pickup position", ["All", "QB", "RB", "WR", "TE"])
        strategy = right.selectbox("Roster priority", ["Balanced", "Win now"],
            help="Balanced preserves measured dynasty value when dropping players. Win now can accept a disclosed value loss for lineup improvement.")
        protected = st.multiselect("Never recommend dropping", sorted(owned(roster)),
                                   format_func=lambda p: _name(snapshot, p), key="waiver_protected_players")
        refresh_stats = st.checkbox("Refresh NFL statistics as well as league ownership", value=False)
        submitted = st.form_submit_button("Analyze Waivers", type="primary", width="stretch")
    service = WaiverService(config, store, league_service)
    if submitted or "waiver_run" not in st.session_state:
        try:
            with st.spinner("Refreshing your league and comparing real pickup/drop options…"):
                fresh, run = service.find(snapshot, roster_id, protected, strategy.lower(), refresh_stats)
            st.session_state["snapshot"] = fresh
            st.session_state["waiver_snapshot"] = fresh
            st.session_state["waiver_run"] = run
            st.session_state["waiver_answers"] = {}
            st.rerun()
        except (DataUnavailable, ProviderUnavailable, BudgetExceeded, ValueError) as exc:
            st.error(str(exc))
            st.info("Retry Analyze Waivers after refreshing the league or resolving the reported source error. No replacement data was substituted.")
            return
    run = st.session_state["waiver_run"]
    evidence = st.session_state["waiver_snapshot"]
    if snapshot.league_id != run.league_id or roster_id != run.roster_id:
        return
    current = {p: r.roster_id for r in snapshot.rosters for p in owned(r)}
    previous = {p: r.roster_id for r in evidence.rosters for p in owned(r)}
    if current != previous or snapshot.scoring != evidence.scoring:
        st.warning("League ownership/scoring changed. Analyze Waivers again before using these results.")
        return
    st.caption(f"Ownership checked {ui.local_time(run.snapshot_at)} · Forecast weeks {run.start_week}–{run.end_week} · {run.free_players_evaluated} evaluated free players of {run.free_players_checked:,} unowned catalog players")
    st.caption(f"Applied priority: {run.strategy}. Protections: {', '.join(_name(evidence,p) for p in run.protected) or 'IR/taxi only'}. Submit Analyze Waivers to apply changed priorities/protections.")
    a,b,c=st.columns(3)
    a.metric("Evaluated free players",run.free_players_evaluated)
    b.metric("Pickup alternatives",len(run.pickups))
    c.metric("Forecast window",f"W{run.start_week}–{run.end_week}")
    budget=run.waiver_budget
    if budget.get("remaining") is not None:
        st.caption(f"Reported remaining FAAB: ${budget['remaining']} · Minimum bid: ${budget['minimum_bid']:g}. Commissioner adjustments and pending claims require verification in Sleeper.")
    elif budget.get("limitation"):st.caption(budget["limitation"])
    with st.expander("Evidence freshness and limitations"):
        for warning in run.warnings:
            st.write(warning)
        for source in run.sources:
            st.link_button(source.name, source.url)
            st.caption(f"Retrieved {ui.local_time(source.retrieved_at)} · Source update: {source.source_updated_at or 'see source data dates'}")
    pickups = [p for p in run.pickups if position == "All" or run.evaluations[p.player_id].position == position]
    st.subheader("Ranked pickup / drop recommendations")
    st.caption("Each row is an alternative single claim, not a sequence. Re-analyze after a successful roster move.")
    if pickups:
        st.dataframe([{"Pickup": _name(evidence,p.player_id), "Drop": _name(evidence,p.drop_id),
            "Position": run.evaluations[p.player_id].position, "Type": p.kind, "Next-week lineup Δ": round(p.next_week_gain,2),
            "ROS lineup Δ": round(p.ros_gain,2), "Bench surplus Δ": round(p.bench_change,2),
            "Dynasty index Δ": p.dynasty_change, "Confidence": p.confidence,
            "FAAB range (subjective)": "–".join(str(x) for x in p.faab["range"]) if p.faab.get("range") is not None else "Not established",
            "Opportunity signal /100": p.breakout_score} for p in pickups], hide_index=True, width="stretch")
    else:
        st.info("No supported pickup/drop improves the modeled roster with these filters and protections. The watch list below separates emerging opportunity from established upgrades.")
    st.subheader("Breakout opportunity watch")
    scope = st.selectbox("Watch-list ownership", ["Available players", "My team", "Entire league"])
    signals = [b for b in run.breakouts if (position == "All" or run.evaluations[b.player_id].position == position)
               and (scope == "Entire league" or scope == "Available players" and b.player_id not in current
                    or scope == "My team" and current.get(b.player_id) == roster_id)]
    st.caption("Signals use recent vs prior verified appearances, weighted opportunity, snaps, target share and red-zone work. Touchdowns/points do not increase the score. This is a heuristic ranking, not a probability.")
    if signals:
        def metric(signal, name):
            return next((m for m in signal.changes if m.metric == name), None)
        st.dataframe([{"Player": _name(evidence,b.player_id), "Position": run.evaluations[b.player_id].position,
            "Signal /100": b.score, "Evidence": b.label, "Confidence": b.confidence,
            "Recent games": b.recent_games, "Prior games": b.prior_games,
            "Recent opportunities/game": metric(b,"opportunities").recent,
            "Prior opportunities/game": metric(b,"opportunities").prior,
            "Snap-share change": metric(b,"snap_share").change,
            "Why watch": " ".join(b.reasons)} for b in signals], hide_index=True, width="stretch")
    else:
        st.caption("No positive opportunity signals meet this ownership/position filter.")
    candidates = list(dict.fromkeys([p.player_id for p in pickups] + [s.player_id for s in signals]))
    if candidates:
        selected = st.selectbox("Player details and current research", candidates, format_func=lambda p: _name(evidence,p))
        pickup = next((p for p in pickups if p.player_id == selected), None)
        signal = next((s for s in signals if s.player_id == selected), None)
        value = run.evaluations[selected]
        with st.container(border=True):
            st.subheader(_name(evidence,selected))
            if pickup:
                st.write(f"**Pickup:** {_name(evidence, selected)} · **Drop:** {_name(evidence,pickup.drop_id)}")
                a,b,c = st.columns(3)
                a.metric("Next-week lineup Δ", f"{pickup.next_week_gain:+.2f}")
                b.metric("ROS lineup Δ", f"{pickup.ros_gain:+.2f}")
                c.metric("Confidence", pickup.confidence.title())
                for reason in pickup.reasons:
                    st.write(reason)
                for risk in pickup.risks:
                    st.caption(risk)
                st.caption("FAAB: "+pickup.faab.get("basis","No estimate available."))
                if pickup.faab.get("limitation"):st.caption(pickup.faab["limitation"])
            if signal:
                st.dataframe([c.model_dump() for c in signal.changes], hide_index=True, width="stretch")
                for warning in signal.limitations:
                    st.caption(warning)
            st.write(f"Observed season PPG: {value.season_ppg:.2f} · Recent PPG: {value.recent_ppg:.2f} · Forecast PPG: {value.projected_ppg:.2f} (uncalibrated)")
            st.dataframe(value.weekly_observed, hide_index=True, width="stretch")
        question = st.text_input("Ask about this pickup or role change", placeholder="Is the opportunity sustainable? What current news changes this decision?")
        if st.button("Research and explain", width="stretch"):
            try:
                with st.spinner("Checking current reporting and reasoning about your roster…"):
                    answer, bundle = service.explain(evidence, run, selected, question)
                st.session_state["waiver_answers"][selected] = (answer,bundle)
            except (DataUnavailable, ProviderUnavailable, BudgetExceeded, ValueError) as exc:
                st.error(str(exc))
                st.caption("Numerical results remain available. Retry the request after resolving the reported API issue.")
        if selected in st.session_state["waiver_answers"]:
            answer,bundle = st.session_state["waiver_answers"][selected]
            st.markdown(answer)
            ui.sources_view(bundle)
    st.download_button("Export waiver analysis", run.model_dump_json(indent=2), file_name=f"waivers-{run.league_id}.json", mime="application/json")
    with st.expander("Full available-player directory"):
        ui.waivers(snapshot)
