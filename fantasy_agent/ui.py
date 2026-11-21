"""Small Streamlit presentation components; no provider calls here."""
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
import altair as alt
from . import design

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
    from .roster_cards import roster_grid
    st.subheader(roster.manager)
    slot_names=[s for s in snapshot.roster_positions if s not in {"BN","IR","TAXI"}]
    slots={pid:slot for pid,slot in zip(roster.starters,slot_names) if pid!="0"}
    groups = {"Starters": list(dict.fromkeys(p for p in roster.starters if p!="0")),
              "Bench": sorted(owned(roster)-set(roster.starters+roster.reserve+roster.taxi),key=lambda p:snapshot.players[p].name),
              "Injured reserve": roster.reserve, "Taxi squad": roster.taxi}
    st.caption("Headshots from Sleeper; initials appear when a photo is unavailable. Injury labels reflect the dated player catalog, not medical clearance.")
    for label,ids in groups.items():
        with st.expander(f"{label} · {len(ids)}",expanded=label in {"Starters","Bench"}):
            if ids:st.html(roster_grid(snapshot,ids,slots if label=="Starters" else None))
            else:st.caption("No players in this group.")


def standings(snapshot, selected_id=None):
    from .standings_ui import render_standings
    render_standings(snapshot, selected_id)


def overview(snapshot, roster):
    cols = st.columns(4)
    cols[0].metric("PLAYERS OWNED", len(owned(roster)))
    cols[1].metric("LEAGUE FORMAT", snapshot.league_type.title())
    cols[2].metric("TEAMS", len(snapshot.rosters))
    cols[3].metric("ELIGIBLE FREE PLAYERS", f"{len(free_players(snapshot)):,}")
    st.space("small")
    left, middle, right = st.columns(3, border=True)
    counts=depth(snapshot,roster)
    colors=["#36ddd1","#338df0","#ad91ee","#edc86a","#f080a1"]
    chart_data=pd.DataFrame([{"Position":p,"Players":n} for p,n in counts.items()])
    with left:
        st.subheader("◈  Roster depth")
        st.caption("Eligible positions · includes IR / taxi")
        if counts:
            st.space("small")
            chart=alt.Chart(chart_data).mark_bar(cornerRadiusTopLeft=5,cornerRadiusTopRight=5,size=30).encode(
                x=alt.X("Position:N",axis=alt.Axis(labelAngle=0,title=None)),y=alt.Y("Players:Q",axis=alt.Axis(tickMinStep=1,title=None)),
                color=alt.Color("Position:N",scale=alt.Scale(range=colors),legend=None),tooltip=["Position","Players"])
            st.altair_chart(chart.properties(height=200).configure(background="transparent").configure_axis(labelColor="#a6bdcc",gridColor="#233747",domain=False),width="stretch",theme=None)
    with middle:
        st.subheader("◎  Positional mix")
        st.caption("Share of position eligibility")
        if counts:
            # Keep the legend outside Vega's fit layout so it cannot shrink or
            # clip the circle, or leave a large blank band inside the chart.
            positions=sorted(counts)
            donut=alt.Chart(chart_data).mark_arc(innerRadius=alt.ExprRef(expr="max(0, min(width, height) / 2 - 6) * 0.68"),outerRadius=alt.ExprRef(expr="max(0, min(width, height) / 2 - 6)"),cornerRadius=3).encode(theta="Players:Q",color=alt.Color("Position:N",scale=alt.Scale(domain=positions,range=colors),legend=None),tooltip=["Position","Players"])
            st.altair_chart(donut.properties(height=180).configure(background="transparent"),width="stretch",theme=None)
            st.html('<div class="ff-mix-legend">'+''.join(f'<span><i style="background:{colors[i%len(colors)]}"></i>{escape(p)}</span>' for i,p in enumerate(positions))+'</div>')
    with right:
        st.subheader("↗  Your next moves")
        empty=roster.starters.count("0")
        design.row("Saved lineup",f"{empty} empty slots" if empty else "All starter slots filled", "Review" if empty else "Filled")
        design.row("Roster availability",f"{len(roster.reserve)} IR · {len(roster.taxi)} taxi",f"{sum(bool(snapshot.players[p].injury_status) for p in owned(roster))} flags")
        design.link("Optimize this week →","Lineup Optimizer","overview_lineup")
        def ask_strategy():
            st.session_state["workspace"]="AI Analyst"
            st.session_state["queued_question"]="Analyze my entire league and tell me the best moves I can make to improve my team. Prioritize specific actions supported by current evidence."
        st.button("Analyze my team with AI",on_click=ask_strategy,type="primary",width="stretch")
    st.caption("Charts count position eligibility, so multi-position players can count twice. Catalog injury flags are not medical clearance.")
    waivers=st.session_state.get('waiver_run');trades=st.session_state.get('trade_run');breakouts=st.session_state.get('breakout_run')
    bench=owned(roster)-set(roster.starters+roster.reserve+roster.taxi)
    pool=free_players(snapshot)
    pool_counts={pos:sum(pos in p.positions for p in pool) for pos in ("QB","RB","WR","TE")}
    pool_detail=" · ".join(f"{n} {pos}" for pos,n in pool_counts.items())
    active=owned(roster)-set(roster.reserve+roster.taxi)
    capacity=sum(slot not in {"IR","TAXI"} for slot in snapshot.roster_positions)
    openings=max(0,capacity-len(active))
    flags=[snapshot.players[p] for p in sorted(owned(roster)) if snapshot.players[p].injury_status]
    bench_positions={}
    for pid in bench:
        position=" / ".join(snapshot.players[pid].positions) or "Unknown"
        bench_positions[position]=bench_positions.get(position,0)+1
    breakdown=" · ".join(f"{n} {p}" for p,n in sorted(bench_positions.items())) or "No bench players outside IR / taxi"
    previews={
        "Waiver Wire":[("Position supply",pool_detail,f"{len(pool):,} free"),
                       ("Roster room",f"{len(active)} active players · {capacity} active slots",f"{openings} open"),
                       ("Availability watch",", ".join(p.name for p in flags[:2]) if flags else "No injury designations in the current catalog",f"{len(flags)} flags")],
        "Trade Finder":[("League market",snapshot.league_type.title()+" · Actual opponent rosters",f"{max(0,len(snapshot.rosters)-1)} rivals"),
                        ("Your bench",breakdown,f"{len(bench)} players"),
                        ("Consolidation route","Compare depth packages for a starter upgrade.","2-for-1")],
        "Breakout Radar":[("Your bench watch",", ".join(snapshot.players[p].name for p in sorted(bench,key=lambda p:snapshot.players[p].name)[:2]) or "Your bench is currently empty",f"{len(bench)} players"),
                          ("Available scouting pool",pool_detail,f"{sum(bool(set(p.positions)&{'QB','RB','WR','TE'}) for p in pool):,} offense"),
                          ("Follow role growth","Compare targets, carries and snap share across verified games.","Usage")]
    }
    for col,title,page,run,items in zip(st.columns(3),["◇  Waiver shortlist","⇄  Trade opportunities","↗  Breakout watch"],
            ["Waiver Wire","Trade Finder","Breakout Radar"],[waivers,trades,breakouts],
            [waivers.pickups if waivers else [],trades.trades if trades else [],breakouts.signals if breakouts else []]):
        with col,st.container(border=True,height="stretch",key="overview_opportunity_"+page.replace(" ","_")):
            st.subheader(title)
            rows=[]
            if run:
                st.caption("Last analysis · "+local_time(run.snapshot_at))
                for item in items[:3]:
                    if page=="Trade Finder":
                        opponent=next((r.manager for r in snapshot.rosters if r.roster_id==item.opponent_id),f"Roster {item.opponent_id}")
                        rows.append((" + ".join(snapshot.players[p].name for p in item.receive),"With "+opponent+" · Send: "+" + ".join(snapshot.players[p].name for p in item.send),f"{item.my_ros_gain:+.1f} ROS"))
                    else:
                        player=snapshot.players[item.player_id]
                        detail=" / ".join(player.positions)+" · "+(player.team or "No NFL team")
                        if page=="Waiver Wire":
                            detail+=" · Drop "+snapshot.players[item.drop_id].name if item.drop_id else " · Open-slot pickup"
                        else:
                            detail+=" · "+item.label
                        rows.append((player.name,detail,f"{item.ros_gain:+.1f} ROS" if page=="Waiver Wire" else f"{item.score:.0f} signal"))
                note={"Trade Finder":"Review both teams’ gains, confidence and required drops. ROS gains are estimates.",
                      "Waiver Wire":"Each pickup is an alternative. Review required drops, confidence and claim eligibility.",
                      "Breakout Radar":"Signals reflect measured role changes. Review the usage windows and evidence coverage."}[page]
                if not items:note="No qualifying results in the last analysis. Current roster context is shown here."
            else:
                st.caption("Not analyzed yet · Current roster context")
                note={"Trade Finder":"Roster depth is context. Analysis checks player eligibility, package balance and both teams’ gains.",
                      "Waiver Wire":"Pool counts describe availability. Run analysis for ranked pickup/drop gains and claim guidance.",
                      "Breakout Radar":"Bench names are an unranked watch pool. Run analysis to find measured opportunity growth."}[page]
            rows+=previews[page][len(rows):]
            st.html('<div class="ff-opportunity-content">'+''.join(
                '<div class="ff-row"><div class="ff-opportunity-copy"><b title="'+escape(str(name),quote=True)+'">'+escape(str(name))+'</b><small title="'+escape(str(detail),quote=True)+'">'+escape(str(detail))+'</small></div><span class="ff-pill">'+escape(str(value))+'</span></div>'
                for name,detail,value in rows)+'</div><p class="ff-opportunity-note">'+escape(note)+'</p>')
            st.space("stretch")
            design.link("Open "+page+" →",page,"overview_"+page)
    with st.container(border=True):
        st.subheader("♜  League standings")
        standings(snapshot, roster.roster_id)


