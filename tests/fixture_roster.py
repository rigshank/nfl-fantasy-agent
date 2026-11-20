"""Synthetic names and IDs make accidental real-world recommendations obvious."""
from fantasy_agent.models import Player, Roster, Snapshot


def demo_snapshot() -> Snapshot:
    players = {}
    positions = ["QB", "RB", "WR", "TE", "WR", "RB", "WR", "RB"]
    for i in range(24):
        pid = f"demo-{i}"
        players[pid] = Player(player_id=pid, name=f"Demo {positions[i % 8]} {i + 1:02}",
                              positions=[positions[i % 8]], team="DEMO")
    rosters = [Roster(roster_id=i + 1, owner_id=f"demo-user-{i}", manager=["North Stars", "Lake Effect"][i],
                      players=[f"demo-{j}" for j in range(i * 8, i * 8 + 8)],
                      starters=[f"demo-{j}" for j in range(i * 8, i * 8 + 5)],
                      reserve=[f"demo-{i * 8 + 7}"], taxi=[f"demo-{i * 8 + 6}"],
                      settings={"wins": 5 - i, "losses": 3 + i, "fpts": 900 - i * 20}) for i in range(2)]
    return Snapshot(league_id="123456", name="Unit test league", season="2026", week=9,
                    league_type="dynasty", roster_positions=["QB", "RB", "WR", "TE", "FLEX", "BN", "BN", "BN"],
                    scoring={"rec": 1, "rec_yd": .1, "rush_yd": .1, "pass_yd": .04, "pass_td": 4},
                    settings={"type": 2}, rosters=rosters, players=players,
                    matchups=[{"roster_id": 1, "matchup_id": 1, "points": 101.2},
                              {"roster_id": 2, "matchup_id": 1, "points": 98.4}],
                    warnings=[])

