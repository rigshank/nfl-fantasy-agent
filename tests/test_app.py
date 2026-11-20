from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from fantasy_agent.config import Config
from fantasy_agent.integrations.research import ProviderUnavailable
from tests.fixture_stats import trade_demo

APP=Path(__file__).resolve().parents[1]/"app.py"


def boot(config,snapshot=None):
    app=AppTest.from_file(APP)
    app.session_state["application_version"]="production-v3"
    if snapshot:
        app.session_state["snapshot"]=snapshot
        app.session_state["sleeper_user_id"]=snapshot.rosters[0].owner_id
    return app.run(timeout=30)


def test_setup_uses_no_demo_and_requests_only_sleeper_connection(tmp_path):
    c=Config(cache_path=tmp_path/"setup.sqlite3")
    with patch("fantasy_agent.config.Config.load",return_value=c):
        app=boot(c)
        assert not app.exception
        assert app.title[0].value=="Connect your Sleeper league"
        assert not app.toggle
        assert app.text_input[0].label=="Sleeper username or league ID"


def test_all_pages_use_real_data_interfaces_without_demo_toggle(tmp_path):
    c=Config(cache_path=tmp_path/"ui.sqlite3");s,d=trade_demo();s.league_type="redraft"
    with patch("fantasy_agent.config.Config.load",return_value=c), \
         patch("fantasy_agent.service.LeagueService.load",return_value=s), \
         patch("fantasy_agent.integrations.nflverse.NFLVerse.load",return_value=d), \
         patch("fantasy_agent.integrations.nflverse.NFLVerse.csv",return_value=(d.schedule,d.sources[0])):
        app=boot(c,s)
        assert not app.exception and not app.toggle
        assert any(label.endswith("Settings") for label in app.sidebar.radio[0].options)
        for page in ["My League","Trade Finder","Waiver Wire","Breakout Radar","Lineup Optimizer","AI Analyst","Settings"]:
            app.sidebar.radio[0].set_value(page).run(timeout=30)
            assert not app.exception,page
        app.sidebar.radio[0].set_value("AI Analyst").run(timeout=30)
        with patch("fantasy_agent.agent.Analyst.run",return_value=(s,{"role":"assistant","content":"Specific roster evidence","tools":[],"research":{"query":"team","sources":[]},"refreshed_at":s.refreshed_at.isoformat()})):
            app.chat_input[0].set_value("Analyze my team").run(timeout=30)
            assert not app.exception
            assert any("Specific roster evidence" in m.value for m in app.markdown)


def test_waiver_page_computes_and_applies_protected_players(tmp_path):
    c=Config(cache_path=tmp_path/"waiver-ui.sqlite3");s,d=trade_demo();s.league_type="redraft"
    s.roster_positions=s.roster_positions[:-2]
    with patch("fantasy_agent.config.Config.load",return_value=c), \
         patch("fantasy_agent.service.LeagueService.load",return_value=s), \
         patch("fantasy_agent.integrations.nflverse.NFLVerse.load",return_value=d):
        app=boot(c,s)
        app.sidebar.radio[0].set_value("Waiver Wire").run(timeout=30)
        assert not app.exception
        assert app.session_state["waiver_run"].pickups
        protect=next(m for m in app.multiselect if m.label=="Never recommend dropping")
        protect.set_value(s.rosters[0].players)
        next(b for b in app.button if b.label=="Analyze Waivers").click().run(timeout=30)
        assert not app.exception
        assert not app.session_state["waiver_run"].pickups


def test_configured_league_auto_connects_without_demo(tmp_path):
    s,d=trade_demo();c=Config(cache_path=tmp_path/"auto.sqlite3",sleeper_league_id=s.league_id)
    with patch("fantasy_agent.config.Config.load",return_value=c), \
         patch("fantasy_agent.service.LeagueService.load",return_value=s) as load:
        app=boot(c)
        assert not app.exception
        assert app.session_state["snapshot"].league_id==s.league_id
        load.assert_called_once()
        assert not app.toggle


def test_connection_failure_shows_actual_error_without_fake_data(tmp_path):
    from fantasy_agent.integrations.sleeper import DataUnavailable
    c=Config(cache_path=tmp_path/"error.sqlite3",sleeper_league_id="123456")
    with patch("fantasy_agent.config.Config.load",return_value=c), \
         patch("fantasy_agent.service.LeagueService.load",side_effect=DataUnavailable("Sleeper HTTP 503: unavailable")):
        app=boot(c)
        assert not app.exception
        assert "503" in app.error[0].value
        assert "snapshot" not in app.session_state


def test_trade_picker_only_offers_evaluated_players_and_search_completes(tmp_path):
    from fantasy_agent.trades import TradeEngine
    c=Config(cache_path=tmp_path/"trade-ui.sqlite3");s,d=trade_demo();s.league_type="redraft"
    with patch("fantasy_agent.config.Config.load",return_value=c), \
         patch("fantasy_agent.service.LeagueService.load",return_value=s), \
         patch("fantasy_agent.integrations.nflverse.NFLVerse.load",return_value=d):
        app=boot(c,s)
        app.sidebar.radio[0].set_value("Trade Finder").run(timeout=30)
        assert not app.exception
        ready=app.session_state['trade_eligibility']
        assert ready['eligible']==TradeEngine(s,d,c).candidate_pool(1)
        assert next(x for x in app.selectbox if x.label=='Trade structure').value=='2-for-1'
        next(b for b in app.button if b.label=='Find Best Trades').click().run(timeout=30)
        assert not app.exception and not app.error
        assert app.session_state['trade_run'].candidates_evaluated>0
