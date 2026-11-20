from datetime import timedelta
import pytest
from fantasy_agent.analysis import owned
from fantasy_agent.integrations.sleeper import DataUnavailable
from tests.fixture_stats import trade_demo
from fantasy_agent.trade_models import TradeOptions
from fantasy_agent.trades import TradeEngine, active_capacity, validate_ownership


@pytest.fixture
def scenario(config):
    s, d = trade_demo()
    s.league_type = "redraft"
    return TradeEngine(s, d, config)


def test_trade_candidates_benefit_both_lineups_and_have_correct_ownership(scenario):
    run = scenario.discover(1)
    assert run.trades
    assert all(t.my_ros_gain >= 1 and t.opponent_ros_gain >= 0 for t in run.trades)
    assert run.trades == sorted(run.trades, key=lambda t: (-t.rank_score, -t.my_ros_gain, t.trade_id))
    for t in run.trades:
        validate_ownership(scenario.snapshot, 1, t.opponent_id, t.send, t.receive)
        assert set(t.send) <= owned(scenario.rosters[1])
        assert set(t.receive) <= owned(scenario.rosters[t.opponent_id])


@pytest.mark.parametrize("send,receive", [(["demo-9"], ["demo-2"]), (["demo-2", "demo-2"], ["demo-9"]),
                                            (["demo-6"], ["demo-9"]), (["demo-7"], ["demo-9"]),
                                            (["nobody"], ["demo-9"])])
def test_illegal_ownership_duplicate_ir_and_taxi_rejected(scenario, send, receive):
    with pytest.raises(ValueError):
        validate_ownership(scenario.snapshot, 1, 2, send, receive)


def test_sum_of_bench_points_is_not_accepted_as_lineup_gain(scenario):
    # A same-position downgrade cannot pass merely because packages have players.
    assert scenario.compare(1, 2, ["demo-24"], ["demo-10"], TradeOptions(max_value_imbalance=.8)) is None


def test_explicit_trade_evaluation_reports_downgrade_without_recommending_it(scenario):
    proposal = scenario.compare(1, 2, ["demo-2"], ["demo-10"], TradeOptions(), enforce_preferences=False)
    assert proposal is not None
    assert proposal.my_ros_gain < 0
    assert proposal.opponent_ros_gain >= 0


def test_structures_position_and_must_send_filters(scenario):
    run = scenario.discover(1, TradeOptions(structures=[(2, 1)], receive_position="RB", must_send=["demo-24"], max_value_imbalance=.6))
    assert run.trades
    for t in run.trades:
        assert len(t.send) == 2 and len(t.receive) == 1
        assert "demo-24" in t.send
        assert scenario.values[t.receive[0]].position == "RB"


def test_roster_capacity_includes_required_drops(config):
    s, d = trade_demo()
    s.league_type = "redraft"
    s.roster_positions = s.roster_positions[:-2]  # Eight active spots, full rosters.
    engine = TradeEngine(s, d, config)
    run = engine.discover(1, TradeOptions(structures=[(2, 1)], max_value_imbalance=.6))
    assert run.trades
    for t in run.trades:
        mine = owned(engine.rosters[1]) - set(engine.rosters[1].reserve + engine.rosters[1].taxi)
        theirs = owned(engine.rosters[2]) - set(engine.rosters[2].reserve + engine.rosters[2].taxi)
        assert len(t.opponent_drops) == 1
        assert len((mine - set(t.send) - set(t.my_drops)) | set(t.receive)) <= active_capacity(s)
        assert len((theirs - set(t.receive) - set(t.opponent_drops)) | set(t.send)) <= active_capacity(s)
        assert not set(t.opponent_drops) & set(t.receive + t.send)


def test_missing_starting_player_prevents_unreliable_team_advice(config):
    s, d = trade_demo()
    s.league_type = "redraft"
    d.ids = [r for r in d.ids if r["sleeper_id"] != "demo-0"]
    engine = TradeEngine(s, d, config)
    with pytest.raises(DataUnavailable, match="starter data"):
        engine.discover(1)


def test_inactive_players_never_enter_generated_packages(config):
    s, d = trade_demo()
    s.league_type = "redraft"
    s.players["demo-24"].active = False
    run = TradeEngine(s, d, config).discover(1)
    assert all("demo-24" not in t.send + t.receive for t in run.trades)


def test_conflicting_league_ownership_blocks_engine(config):
    s, d = trade_demo()
    s.rosters[1].players.append("demo-24")
    with pytest.raises(DataUnavailable, match="ownership"):
        TradeEngine(s, d, config)


def test_dynasty_has_no_redraft_fallback(config):
    s, d = trade_demo()
    d.dynasty = []
    with pytest.raises(DataUnavailable, match="no redraft fallback"):
        TradeEngine(s, d, config)
    s, d = trade_demo()
    for row in d.dynasty:
        row["scrape_date"] = "2000-01-01"
    with pytest.raises(DataUnavailable, match="dynasty"):
        TradeEngine(s, d, config)


def test_dynasty_market_values_are_separate_from_ros_points(config):
    s, d = trade_demo()
    run = TradeEngine(s, d, config).discover(1)
    assert run.trades
    assert all(t.my_dynasty_gain is not None and "community" in t.value_basis for t in run.trades)


@pytest.mark.parametrize("change,error", [("deadline", "deadline"), ("disabled", "disabled"), ("keeper", "Keeper")])
def test_league_restrictions_fail_closed(config, change, error):
    s, d = trade_demo()
    if change == "deadline": s.settings["trade_deadline"] = 8
    if change == "disabled": s.settings["disable_trades"] = 1
    if change == "keeper": s.league_type = "keeper"
    with pytest.raises(DataUnavailable, match=error):
        TradeEngine(s, d, config)


def test_search_has_no_arbitrary_candidate_cap(config):
    s, d = trade_demo()
    s.league_type = "redraft"
    run = TradeEngine(s, d, config).discover(1)
    assert run.candidates_evaluated > 50
    assert not any("Bounded" in warning for warning in run.warnings)


def test_outgoing_pool_and_named_rejection_share_eligibility(scenario):
    engine=scenario
    pid=engine.candidate_pool(1)[0]
    engine.values[pid].available=False
    assert pid not in engine.candidate_pool(1)
    reason=engine.exclusion_reasons(1,pid)
    assert any('availability' in r for r in reason)
    with pytest.raises(DataUnavailable,match=engine.snapshot.players[pid].name):
        engine.discover(1,TradeOptions(structures=[(2,1)],must_send=[pid]))
    # An excluded optional player must not stop an unrestricted discovery.
    assert engine.discover(1,TradeOptions(structures=[(2,1)])).candidates_evaluated>0


def test_required_package_cannot_exceed_selected_structure(scenario):
    ids=scenario.candidate_pool(1)[:2]
    with pytest.raises(ValueError,match='Select fewer players'):
        scenario.discover(1,TradeOptions(structures=[(1,1)],must_send=ids))
