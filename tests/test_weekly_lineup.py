from datetime import datetime,timedelta,timezone
from unittest.mock import Mock,patch
import pytest
from fantasy_agent.lineup import LineupOptimizer
from fantasy_agent.lineup_service import LineupService,kickoff
from fantasy_agent.models import Player,utcnow
from fantasy_agent.special_scoring import score_special,DEFENSE
from fantasy_agent.integrations.sleeper import DataUnavailable
from tests.fixture_stats import trade_demo


def scenario():
    s,d=trade_demo();s.league_status="in_season";s.league_type="redraft"
    for r in d.schedule:
        r["gameday"]=(utcnow()+timedelta(days=2)).date().isoformat();r["gametime"]="13:00"
    return s,d


def test_kicker_defense_idp_assignment_and_negative_legal_starter():
    players={p:Player(player_id=p,name=p,positions=[pos]) for p,pos in [("k","K"),("def","DEF"),("lb","LB"),("de","DE")]}
    result=LineupOptimizer(players,["K","DEF","DL","IDP_FLEX"],all_positions=True).solve(players,{"k":5,"def":-2,"lb":8,"de":7},fill=True)
    assert result.missing_slots==0 and result.total==18
    assert [p for _,p,_ in result.assignments]==["k","def","de","lb"]


def test_locks_preserve_saved_slot_and_exclude_locked_bench():
    players={p:Player(player_id=p,name=p,positions=["WR"]) for p in ["saved","better","bench"]}
    result=LineupOptimizer(players,["WR","FLEX"],all_positions=True).solve(["saved","better"],{"saved":2,"better":9,"bench":50},locked={0:"saved"},fill=True)
    assert [p for _,p,_ in result.assignments]==["saved","better"]
    with pytest.raises(ValueError,match="Duplicate"):
        LineupOptimizer(players,["WR","WR"]).solve(players,{},locked={0:"saved",1:"saved"})


def test_current_week_started_games_cannot_be_moved(config,store):
    s,d=scenario()
    for r in d.schedule:
        if int(r["week"])==s.week:r.update(gameday=(utcnow()-timedelta(days=1)).date().isoformat(),gametime="13:00")
    report=LineupService(config,store).analyze(s,d,1)
    assert all(r.locked and r.current_id==r.recommended_id for r in report.slots)
    assert report.expected_total is None and report.expected_gain is None
    assert all(r.estimate is None for r in report.slots)


def test_unknown_kickoffs_conservative_but_future_week_not_locked(config,store):
    s,d=scenario()
    for r in d.schedule:r.pop("gametime",None)
    current=LineupService(config,store).analyze(s,d,1)
    future=LineupService(config,store).analyze(s,d,1,s.week+1)
    assert all(r.locked for r in current.slots)
    assert not any(r.locked for r in future.slots)
    assert future.complete


def test_byes_injuries_ir_taxi_and_strategy_estimates(config,store):
    s,d=scenario();s.players['demo-4'].injury_status="Out"
    service=LineupService(config,store)
    for strategy in ("expected","upside","floor"):
        report=service.analyze(s,d,1,s.week+1,strategy)
        chosen={r.recommended_id for r in report.slots}
        assert not chosen&set(s.rosters[0].reserve+s.rosters[0].taxi+["demo-4"])
        assert report.expected_total==pytest.approx(sum(r.estimate for r in report.slots))
        assert report.expected_gain==pytest.approx(report.expected_total-report.current_total)
    d.schedule.append({"season":int(s.season),"week":11,"game_type":"REG","home_team":"OTHER-A","away_team":"OTHER-B","gameday":"2026-11-22","gametime":"13:00"})
    bye=service.analyze(s,d,1,11)
    assert not bye.complete and all(r.estimate is None for r in bye.slots)


def test_matchup_starters_authoritative_and_bad_ownership_rejected(config,store):
    s,d=scenario();s.matchups[0]["starters"]=s.rosters[0].starters.copy()
    s.matchups[0]["starters"][2]='demo-24'
    report=LineupService(config,store).analyze(s,d,1)
    assert report.slots[2].current_id=='demo-24'
    s.matchups[0]['starters'][2]='demo-8'
    with pytest.raises(DataUnavailable,match="ownership"):
        LineupService(config,store).analyze(s,d,1)


def test_kickoff_uses_eastern_and_dst():
    assert kickoff({"gameday":"2026-11-22","gametime":"13:00"}).astimezone(timezone.utc).hour==18
    assert kickoff({"gameday":"2026-09-20","gametime":"13:00"}).astimezone(timezone.utc).hour==17
    assert kickoff({"gameday":"2026-11-22","gametime":"TBD"}) is None


def test_special_scoring_exact_rules_ranges_and_missing_fields():
    assert score_special({"fg_made_50_59":1,"fg_made_60_":1,"pat_made":2,"pat_att":3},{"fgm_50p":5,"fgm_60p":1,"xpm":1,"xpmiss":-1},"K")==12
    row={v:0 for v in DEFENSE.values()};row.update(def_sacks=3,def_interceptions=1)
    opp={k:0 for k in ['passing_tds','rushing_tds','special_teams_tds','fg_made','pat_made','passing_2pt_conversions','rushing_2pt_conversions','def_2pt_made']}
    # All PATs count even when the preceding opposing defensive TD does not.
    opp.update(passing_tds=1,pat_made=2,fg_made=1,points_scored=17,def_tds=1,def_safeties=0)
    assert score_special(row,{"sack":1,"int":2,"pts_allow_7_13":4,"pts_allow_14_20":1},"DEF",opp)==9
    assert score_special({"def_tackles_solo":5,"def_tackle_assists":2,"def_sacks":1},{"idp_tkl_solo":1,"idp_tkl_ast":.5,"idp_sack":3,"sack":100},"IDP")==9
    assert score_special({"def_sacks":1},{"sack":2,"idp_sack":100},"DEF")==2
    with pytest.raises(ValueError,match="Missing"):
        score_special({}, {"xpm":1},"K")
    with pytest.raises(ValueError,match="Unsupported"):
        score_special({}, {"def_3_and_out":1},"DEF",opp)


def test_blocked_kicks_count_as_misses_and_pa_uses_actual_scoreboard():
    row={"fg_att":3,"fg_made":1,"fg_missed":1,"fg_blocked":1,"fg_missed_40_49":1,"fg_blocked_list":"47","pat_att":2,"pat_made":1}
    assert score_special(row,{"fgmiss":-1,"xpmiss":-1,"fgmiss_40_49":-1},"K")==-5
    # An offensive fumble recovery TD belongs in points allowed; subtract only
    # the opposing defensive TD, retaining its conversion points.
    assert score_special({}, {"pts_allow_7_13":4},"DEF",{"points_scored":19,"def_tds":1,"def_safeties":0})==4
