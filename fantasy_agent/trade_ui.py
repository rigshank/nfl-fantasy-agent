"""Trade Finder extension using the dashboard's existing cards and tables."""
import streamlit as st
from .analysis import owned
from .evaluation import OFFENSE
from .integrations.research import ProviderUnavailable
from .integrations.sleeper import DataUnavailable
from .models import utcnow
from .storage import BudgetExceeded
from .trade_models import TradeOptions
from .trade_service import TradeService
from . import ui


STRUCTURES = {"All supported": [(1, 1), (2, 1), (2, 2), (3, 2), (1, 2), (2, 3)],
              "1-for-1": [(1, 1)], "2-for-1": [(2, 1)], "2-for-2": [(2, 2)],
              "3-for-2": [(3, 2)], "1-for-2": [(1, 2)], "2-for-3": [(2, 3)], "3-for-1": [(3, 1)]}


def names(snapshot, ids):
    return ", ".join(snapshot.players[p].name for p in ids) or "None"


def _lineup_table(snapshot, lineup):
    return [{"Slot": slot, "Player": snapshot.players[pid].name if pid else "Unfilled / unmodeled",
             "Projected points": round(points, 2)} for slot, pid, points in lineup.assignments]


def render_trade_finder(snapshot, roster_id, league_service, config, store):
    st.subheader("Find realistic trades")
    st.caption("Python compares both teams' optimal offensive lineups, roster depth and replacement costs. Gemini explanations are optional.")
    if snapshot.week >= 18:
        st.info("No future regular-season weeks remain for this trade model.")
        return
    roster = next(r for r in snapshot.rosters if r.roster_id == roster_id)
    opponent_names = {r.roster_id: r.manager for r in snapshot.rosters if r.roster_id != roster_id}
    available = sorted(p for p in owned(roster) - set(roster.reserve + roster.taxi) if OFFENSE.intersection(snapshot.players[p].positions))
    with st.form("trade_filters"):
        a, b, c = st.columns(3)
        position = a.selectbox("Position to acquire", ["Any", "QB", "RB", "WR", "TE"])
        structure = b.selectbox("Trade structure", list(STRUCTURES), index=0)
        opponent = c.selectbox("Trading partner", [None] + list(opponent_names),
                               format_func=lambda x: "All opponents" if x is None else opponent_names[x])
        must_send = st.multiselect("Players I want to trade away (all selected must be included)", available,
                                   format_func=lambda pid: snapshot.players[pid].name)
        d, e = st.columns(2)
        start = d.number_input("First forecast week", min_value=snapshot.week + 1, max_value=18, value=snapshot.week + 1)
        end = e.number_input("Last fantasy week", min_value=snapshot.week + 1, max_value=18, value=max(snapshot.week + 1, 17))
        with st.expander("Ranking controls and refresh"):
            st.caption("All scores here are transparent heuristics, not probabilities. Both teams must meet the minimum ROS lineup benefit.")
            imbalance = st.slider("Maximum package imbalance", .05, .6, .4, .05)
            my_gain = st.number_input("Minimum my ROS lineup gain (points)", min_value=0.0, value=1.0)
            opponent_gain = st.number_input("Minimum opponent ROS lineup gain (points)", min_value=0.0, value=0.0)
            consolidation = st.slider("Consolidation ranking weight", 0.0, 1.0, .1, .05)
            opponent_weight = st.slider("Opponent benefit ranking weight", 0.0, 2.0, .35, .05)
            risk_weight = st.slider("Risk ranking penalty weight", 0.0, 2.0, .2, .05)
            force_stats = st.checkbox("Refresh statistics too (otherwise reuse six-hour cache)", value=False)
        submitted = st.form_submit_button("Find Best Trades", type="primary", width="stretch")
    service = TradeService(config, store, league_service)
    identity = (snapshot.league_id, roster_id)
    if st.session_state.get("trade_identity") != identity:
        for key in ["trade_run", "trade_snapshot", "trade_explanations", "trade_history"]:
            st.session_state.pop(key, None)
        st.session_state["trade_identity"] = identity
    if submitted:
        try:
            options = TradeOptions(structures=STRUCTURES[structure], opponent_id=opponent,
                receive_position=None if position == "Any" else position, must_send=must_send,
                max_value_imbalance=imbalance, min_my_ros_gain=my_gain, min_opponent_ros_gain=opponent_gain,
                consolidation_weight=consolidation, opponent_weight=opponent_weight, risk_weight=risk_weight)
            with st.spinner("Refreshing league, evaluating opportunities and comparing legal trades…"):
                fresh, run = service.find(snapshot, roster_id, options, start, end, force_stats)
            st.session_state["trade_run"], st.session_state["trade_snapshot"] = run, fresh
            st.session_state["trade_explanations"] = {}
            st.session_state["trade_history"] = {}
            st.session_state["snapshot"] = fresh
            st.rerun()
        except (DataUnavailable, ProviderUnavailable, BudgetExceeded, ValueError) as exc:
            st.error(f"Trade discovery stopped: {exc}")
            st.session_state.pop("trade_run", None)
    run = st.session_state.get("trade_run")
    if not run:
        st.info("Choose filters, then Find Best Trades. Statistics are fetched only on request; AI/search credits are not needed.")
        return
    evidence_snapshot = st.session_state["trade_snapshot"]
    stale = ((utcnow() - run.snapshot_at).total_seconds() > config.league_cache_seconds
             or snapshot.refreshed_at != run.snapshot_at)
    st.caption(f"Analyzed {ui.local_time(run.snapshot_at)} · Forecast weeks {run.start_week}–{run.end_week} · {run.candidates_evaluated:,} packages evaluated")
    with st.expander("Data coverage, sources and model assumptions", expanded=not run.trades):
        for warning in run.warnings:
            st.write(warning)
        for source in run.sources:
            if source.url.startswith("https://"):
                st.link_button(source.name, source.url)
            else:
                st.write(source.name)
            st.caption(f"Retrieved {ui.local_time(source.retrieved_at)} · Source update: {source.source_updated_at or 'not supplied; inspect data dates'}")
        st.caption("Forecast: 65% last-four-game volume + 35% season volume; efficiency and touchdown rates shrink toward position averages. Matchup factors capped at ±15%. No verified recovery timelines. No waiver claims assumed.")
        st.caption("Rank = (my ROS gain + opponent weight × opponent ROS gain) / weeks + consolidation bonus − imbalance − risk penalty − bench-depth penalty. Medium is the highest confidence until out-of-time calibration.")
    st.subheader("League-wide team-needs matrix")
    st.dataframe([{"Team": t.manager, "Coverage": f"{t.coverage:.0%}", "Next-week offense": round(t.next_lineup.total, 1),
                   "ROS offense": round(t.ros_total, 1), "Relative strengths": ", ".join(t.strengths),
                   "Relative needs": ", ".join(t.needs), "Bench above replacement": str(t.bench_depth),
                   "Injured": names(evidence_snapshot, t.injured), "Expendable candidates": names(evidence_snapshot, t.expendable),
                   "Partner eligible": t.eligible_partner, "Limitations": "; ".join(t.warnings)} for t in run.teams], hide_index=True, width="stretch")
    st.caption("Needs are relative positional depth/quality signals; playoff qualification and manager preferences are not inferred.")
    if stale:
        st.warning("These calculations are stale or the league was refreshed. Click Find Best Trades to recompute before using recommendations.")
        return
    if not run.trades:
        st.info("No qualifying trades. Try another structure or opponent; the engine will not force an unfavorable or unsupported offer.")
        return
    st.subheader("Ranked trade opportunities")
    st.dataframe([{"Rank": i + 1, "Opponent": opponent_names.get(t.opponent_id, str(t.opponent_id)),
                   "Send": names(evidence_snapshot, t.send), "Receive": names(evidence_snapshot, t.receive),
                   "My next-week Δ": round(t.my_week_gain, 2), "My ROS Δ": round(t.my_ros_gain, 2),
                   "Opponent ROS Δ": round(t.opponent_ros_gain, 2), "Balance / 100 (heuristic)": round(t.balance_score),
                   "Rank score (heuristic)": round(t.rank_score, 2), "Confidence": t.confidence} for i, t in enumerate(run.trades)],
                 hide_index=True, width="stretch")
    selected_id = st.selectbox("Detailed trade", [t.trade_id for t in run.trades],
        format_func=lambda tid: f"#{next(i + 1 for i,t in enumerate(run.trades) if t.trade_id == tid)} · " +
            opponent_names.get(next(t.opponent_id for t in run.trades if t.trade_id == tid), "Opponent"))
    trade = next(t for t in run.trades if t.trade_id == selected_id)
    with st.container(border=True):
        st.subheader(f"Trade with {opponent_names.get(trade.opponent_id, 'opponent')}")
        st.write("**You send:** " + names(evidence_snapshot, trade.send))
        st.write("**You receive:** " + names(evidence_snapshot, trade.receive))
        cols = st.columns(4)
        cols[0].metric("Your ROS lineup Δ", f"{trade.my_ros_gain:+.1f}")
        cols[1].metric("Opponent ROS lineup Δ", f"{trade.opponent_ros_gain:+.1f}")
        cols[2].metric("Balance · heuristic", f"{trade.balance_score:.0f}/100")
        cols[3].metric("Confidence · uncalibrated", trade.confidence.title())
        for reason in trade.reasons:
            st.write(reason)
        st.caption(f"Balance basis: {trade.value_basis}")
        if trade.my_dynasty_gain is not None:
            st.write(f"Long-term community market value Δ: you {trade.my_dynasty_gain:+.0f}; opponent {trade.opponent_dynasty_gain:+.0f}. These units are not fantasy points.")
        if trade.my_drops or trade.opponent_drops:
            st.warning(f"Required drops — you: {names(evidence_snapshot, trade.my_drops)}; opponent: {names(evidence_snapshot, trade.opponent_drops)}. The offer is conditional on these actions.")
        st.write(f"Remaining bench value Δ above replacement (points/game): you {trade.my_bench_change:+.2f}; opponent {trade.opponent_bench_change:+.2f}.")
        if trade.my_playoff_gain is not None:
            st.caption(f"Conditional playoff-week lineup Δ: you {trade.my_playoff_gain:+.1f}, opponent {trade.opponent_playoff_gain:+.1f}. Qualification is not estimated.")
        left, right = st.columns(2)
        before_mine = next(t.next_lineup for t in run.teams if t.roster_id == roster_id)
        before_theirs = next(t.next_lineup for t in run.teams if t.roster_id == trade.opponent_id)
        with left:
            st.write(f"**Your week {run.start_week} offense:** {before_mine.total:.1f} → {trade.my_after.total:.1f}")
            st.dataframe(_lineup_table(evidence_snapshot, trade.my_after), hide_index=True, width="stretch")
        with right:
            st.write(f"**Opponent week {run.start_week} offense:** {before_theirs.total:.1f} → {trade.opponent_after.total:.1f}")
            st.dataframe(_lineup_table(evidence_snapshot, trade.opponent_after), hide_index=True, width="stretch")
        for risk in trade.risks:
            st.caption(risk)
    with st.expander("Player comparison and observed evidence", expanded=True):
        st.dataframe([{"Player": evidence_snapshot.players[p].name, "ID": p, "Games": run.evaluations[p].games,
                       "Season PPG (observed)": round(run.evaluations[p].season_ppg, 2),
                       "Last 4 PPG (observed)": round(run.evaluations[p].recent_ppg, 2),
                       "Forecast PPG (heuristic)": round(run.evaluations[p].projected_ppg, 2),
                       "Recent targets/game": run.evaluations[p].targets, "Recent carries/game": run.evaluations[p].carries,
                       "RZ targets/game (PBP)": run.evaluations[p].red_zone_targets,
                       "RZ carries/game (PBP)": run.evaluations[p].red_zone_carries,
                       "Goal-line carries/game (PBP)": run.evaluations[p].goal_line_carries,
                       "Snap share": run.evaluations[p].snap_pct, "Recent offensive snaps/game": run.evaluations[p].recent_snaps,
                       "Opportunity trend": run.evaluations[p].opportunity_trend,
                       "Historical points SD": run.evaluations[p].consistency_sd,
                       "TD share of observed points": run.evaluations[p].td_share,
                       "NFL offense points/game (context)": run.evaluations[p].offensive_environment,
                       "Historical floor (20th %)": round(run.evaluations[p].floor, 2),
                       "Historical upside (80th %)": round(run.evaluations[p].upside, 2),
                       "Trend": run.evaluations[p].trend, "Age": run.evaluations[p].age,
                       "Dynasty index": run.evaluations[p].dynasty_value, "Dynasty date": run.evaluations[p].dynasty_date}
                      for p in trade.send + trade.receive], hide_index=True, width="stretch")
        st.dataframe([{"Player": evidence_snapshot.players[p].name, "Week": week, "Opponent": run.evaluations[p].opponents[week],
                       "Matchup factor": run.evaluations[p].schedule_factors[week], "Forecast points": run.evaluations[p].weekly[week]}
                      for p in trade.send + trade.receive for week in range(run.start_week, run.end_week + 1)], hide_index=True, width="stretch")
    st.subheader("Ask Gemini about this trade")
    web = st.checkbox("Research this package first · one Tavily search", value=False)
    question = st.text_input("Trade follow-up", placeholder="Why might this manager accept? What evidence could change the decision?")
    if st.button("Request detailed analysis", width="stretch"):
        try:
            history = st.session_state["trade_history"].get(selected_id, [])
            with st.spinner("Reviewing this trade and its evidence…"):
                answer, bundle = service.explain(evidence_snapshot, run, trade, question, history, web)
            st.session_state["trade_explanations"][selected_id] = (answer, bundle)
            st.session_state["trade_history"][selected_id] = (history + [{"role": "user", "content": question}, {"role": "assistant", "content": answer}])[-6:]
        except (DataUnavailable, ProviderUnavailable, BudgetExceeded, ValueError) as exc:
            st.warning(f"Explanation unavailable. Deterministic calculations remain visible. {exc}")
    if selected_id in st.session_state["trade_explanations"]:
        answer, bundle = st.session_state["trade_explanations"][selected_id]
        st.markdown(answer)
        ui.sources_view(bundle)
    st.download_button("Export trade analysis", run.model_dump_json(indent=2),
                       file_name=f"trades-{run.league_id}.json", mime="application/json")
