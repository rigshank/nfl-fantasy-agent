import pytest
from fantasy_agent.analysis import free_players, owned, roster_warnings, score_linear
from tests.fixture_roster import demo_snapshot
from fantasy_agent.models import Player, Roster
from fantasy_agent.normalization import league_type, player_from_raw, roster_from_raw


def test_linear_ppr_and_passing_scoring():
    assert score_linear({"rec": 6, "rec_yd": 80, "rec_td": 1}, {"rec": 1, "rec_yd": .1, "rec_td": 6}) == 20
    assert score_linear({"pass_yd": 250, "pass_td": 2, "pass_int": 1},
                        {"pass_yd": .04, "pass_td": 4, "pass_int": -2}) == 16


@pytest.mark.parametrize("stats,rules", [({}, {"rec": 1}), ({"rec": None}, {"rec": 1}),
                                         ({"rec": float("nan")}, {"rec": 1}),
                                         ({"bonus_rec_yd_100": 1}, {"bonus_rec_yd_100": 3})])
def test_scoring_refuses_missing_or_unsupported_data(stats, rules):
    with pytest.raises(ValueError):
        score_linear(stats, rules)


def test_identification_preserves_defense_ids_and_ignores_names():
    defense = player_from_raw("CHI", {"position": "DEF", "full_name": "Chicago Bears"})
    assert defense.player_id == "CHI" and defense.positions == ["DEF"]
    first = player_from_raw("1", {"full_name": "Same Name"})
    second = player_from_raw("2", {"full_name": "Same Name"})
    assert first.player_id != second.player_id


@pytest.mark.parametrize("code,expected", [(0, "redraft"), (1, "keeper"), (2, "dynasty"), (9, "unknown"), (None, "unknown")])
def test_format_detection(code, expected):
    assert league_type({"type": code}) == expected


def test_ownerless_roster_and_null_fields():
    r = roster_from_raw({"roster_id": 3, "players": None, "reserve": None}, {})
    assert r.players == [] and r.manager == "Team 3"


def test_available_players_exclude_all_ownership_including_ir_and_taxi():
    s = demo_snapshot()
    s.players["ir-only"] = Player(player_id="ir-only", name="IR player", positions=["RB"])
    s.players["taxi-only"] = Player(player_id="taxi-only", name="Taxi player", positions=["WR"])
    s.players["inactive"] = Player(player_id="inactive", name="Inactive", positions=["QB"], active=False)
    s.players["idp"] = Player(player_id="idp", name="IDP", positions=["LB"])
    s.rosters[0].reserve.append("ir-only")
    s.rosters[1].taxi.append("taxi-only")
    free = {p.player_id for p in free_players(s)}
    assert len(free) == 8
    assert not free & {"ir-only", "taxi-only", "inactive", "idp"}
    assert "ir-only" in owned(s.rosters[0])


def test_roster_validation_detects_duplicate_unowned_and_reserved_starter():
    roster = Roster(roster_id=1, manager="X", players=["1"], starters=["1", "1", "2"], reserve=["1"])
    warnings = roster_warnings(roster, ["QB"])
    assert len(warnings) == 4


def test_slot_validation_accepts_flex_and_rejects_wrong_position():
    roster = Roster(roster_id=1, manager="X", players=["rb"], starters=["rb"])
    players = {"rb": Player(player_id="rb", name="Runner", positions=["RB"])}
    assert roster_warnings(roster, ["SUPER_FLEX"], players) == []
    assert "ineligible" in roster_warnings(roster, ["QB"], players)[0]
