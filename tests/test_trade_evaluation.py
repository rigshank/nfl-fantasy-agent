from datetime import timedelta
import pytest
from fantasy_agent.evaluation import evaluate_players, id_index
from fantasy_agent.integrations.sleeper import DataUnavailable
from fantasy_agent.models import utcnow
from fantasy_agent.scoring import score_offense
from tests.fixture_stats import trade_demo


def test_id_mapping_rejects_ambiguity_and_never_joins_names():
    rows = [{"gsis_id": "g1", "sleeper_id": "1", "name": "Same Name"},
            {"gsis_id": "g1", "sleeper_id": "2", "name": "Same Name"},
            {"gsis_id": "g3", "sleeper_id": "3", "name": "Same Name"},
            {"gsis_id": "g4", "sleeper_id": "3", "name": "Same Name"},
            {"gsis_id": "g5", "sleeper_id": "5", "name": "Same Name"}]
    assert id_index(rows, "gsis_id") == {"g5": "5"}


def test_scoring_ppr_te_premium_and_bonuses_are_league_specific():
    row = {"receptions": 5, "receiving_yards": 110, "receiving_tds": 1}
    rules = {"rec": 1, "rec_yd": .1, "rec_td": 6, "bonus_rec_te": .5, "bonus_rec_yd_100": 3,
             "pts_allow_0": 10, "fgm": 3}
    assert score_offense(row, rules, "TE") == 27.5
    assert score_offense(row, rules, "WR") == 25
    assert score_offense({**row, "receiving_yards": 210}, {"bonus_rec_yd_100": 3, "bonus_rec_yd_200": 5}, "WR") == 5


def test_missing_scoring_metric_is_not_zero_filled():
    with pytest.raises(ValueError, match="Missing"):
        score_offense({}, {"rec": 1}, "WR")
    with pytest.raises(ValueError, match="Unsupported"):
        score_offense({}, {"unknown_offense_bonus": 2}, "QB")


def test_evaluations_use_usage_and_show_projection_limits():
    s, d = trade_demo()
    values, warnings = evaluate_players(s, d, 10, 17)
    assert len(values) == len(s.players)
    v = values["demo-24"]
    assert v.targets > 0 and v.snap_pct == .7
    assert v.floor <= v.upside
    assert v.projected_ppg != v.recent_ppg
    assert any("Red-zone" in x for x in v.limitations)
    assert len(v.weekly) == 8
    assert any("uncalibrated" in x or "quantiles" in x for x in warnings)


def test_opportunity_growth_and_td_regression_are_separate():
    s, d = trade_demo()
    for row in d.stats:
        if row["player_id"] in {"g-demo-24", "g-demo-25"}:
            week = row["week"]
            row["targets"] = 5 if week <= 4 else 12 if row["player_id"] == "g-demo-24" else 5
            row["receptions"] = row["targets"] * .7
            row["receiving_yards"] = row["targets"] * 8
            row["receiving_tds"] = 0 if row["player_id"] == "g-demo-24" else (2 if week > 4 else 0)
    values, _ = evaluate_players(s, d, 10, 17)
    rising, spiking = values["demo-24"], values["demo-25"]
    assert rising.opportunity_trend > .15
    assert spiking.opportunity_trend == 0
    assert spiking.projected_ppg < spiking.recent_ppg
    assert rising.projected_ppg > spiking.projected_ppg


def test_duplicate_weekly_history_is_rejected():
    s, d = trade_demo()
    d.stats.append(next(r.copy() for r in d.stats if r["player_id"] == "g-demo-24"))
    values, warnings = evaluate_players(s, d, 10, 17)
    assert "demo-24" not in values
    assert any("ambiguous" in x for x in warnings)


@pytest.mark.parametrize("designation", ["Out", "IR", "Doubtful", "SUS"])
def test_injured_players_have_no_invented_return_week(designation):
    s, d = trade_demo()
    s.players["demo-24"].injury_status = designation
    values, _ = evaluate_players(s, d, 10, 17)
    assert not values["demo-24"].available
    assert not any(values["demo-24"].weekly.values())


def test_inactive_player_is_excluded_even_with_good_history():
    s, d = trade_demo()
    s.players["demo-24"].active = False
    values, _ = evaluate_players(s, d, 10, 17)
    assert not values["demo-24"].available


def test_stale_stats_and_mismatched_season_fail_closed():
    s, d = trade_demo()
    d.stats = [r for r in d.stats if r["week"] <= 4]
    with pytest.raises(DataUnavailable, match="lag"):
        evaluate_players(s, d, 10, 17)
    s, d = trade_demo()
    d.season = 2025
    with pytest.raises(DataUnavailable, match="season"):
        evaluate_players(s, d, 10, 17)


def test_dated_dynasty_values_require_current_date_and_ids():
    s, d = trade_demo()
    d.dynasty[0]["scrape_date"] = (utcnow() - timedelta(days=90)).date().isoformat()
    values, _ = evaluate_players(s, d, 10, 17)
    assert values["demo-0"].dynasty_value is None
    assert values["demo-1"].dynasty_value is not None


def test_bye_week_is_zero_forecast_not_missing_stat():
    s, d = trade_demo()
    d.schedule = [r for r in d.schedule if r["week"] != 11]
    values, _ = evaluate_players(s, d, 10, 17)
    assert values["demo-24"].weekly[11] == 0
    assert values["demo-24"].opponents[11] == "BYE"


def test_partial_current_week_is_excluded_from_observations():
    s, d = trade_demo()
    future = next(r.copy() for r in d.stats if r["player_id"] == "g-demo-24")
    future.update(week=s.week, receiving_yards=1000)
    before, _ = evaluate_players(s, d, 10, 17)
    d.stats.append(future)
    after, _ = evaluate_players(s, d, 10, 17)
    assert before["demo-24"].projected_ppg == after["demo-24"].projected_ppg
