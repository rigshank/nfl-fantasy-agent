from unittest.mock import Mock, patch
import pytest
from fantasy_agent.analysis import owned
from fantasy_agent.models import Player
from fantasy_agent.waivers import WaiverEngine, breakout_signals
from fantasy_agent.waiver_service import WaiverService
from tests.fixture_stats import trade_demo


@pytest.fixture
def scenario(config):
    s,d=trade_demo();s.league_type="redraft"
    s.roster_positions=s.roster_positions[:-2]
    return s,d,config


def test_real_pickup_drop_math_and_all_team_ownership(scenario):
    s,d,c=scenario
    run=WaiverEngine(s,d,c,1).find()
    assert run.pickups
    rostered=set().union(*(owned(r) for r in s.rosters))
    mine=owned(s.rosters[0])-set(s.rosters[0].reserve+s.rosters[0].taxi)
    for p in run.pickups:
        assert p.player_id not in rostered
        assert p.drop_id in mine
        assert p.ros_gain>=-.01
        assert p.drop_id not in s.rosters[0].reserve+s.rosters[0].taxi


def test_open_slot_has_no_invented_drop(config):
    s,d=trade_demo();s.league_type="redraft"
    run=WaiverEngine(s,d,config,1).find()
    assert run.pickups and all(p.drop_id is None for p in run.pickups)


def test_protected_players_are_never_dropped(scenario):
    s,d,c=scenario
    protected=owned(s.rosters[0])
    run=WaiverEngine(s,d,c,1,protected=protected).find()
    assert not run.pickups


def test_unowned_missing_statistics_never_become_zero_valued_pickup(scenario):
    s,d,c=scenario
    s.players["unknown-new"]=Player(player_id="unknown-new",name="Newly listed player",positions=["RB"],team="DEMO-A")
    run=WaiverEngine(s,d,c,1).find()
    assert "unknown-new" not in run.evaluations
    assert all(p.player_id!="unknown-new" for p in run.pickups)
    assert run.free_players_checked>run.free_players_evaluated


def test_balanced_dynasty_drops_preserve_measured_value(config):
    s,d=trade_demo();s.roster_positions=s.roster_positions[:-2]
    run=WaiverEngine(s,d,config,1).find()
    assert all(p.dynasty_change is not None and p.dynasty_change>=0 for p in run.pickups)


def test_missing_dynasty_values_do_not_get_fake_market_prices(config):
    s,d=trade_demo();s.roster_positions=s.roster_positions[:-2];d.dynasty=[]
    run=WaiverEngine(s,d,config,1).find()
    assert not run.pickups
    assert any("trustworthy dynasty" in x for x in run.warnings)


def usage_rows(rising=True):
    return [{"week":i+1,"opportunities":5 if i<3 or not rising else 13,
             "targets":3 if i<3 or not rising else 8,"carries":0,"snap_share":.3 if i<3 or not rising else .75,
             "target_share":.05 if i<3 or not rising else .2,"red_zone_opportunities":0 if i<3 or not rising else 2,
             "fantasy_points":10} for i in range(6)]


def test_breakout_prefers_opportunity_not_touchdown_spikes(scenario):
    s,d,c=scenario
    values=WaiverEngine(s,d,c,1).values
    rising=values["demo-24"].model_copy(deep=True);rising.weekly_observed=usage_rows(True)
    spiking=values["demo-25"].model_copy(deep=True);spiking.weekly_observed=usage_rows(False)
    for row in spiking.weekly_observed[-3:]:row["fantasy_points"]=50
    signals=breakout_signals({"rise":rising,"spike":spiking})
    assert [x.player_id for x in signals]==["rise"]
    assert signals[0].score>0 and signals[0].confidence=="medium"


def test_one_game_is_a_low_confidence_new_role_not_proven_growth(scenario):
    s,d,c=scenario
    value=WaiverEngine(s,d,c,1).values["demo-24"].model_copy(deep=True)
    value.weekly_observed=usage_rows(True)[-1:]
    signal=breakout_signals({"new":value})[0]
    assert signal.label=="New observed role" and signal.prior_games==0 and signal.confidence=="low"


def test_service_refreshes_actual_ownership_and_uses_real_adapter(scenario,store):
    s,d,c=scenario;league=Mock();league.load.return_value=s;data=Mock();data.load.return_value=d
    fresh,run=WaiverService(c,store,league,data).find(s,1)
    assert fresh is s and run.free_players_evaluated>0
    assert league.load.call_args.kwargs["force"] is True
    data.load.assert_called_once()


def test_research_refuses_pickup_that_an_opponent_just_added(scenario,store):
    s,d,c=scenario;run=WaiverEngine(s,d,c,1).find();pid=run.pickups[0].player_id
    fresh=s.model_copy(deep=True);fresh.rosters[1].players.append(pid)
    league=Mock();league.load.return_value=fresh
    with patch("fantasy_agent.waiver_service.Gemini") as gemini:
        with pytest.raises(ValueError,match="ownership"):
            WaiverService(c,store,league).explain(s,run,pid)
        gemini.assert_not_called()


def test_missing_latest_appearance_requires_role_verification(scenario):
    s,d,c=scenario;pid="demo-24"
    d.stats=[r for r in d.stats if not(r["player_id"]=="g-"+pid and r["week"]==8)]
    d.snaps=[r for r in d.snaps if not(r["pfr_player_id"]=="p-"+pid and r["week"]==8)]
    engine=WaiverEngine(s,d,c,1)
    assert not engine.values[pid].available
    assert any("latest completed game" in x for x in engine.values[pid].limitations)
