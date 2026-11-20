"""Exact maximum-weight slot assignment (including flex and unique players)."""
import numpy as np
from scipy.optimize import linear_sum_assignment
from .analysis import FLEX_POSITIONS
from .evaluation import OFFENSE
from .trade_models import Lineup


def offensive_slots(roster_positions):
    return [slot for slot in roster_positions if slot in OFFENSE or (FLEX_POSITIONS.get(slot, set()) & OFFENSE)]


class LineupOptimizer:
    def __init__(self, players, slots, all_positions=False):
        self.slots = [s for s in slots if s not in {"BN", "IR", "TAXI"}] if all_positions else offensive_slots(slots)
        self.player_ids = sorted(players)
        self.index = {pid: i for i, pid in enumerate(self.player_ids)}
        self.eligibility = np.array([[bool(set(players[p].positions).intersection(FLEX_POSITIONS.get(slot, {slot})))
                                      for p in self.player_ids] for slot in self.slots], dtype=bool)

    def solve(self, ids, scores, locked=None, fill=False):
        locked = locked or {}
        if any(i < 0 or i >= len(self.slots) for i in locked):
            raise ValueError("Invalid locked slot index.")
        locked_ids = [p for p in locked.values() if p]
        if len(locked_ids) != len(set(locked_ids)):
            raise ValueError("Duplicate locked player.")
        if locked:
            open_rows = [i for i in range(len(self.slots)) if i not in locked]
            remaining = LineupOptimizer.__new__(LineupOptimizer)
            remaining.slots = [self.slots[i] for i in open_rows]
            remaining.player_ids, remaining.index = self.player_ids, self.index
            remaining.eligibility = self.eligibility[open_rows]
            solved = remaining.solve(set(ids) - set(locked_ids), scores, fill=fill)
            assignments = dict(zip(open_rows, solved.assignments))
            for i, pid in locked.items():
                assignments[i] = (self.slots[i], pid, float(scores.get(pid, 0)))
            result = [assignments[i] for i in range(len(self.slots))]
            return Lineup(total=sum(p for _, _, p in result), assignments=result,
                          missing_slots=sum(p is None for _, p, _ in result))
        ids = sorted(set(ids) & self.index.keys())
        slots = self.slots
        if not slots:
            return Lineup(total=0, assignments=[])
        columns = np.array([self.index[p] for p in ids], dtype=int)
        points = np.array([scores.get(p, np.nan) for p in ids], dtype=float)
        eligible = self.eligibility[:, columns] & np.isfinite(points)[None, :]
        # Distinct dummy players permit a vacancy without assigning an ineligible
        # or unavailable player. Eligibility is precomputed once per league.
        matrix = np.zeros((len(slots), len(ids) + len(slots)))
        matrix[:, :len(ids)] = np.where(eligible, points[None, :], -1e9)
        # For a submitted lineup, fill every measurable legal slot even when its
        # estimate is negative. Trade comparisons keep their prior vacancy policy.
        objective = matrix.copy()
        if fill:
            bonus = (sum(abs(p) for p in points if np.isfinite(p)) + 1) * 2
            objective[:, :len(ids)] = np.where(eligible, matrix[:, :len(ids)] + bonus, -1e9)
        rows, assigned = linear_sum_assignment(objective, maximize=True)
        assignments = [(slots[i], ids[j] if j < len(ids) else None, round(float(matrix[i, j]), 4)) for i, j in zip(rows, assigned)]
        return Lineup(total=round(float(matrix[rows, assigned].sum()), 4), assignments=assignments,
                      missing_slots=sum(pid is None for _, pid, _ in assignments))


def optimize_lineup(ids, players, scores, slots):
    return LineupOptimizer(players, slots).solve(ids, scores)