def league_view(snapshot):
    names = {r.roster_id: r.manager for r in snapshot.rosters}
    rid = st.selectbox("Inspect team", list(names), format_func=names.get)
    r = next(r for r in snapshot.rosters if r.roster_id == rid)
    roster_tab,matchup_tab,rules_tab,activity_tab=st.tabs(["Roster & depth","Weekly matchups","Scoring & rules","League activity"])
    with roster_tab:
        a,b,c,d=st.columns(4)
        for col,label,value in zip([a,b,c,d],["Owned","Starters","Injured reserve","Taxi squad"],[len(owned(r)),len(set(r.starters)-{"0"}),len(r.reserve),len(r.taxi)]):col.metric(label,value)
        roster_view(snapshot,r)
    with matchup_tab:
        st.subheader(f"Week {snapshot.week} scoreboard")
        from .matchup_cards import scoreboard,team_records
        st.caption("Scores reflect the last league refresh; a lead is not a final result. Use Refresh league for the latest scores.")
        if snapshot.matchups:st.html(scoreboard(snapshot))
        else:st.info("No matchup data was returned. Check data notices for upstream failures.")
        st.subheader("League records")
        st.caption("Wins – losses – ties · Ordered by wins, then points for. Custom playoff tiebreakers are not modeled.")
        st.html(team_records(snapshot))
    with rules_tab:
        from .rules_ui import render_rules
        render_rules(snapshot)
    with activity_tab:
        from .activity_ui import render_activity
        render_activity(snapshot)


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
