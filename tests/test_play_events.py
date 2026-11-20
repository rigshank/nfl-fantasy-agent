import io
import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fantasy_agent.integrations.nflverse import NFLVerse
from fantasy_agent.integrations.sleeper import DataUnavailable
from fantasy_agent.play_events import aggregate_plays
from fantasy_agent.scoring import score_offense


def play(**values):
    return {"game_id": "2026_10_BUF_KC", "play_id": 1, "season": 2026, "season_type": "REG", "week": 10,
            "play_type": "pass", "passer_player_id": "qb", "receiver_player_id": "wr", "rusher_player_id": None,
            "td_player_id": "wr", "pass_touchdown": 1, "rush_touchdown": 0, "interception": 0,
            "return_touchdown": 0, "yards_gained": 55, "yardline_100": 55,
            "pass_attempt": 1, "rush_attempt": 0, "qb_kneel": 0, **values}


def test_long_td_bonus_stacks_and_pick_six_is_charged_to_passer():
    events, games = aggregate_plays([play(), play(play_id=2, pass_touchdown=0, interception=1,
                                                return_touchdown=1, td_player_id="defender", yards_gained=0)], 2026)
    qb = next(r for r in events if r["player_id"] == "qb")
    wr = next(r for r in events if r["player_id"] == "wr")
    assert score_offense(qb, {"pass_td_40p": 2, "pass_td_50p": 3, "pass_int_td": -4}, "QB") == 1
    assert score_offense(wr, {"rec_td_40p": 2, "rec_td_50p": 3}, "WR") == 5
    assert games == ["2026_10_BUF_KC"]


def test_no_play_penalty_and_short_td_do_not_get_long_bonus():
    rows, _ = aggregate_plays([play(play_type="no_play"), play(play_id=2, yards_gained=39)], 2026)
    assert not rows


def test_red_zone_and_goal_line_opportunities_exclude_kneels():
    rows, _ = aggregate_plays([
        play(play_id=1, yardline_100=18, yards_gained=7, pass_touchdown=0),
        play(play_id=2, play_type="run", passer_player_id=None, receiver_player_id=None,
             rusher_player_id="rb", pass_attempt=0, rush_attempt=1, rush_touchdown=0,
             pass_touchdown=0, yardline_100=4, yards_gained=2),
        play(play_id=3, play_type="qb_kneel", rusher_player_id="qb", qb_kneel=1,
             pass_attempt=0, rush_attempt=1, pass_touchdown=0, yardline_100=3, yards_gained=-1)], 2026)
    wr = next(r for r in rows if r["player_id"] == "wr")
    rb = next(r for r in rows if r["player_id"] == "rb")
    assert wr["red_zone_targets"] == 1
    assert rb["red_zone_carries"] == 1 and rb["goal_line_carries"] == 1
    assert not any(r["player_id"] == "qb" for r in rows)


def test_duplicate_plays_are_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        aggregate_plays([play(), play()], 2026)


def test_parquet_adapter_caches_aggregates_and_removes_temporary_file(config, store):
    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_pylist([play()]), buffer)
    calls = []
    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, content=buffer.getvalue())
    adapter = NFLVerse(config, store, httpx.Client(transport=httpx.MockTransport(handler)))
    rows, games, source = adapter.play_events(2026)
    adapter.play_events(2026)
    assert len(calls) == 1 and rows and games
    assert not list(store.path.parent.glob("*.parquet"))


def test_schema_failure_also_closes_and_removes_parquet(config, store):
    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_pylist([{"wrong": 1}]), buffer)
    adapter = NFLVerse(config, store, httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=buffer.getvalue()))))
    with pytest.raises(DataUnavailable, match="schema"):
        adapter.play_events(2026)
    assert not list(store.path.parent.glob("*.parquet"))
