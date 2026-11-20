"""Small Streamlit presentation components; no provider calls here."""
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st

from .analysis import depth, free_players, owned
from .models import Snapshot


def local_time(value: datetime) -> str:
    return value.astimezone(ZoneInfo("America/Chicago")).strftime("%b %d, %Y · %I:%M:%S %p %Z")


def player_table(snapshot: Snapshot, ids: list[str] | set[str]):
    rows = []
    for pid in ids:
        if pid == "0":
            continue
        p = snapshot.players[pid]
        rows.append({"Player": p.name, "Position": "/".join(p.positions), "NFL team": p.team or "—",
                     "Catalog injury": p.injury_status or "—", "Sleeper ID": pid})
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.caption("No players in this group.")


def roster_view(snapshot, roster):
    st.subheader(roster.manager)
    groups = {"Starters": set(roster.starters) - {"0"},
              "Bench": owned(roster) - set(roster.starters + roster.reserve + roster.taxi),
              "Injured reserve": set(roster.reserve), "Taxi squad": set(roster.taxi)}
    for label, ids in groups.items():
        with st.expander(f"{label} · {len(ids)}", expanded=label in {"Starters", "Bench"}):
            player_table(snapshot, sorted(ids))


def standings(snapshot):
    rows = []
    for r in snapshot.rosters:
        s = r.settings
        rows.append({"Team": r.manager, "Wins": s.get("wins", 0), "Losses": s.get("losses", 0),
                     "Ties": s.get("ties", 0), "Points for": s.get("fpts", 0) + s.get("fpts_decimal", 0) / 100})
    st.dataframe(pd.DataFrame(rows).sort_values(["Wins", "Points for"], ascending=False),
                 hide_index=True, width="stretch")
    st.caption("Record table sorted by wins, then points; custom standings and playoff tiebreakers are not modeled.")


def overview(snapshot, roster):
    cols = st.columns(4)
    cols[0].metric("Players owned", len(owned(roster)))
    cols[1].metric("League format", snapshot.league_type.title())
    cols[2].metric("Teams", len(snapshot.rosters))
    cols[3].metric("Eligible free players", len(free_players(snapshot)))
    left, right = st.columns([1, 1.2])
    with left:
        with st.container(border=True):
            st.subheader("Roster depth")
            counts = depth(snapshot, roster)
            if counts:
                st.bar_chart(pd.DataFrame({"Players": counts}), color="#20bfa9")
            st.caption("Counts reflect eligible positions, including IR/taxi. Multi-position players may count twice.")
    with right:
        with st.container(border=True):
            st.subheader("Your next moves")
            empty = roster.starters.count("0")
            if empty:
                st.warning(f"{empty} starter slot(s) empty in the saved Sleeper lineup.")
            else:
                st.write("All saved starter slots are filled.")
            st.write("Review scoring and roster rules in My League, inspect your bench, then ask the AI Analyst a focused question.")
            st.info("Open Trade Finder to load statistical team-needs analysis and ranked opportunities. This overview reports roster facts without estimating player values.")
    st.subheader("League record table")
    standings(snapshot)
    def ask_strategy():
        st.session_state["workspace"]="AI Analyst"
        st.session_state["queued_question"]="Analyze my entire league and tell me the best moves I can make to improve my team. Prioritize specific actions supported by current evidence."
    st.button("Analyze my team with AI",on_click=ask_strategy,type="primary")


def league_view(snapshot):
    names = {r.roster_id: r.manager for r in snapshot.rosters}
    rid = st.selectbox("Inspect team", list(names), format_func=names.get)
    r = next(r for r in snapshot.rosters if r.roster_id == rid)
    roster_view(snapshot, r)
    st.caption("Position counts describe each opponent's depth; Trade Finder loads statistical evaluations for competitive needs.")
    st.write(depth(snapshot, r))
    with st.expander("League scoring and requirements"):
        st.write("Starter and bench slots", snapshot.roster_positions)
        st.json(snapshot.scoring)
        st.json(snapshot.settings)
        if snapshot.metadata:
            st.json(snapshot.metadata)
    for field, label in [("matchups", f"Week {snapshot.week} matchups and scores"),
                         ("transactions", f"Week {snapshot.week} transactions (including completed trades)"),
                         ("traded_picks", "Traded draft picks"), ("drafts", "Draft metadata")]:
        with st.expander(label):
            if any(w.startswith(field + " unavailable") for w in snapshot.warnings):
                st.warning("This data was unavailable on the last refresh.")
            else:
                st.json(getattr(snapshot, field))
    st.caption("Draft metadata and traded-pick records are shown. This view does not provide a complete historical transaction log, draft selections or future-pick inventory.")


def waivers(snapshot):
    st.subheader("Available player directory")
    st.caption("Alphabetical ownership directory, including all roster/IR/taxi exclusions. Statistical pickup and breakout rankings appear above.")
    candidates = free_players(snapshot)
    col1, col2 = st.columns([2, 1])
    query = col1.text_input("Find available player", placeholder="Player name")
    positions = sorted({pos for p in candidates for pos in p.positions})
    pos = col2.selectbox("Position", ["All"] + positions)
    filtered = [p for p in candidates if query.casefold() in p.name.casefold() and (pos == "All" or pos in p.positions)]
    st.caption(f"{len(filtered):,} matching players. Catalog marked active and eligible for a league position; check Sleeper for waiver locks and claim eligibility.")
    page = st.number_input("Page (100 players each)", min_value=1,
                           max_value=max(1, (len(filtered) + 99) // 100), value=1)
    player_table(snapshot, [p.player_id for p in filtered[(page - 1) * 100:page * 100]])


def sources_view(bundle):
    if not bundle:
        return
    with st.expander("Research evidence", expanded=True):
        st.caption(f"Query: {bundle.query} · retrieved {local_time(bundle.retrieved_at)}")
        if not bundle.sources:
            st.warning("No sources returned; no current-news evidence was added.")
        for source in bundle.sources:
            st.link_button(source.title, source.url)
            st.caption(f"Published: {source.published_at or 'not supplied'} · retrieved {local_time(source.retrieved_at)}")
            st.write(source.excerpt)
