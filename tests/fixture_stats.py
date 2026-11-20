"""Isolated synthetic statistical scenario. Never loaded for a real league."""
from .fixture_roster import demo_snapshot
from fantasy_agent.models import Player, utcnow
from fantasy_agent.scoring import STAT_FIELDS
from fantasy_agent.trade_models import SourceInfo, TradeData


def trade_demo(snapshot=None):
    s = (snapshot or demo_snapshot()).model_copy(deep=True)
    s.roster_positions += ["BN", "BN"]
    s.scoring.update({"rush_td": 6, "rec_td": 6, "pass_int": -2, "fum_lost": -2})
    for rid, pos, base in [(1, "WR", 24), (2, "RB", 26)]:
        r = next(r for r in s.rosters if r.roster_id == rid)
        for i in range(base, base + 2):
            pid = f"demo-{i}"
            s.players[pid] = Player(player_id=pid, name=f"Demo {pos} {i + 1:02}", positions=[pos], team="DEMO-A" if rid == 1 else "DEMO-B")
            r.players.append(pid)
    for pid, player in s.players.items():
        i = int(pid.split("-")[1])
        player.team = "DEMO-A" if i < 8 or i in {24, 25} else "DEMO-B"
    stats, ids, snaps, dynasty = [], [], [], []
    # WR surplus on A; RB surplus on B. All numbers are explicitly synthetic.
    for pid, player in s.players.items():
        i = int(pid.split("-")[1])
        pos = player.positions[0]
        ids.append({"gsis_id": "g-" + pid, "sleeper_id": pid, "pfr_id": "p-" + pid, "fantasypros_id": "f-" + pid})
        base = {f: 0 for f in set(STAT_FIELDS.values()) | {"targets", "attempts", "completions"}}
        roster_asset = i < 16 or i >= 24
        volume = (11 + i % 3) if (roster_asset and player.team == "DEMO-A" and pos == "WR") else (20 + i % 3) if (roster_asset and player.team == "DEMO-B" and pos == "RB") else 4 + i % 3
        for week in range(1, s.week):
            row = {**base, "player_id": "g-" + pid, "position": pos, "season": int(s.season), "season_type": "REG",
                   "week": week, "team": player.team, "opponent_team": "DEMO-B" if player.team == "DEMO-A" else "DEMO-A", "game_id": f"demo-game-{week}"}
            delta = (week % 3 - 1) * .8
            if pos == "QB":
                row.update(attempts=32 + delta, completions=22, passing_yards=240 + delta * 5, passing_tds=1, passing_interceptions=0)
            elif pos == "RB":
                row.update(carries=round(volume + delta), rushing_yards=round((volume + delta) * 4.4), targets=3, receptions=2, receiving_yards=15, rushing_tds=int((week + i) % 4 == 0))
            else:
                row.update(targets=round(volume + delta), receptions=round((volume + delta) * .7), receiving_yards=round((volume + delta) * 8), receiving_tds=int((week + i) % 4 == 0))
            stats.append(row)
            snaps.append({"pfr_player_id": "p-" + pid, "week": week, "offense_pct": .7, "offense_snaps": 45, "game_type": "REG", "game_id": f"demo-game-{week}"})
        # A synthetic community index is used only to exercise the dynasty path.
        value = volume * 100 + 500 if pos != "QB" else 2000
        dynasty.append({"fp_id": "f-" + pid, "value_1qb": value, "value_2qb": value,
                        "scrape_date": utcnow().date().isoformat(), "age": 25})
    schedule = [{"season": int(s.season), "week": w, "game_type": "REG", "home_team": "DEMO-A", "away_team": "DEMO-B",
                 "gameday": f"{s.season}-11-01", "home_score": 24 if w < s.week else "", "away_score": 21 if w < s.week else ""}
                for w in range(1, 19) if w != 11]
    return s, TradeData(season=int(s.season), stats=stats, ids=ids, snaps=snaps, schedule=schedule, dynasty=dynasty,
        sources=[SourceInfo(name="Unit test fixture", url="https://example.test/fixture", retrieved_at=utcnow())])
