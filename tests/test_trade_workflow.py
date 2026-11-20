from unittest.mock import Mock, patch
import pytest
from tests.fixture_roster import demo_snapshot
from fantasy_agent.models import ResearchBundle
from tests.fixture_stats import trade_demo
from fantasy_agent.trade_models import TradeOptions
from fantasy_agent.trade_service import TradeService
from fantasy_agent.trades import TradeEngine
from fantasy_agent.integrations.research import ProviderUnavailable


def live_fixture(config):
    # Realistic public-feed shapes with synthetic data. Never a production offer.
    s, data = trade_demo()
    s.league_type = "redraft"
    engine = TradeEngine(s, data, config)
    run = engine.discover(1)
    assert run.trades
    return s, data, run


def test_real_workflow_refreshes_league_before_loading_stats(config, store):
    s, data, _ = live_fixture(config)
    league, data_client = Mock(), Mock()
    calls = []
    league.load.side_effect = lambda *a, **kw: (calls.append("league") or s)
    data_client.load.side_effect = lambda *a, **kw: (calls.append("stats") or data)
    _, run = TradeService(config, store, league, data_client).find(s, 1, TradeOptions())
    assert calls == ["league", "stats"] and run.trades
    assert league.load.call_args.kwargs["force"] is True


def test_selected_trade_batches_one_search_and_passes_calculated_evidence(config, store):
    s, _, run = live_fixture(config)
    trade = run.trades[0]
    league = Mock()
    league.load.return_value = s
    with patch("fantasy_agent.trade_service.Gemini") as gemini, patch("fantasy_agent.trade_service.Research") as research:
        gemini.return_value.answer.return_value = "Explanation"
        research.return_value.search.return_value = ResearchBundle(query="batched")
        answer, bundle = TradeService(config, store, league).explain(s, run, trade, "Why accept?", web=True)
        assert answer == "Explanation" and bundle
        assert research.return_value.search.call_count == 1
        query = research.return_value.search.call_args.args[0]
        assert all(s.players[p].name in query for p in trade.send + trade.receive)
        context = gemini.return_value.answer.call_args.args[0]
        assert context["calculated_trade"]["my_ros_gain"] == trade.my_ros_gain
        assert context["format"] == "redraft"


def test_search_failure_degrades_to_statistical_explanation(config, store):
    s, _, run = live_fixture(config)
    league = Mock()
    league.load.return_value = s
    with patch("fantasy_agent.trade_service.Gemini") as gemini, patch("fantasy_agent.trade_service.Research") as research:
        gemini.return_value.answer.return_value = "Statistical explanation"
        research.return_value.search.side_effect = ProviderUnavailable("free quota exhausted")
        answer, bundle = TradeService(config, store, league).explain(s, run, run.trades[0], "Why?", web=True)
        assert "statistical evidence only" in answer and bundle is None
        assert gemini.return_value.answer.call_count == 1


def test_changed_ownership_prevents_outdated_explanation(config, store):
    s, _, run = live_fixture(config)
    fresh = s.model_copy(deep=True)
    fresh.rosters[0].players.remove(run.trades[0].send[0])
    league = Mock()
    league.load.return_value = fresh
    with patch("fantasy_agent.trade_service.Gemini") as gemini:
        with pytest.raises(ValueError):
            TradeService(config, store, league).explain(s, run, run.trades[0], "Why?")
        gemini.assert_not_called()


def test_eligibility_picker_matches_engine_and_discloses_exclusions(config,store):
    s,data,_=live_fixture(config)
    league=Mock();league.load.return_value=s
    client=Mock();client.load.return_value=data
    fresh,ready=TradeService(config,store,league,client).eligibility(s,1)
    engine=TradeEngine(fresh,data,config)
    assert ready['eligible']==engine.candidate_pool(1)
    assert set(ready['eligible']).isdisjoint(ready['excluded'])
    assert all(ready['excluded'].values())
    assert set(ready['eligible'])|set(ready['excluded'])==set(s.rosters[0].players+s.rosters[0].reserve+s.rosters[0].taxi)
