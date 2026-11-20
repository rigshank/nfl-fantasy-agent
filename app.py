"""Personal, real-data Sleeper dashboard. Run: python -m streamlit run app.py."""
import streamlit as st
from fantasy_agent import ui, design
from fantasy_agent.config import Config
from fantasy_agent.integrations.sleeper import DataUnavailable, Sleeper
from fantasy_agent.lineup_ui import render_lineup
from fantasy_agent.analyst_ui import render_analyst
from fantasy_agent.models import utcnow
from fantasy_agent.service import LeagueService
from fantasy_agent.storage import BudgetExceeded, Store
from fantasy_agent.trade_ui import render_trade_finder
from fantasy_agent.waiver_ui import render_waivers
from fantasy_agent.breakout_ui import render_breakouts
from fantasy_agent.settings_ui import render_settings
from fantasy_agent.session import clear_analysis,apply_overrides

st.set_page_config(page_title="Fantasy Analyst", page_icon="🏈", layout="wide")
design.theme()
try:
    secrets = dict(st.secrets)
except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
    secrets = {}
config = apply_overrides(Config.load(secrets),st.session_state)
store = Store(config.cache_path)


@st.cache_resource
def sleeper_client(path):
    return Sleeper(Store(path))


service = LeagueService(config, store, sleeper_client(str(config.cache_path)))
if st.session_state.get("application_version") != "production-v3":
    st.session_state.clear()
    st.session_state["application_version"] = "production-v3"
st.session_state.setdefault("messages", [])


def connect(league_id,user_id=None):
    fresh = service.load(league_id, force=True)
    clear_analysis(st.session_state,team_changed=True)
    st.session_state["snapshot"] = fresh
    st.session_state["messages"] = []
    for key in ("team_choice", "team_identity", "waiver_run", "trade_run", "connection_error"):
        st.session_state.pop(key, None)
    st.session_state.pop("sleeper_user_id",None)
    st.session_state.pop("connection_notice",None)
    if user_id:
        st.session_state["sleeper_user_id"]=user_id
    elif config.sleeper_username:
        try:
            st.session_state["sleeper_user_id"] = service.sleeper.user(config.sleeper_username)["user_id"]
        except (DataUnavailable, BudgetExceeded, ValueError) as exc:
            st.session_state["connection_notice"] = str(exc) + " Choose your team manually."


def setup_form():
    with st.form("league_setup"):
        identifier = st.text_input("Sleeper username or league ID", value=config.sleeper_username or config.sleeper_league_id)
        season = st.number_input("Season", min_value=2017, max_value=2100, value=utcnow().year)
        submitted = st.form_submit_button("Connect to Sleeper", type="primary")
    if submitted:
        try:
            with st.spinner("Connecting to Sleeper…"):
                value = identifier.strip()
                if value.isdecimal():
                    connect(value)
                else:
                    user = service.sleeper.user(value)
                    leagues = service.sleeper.leagues(user["user_id"], season)
                    st.session_state["sleeper_user_id"] = user["user_id"]
                    if not leagues:
                        raise DataUnavailable("No NFL leagues found for this username and season. Check the season and try again.")
                    st.session_state["league_choices"] = leagues
                    st.session_state["league_choice_user_id"] = user["user_id"]
                    if len(leagues) == 1:
                        connect(leagues[0]["league_id"],user["user_id"])
            st.rerun()
        except (DataUnavailable, BudgetExceeded, ValueError) as exc:
            st.error(str(exc))
    choices = st.session_state.get("league_choices", [])
    if len(choices) > 1:
        choice = st.selectbox("Choose your league", choices, format_func=lambda x: f"{x['name']} ({x['season']})")
        if st.button("Load selected league"):
            try:
                connect(choice["league_id"],st.session_state.get("league_choice_user_id"))
                st.rerun()
            except (DataUnavailable, BudgetExceeded, ValueError) as exc:
                st.error(str(exc))


if "snapshot" not in st.session_state and config.sleeper_league_id and not st.session_state.get("autoload_attempted"):
    st.session_state["autoload_attempted"] = True
    try:
        with st.spinner("Loading your configured Sleeper league…"):
            connect(config.sleeper_league_id.strip())
    except (DataUnavailable, BudgetExceeded, ValueError) as exc:
        st.session_state["connection_error"] = str(exc)

