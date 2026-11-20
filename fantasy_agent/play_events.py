"""Small per-player/week scoring and opportunity aggregates from nflverse PBP."""
from collections import defaultdict
from .scoring import EVENT_FIELDS, number

OPPORTUNITY_FIELDS = {"red_zone_targets", "red_zone_carries", "goal_line_carries"}
PBP_COLUMNS = {"game_id", "play_id", "season", "season_type", "week", "no_play", "play_type", "passer_player_id",
               "receiver_player_id", "rusher_player_id", "td_player_id", "pass_touchdown", "rush_touchdown",
               "interception", "return_touchdown", "yards_gained", "passing_yards", "receiving_yards",
               "rushing_yards", "yardline_100", "pass_attempt", "rush_attempt", "qb_kneel"}
REQUIRED_COLUMNS = {"game_id", "play_id", "season", "season_type", "week", "play_type", "passer_player_id",
                    "receiver_player_id", "rusher_player_id", "td_player_id", "pass_touchdown", "rush_touchdown",
                    "interception", "return_touchdown", "yards_gained", "yardline_100", "pass_attempt", "rush_attempt", "qb_kneel"}


def aggregate_plays(rows, season):
    aggregates, games, seen = defaultdict(lambda: {k: 0 for k in EVENT_FIELDS | OPPORTUNITY_FIELDS}), set(), set()
    for r in rows:
        if int(r.get("season") or 0) != season or r.get("season_type") != "REG":
            continue
        game = r["game_id"]
        games.add(game)
        key = (game, r["play_id"])
        if key in seen:
            raise ValueError("Duplicate play-by-play game/play ID; scoring supplementation refused.")
        seen.add(key)
        if r.get("no_play") == 1 or r.get("play_type") == "no_play":
            continue
        week = int(r["week"])
        passer, receiver, runner = r.get("passer_player_id"), r.get("receiver_player_id"), r.get("rusher_player_id")
        def add(pid, field):
            if pid:
                aggregates[(pid, week)][field] += 1
        yardline = number(r.get("yardline_100"))
        if yardline is not None and yardline <= 20:
            if r.get("pass_attempt") == 1:
                add(receiver, "red_zone_targets")
            if r.get("rush_attempt") == 1 and r.get("qb_kneel") != 1:
                add(runner, "red_zone_carries")
                if yardline <= 5:
                    add(runner, "goal_line_carries")
        if r.get("interception") == 1 and r.get("return_touchdown") == 1:
            add(passer, "passing_pick_sixes")
        # NFL offensive TD distance uses scrimmage gain; return TDs do not count.
        distance = number(r.get("yards_gained"))
        if distance is None:
            continue
        for threshold in (40, 50):
            if distance < threshold:
                continue
            if r.get("pass_touchdown") == 1:
                add(passer, f"passing_tds_{threshold}_plus")
                add(r.get("td_player_id") or receiver, f"receiving_tds_{threshold}_plus")
            if r.get("rush_touchdown") == 1:
                add(r.get("td_player_id") or runner, f"rushing_tds_{threshold}_plus")
    return [{"player_id": pid, "week": week, **values} for (pid, week), values in aggregates.items()], sorted(games)
