from itertools import permutations
import random
import pytest
from fantasy_agent.lineup import optimize_lineup
from fantasy_agent.models import Player


def test_superflex_optimization_is_global_not_greedy():
    players = {"dual": Player(player_id="dual", name="Dual", positions=["QB", "WR"]),
               "qb": Player(player_id="qb", name="QB", positions=["QB"]),
               "wr": Player(player_id="wr", name="WR", positions=["WR"])}
    result = optimize_lineup(players, players, {"dual": 20, "qb": 19, "wr": 5}, ["QB", "WR"])
    assert result.total == 39
    assert [p for _, p, _ in result.assignments] == ["qb", "dual"]


def test_optimizer_handles_byes_unknowns_negative_scores_and_fixed_nonoffense_slots():
    players = {"rb": Player(player_id="rb", name="RB", positions=["RB"])}
    r = optimize_lineup(["rb", "unknown"], players, {"rb": -2}, ["QB", "FLEX", "K", "DEF", "BN"])
    assert r.total == 0 and r.missing_slots == 2
    assert len(r.assignments) == 2


@pytest.mark.parametrize("seed", range(8))
def test_assignment_matches_brute_force_small_rosters(seed):
    rng = random.Random(seed)
    pos = ["QB", "RB", "WR", "TE", "WR"]
    players = {str(i): Player(player_id=str(i), name=str(i), positions=[p]) for i, p in enumerate(pos)}
    scores = {pid: rng.uniform(1, 25) for pid in players}
    slots = ["QB", "WR", "FLEX"]
    actual = optimize_lineup(list(players) + ["0", "0"], players, scores, slots)
    best = max(sum(scores[p] for p in assignment) for assignment in permutations(players, 3)
               if players[assignment[0]].positions == ["QB"] and players[assignment[1]].positions == ["WR"]
               and players[assignment[2]].positions[0] in {"RB", "WR", "TE"})
    assert actual.total == pytest.approx(best, abs=.0001)
    ids = [p for _, p, _ in actual.assignments]
    assert len(ids) == len(set(ids))