snapshot = st.session_state.get("snapshot")
if not snapshot:
    st.title("Connect your Sleeper league")
    st.write("Enter your username or league ID to load actual rosters, scoring and available players.")
    if st.session_state.get("connection_error"):
        st.error(st.session_state["connection_error"])
        st.caption("Check the identifier or provider availability, then retry below.")
    setup_form()
    st.stop()

with st.sidebar:
    st.title("🏈 Fantasy Analyst")
    st.html('<div class="ff-eyebrow">FANTASY INTELLIGENCE</div>')
    st.caption(snapshot.name)
    section = st.radio("Workspace", ["Overview", "My League", "Trade Finder", "Waiver Wire", "Breakout Radar", "Lineup Optimizer", "AI Analyst", "Settings"], label_visibility="collapsed",key="workspace",format_func=lambda page: f"{design.ICONS[page]}   {page}")
    rosters = {r.roster_id:r for r in snapshot.rosters}
    owner = st.session_state.get("sleeper_user_id")
    default = next((r.roster_id for r in snapshot.rosters if owner and owner in [r.owner_id] + r.co_owners), None)
    roster_id = st.selectbox("My team", list(rosters), format_func=lambda rid: rosters[rid].manager,
        index=list(rosters).index(default) if default is not None else None, placeholder="Choose your team", key="team_choice")
    if st.session_state.get("connection_notice"):
        st.caption(st.session_state["connection_notice"])
    if st.button("Refresh league", width="stretch"):
        try:
            st.session_state["snapshot"] = service.load(snapshot.league_id, force=True)
            clear_analysis(st.session_state)
            st.rerun()
        except (DataUnavailable, BudgetExceeded, ValueError) as exc:
            st.error(str(exc))
            st.caption("Previous real snapshot retained with its original timestamp. Retry Refresh league.")
    st.caption("Last successful league refresh")
    st.caption(ui.local_time(snapshot.refreshed_at))
    with st.expander("Change league"):
        setup_form()
    with st.expander("Connections"):
        st.caption(f"Gemini: {'configured' if config.gemini_api_key.get_secret_value() else 'missing key'} · {config.gemini_model}")
        st.caption(f"Tavily: {'configured' if config.tavily_api_key.get_secret_value() else 'missing key'}")
        st.download_button("Export league snapshot", snapshot.model_dump_json(indent=2), file_name=f"league-{snapshot.league_id}.json", mime="application/json")

if roster_id is None:
    st.info("Choose your team in the sidebar so recommendations use the correct roster.")
    st.stop()
roster = rosters[roster_id]
identity = (snapshot.league_id, roster_id)
if st.session_state.get("team_identity") != identity:
    st.session_state["team_identity"] = identity
    clear_analysis(st.session_state,team_changed=True)
design.header(section,snapshot,roster)
from html import escape
stale=(utcnow()-snapshot.refreshed_at).total_seconds()>config.league_cache_seconds
status="Refresh recommended" if stale else "League connected"
st.html(f'<div class="ff-sync"><strong>✓ {status}</strong> Snapshot: {escape(ui.local_time(snapshot.refreshed_at))} · Catalog: {escape(ui.local_time(snapshot.catalog_at))}. Refresh league for current ownership.</div>')
if snapshot.warnings:
    with st.expander("Data notices"):
        for warning in snapshot.warnings:
            st.write(warning)

if section == "Overview":
    ui.overview(snapshot,roster)
elif section == "My League":
    ui.league_view(snapshot)
elif section == "Trade Finder":
    render_trade_finder(snapshot,roster_id,service,config,store)
elif section == "Waiver Wire":
    render_waivers(snapshot,roster_id,service,config,store)
elif section == "Breakout Radar":
    render_breakouts(snapshot,roster_id,service,config,store)
elif section == "Lineup Optimizer":
    render_lineup(snapshot,roster_id,service,config,store)
elif section == "AI Analyst":
    render_analyst(snapshot,roster_id,service,config,store)
elif section == "Settings":
    render_settings(snapshot,service,config,store)
