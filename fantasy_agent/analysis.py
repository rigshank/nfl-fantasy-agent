"""Deterministic facts only. Rankings require the later statistics pipeline."""
from collections import Counter
import math
from .models import Player, Roster, Snapshot


FLEX_POSITIONS = {"FLEX": {"RB", "WR", "TE"}, "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
                  "REC_FLEX": {"WR", "TE"}, "WRRB_FLEX": {"WR", "RB"},
                  "IDP_FLEX": {"DL", "LB", "DB", "DE", "DT", "CB", "S"},
                  "DL": {"DL", "DE", "DT"}, "DB": {"DB", "CB", "S"}}


def owned(roster: Roster) -> set[str]:
    return set(roster.players + roster.reserve + roster.taxi) - {"0"}


def free_players(snapshot: Snapshot) -> list[Player]:
    rostered = set().union(*(owned(r) for r in snapshot.rosters))
    eligible = set(snapshot.roster_positions) - {"BN", "IR", "TAXI"}
    for slot in list(eligible):
        eligible.update(FLEX_POSITIONS.get(slot, set()))
    return sorted((p for pid, p in snapshot.players.items()
                   if pid not in rostered and p.active and p.known and eligible.intersection(p.positions)),
                  key=lambda p: p.name.casefold())


def roster_warnings(roster: Roster, slots: list[str], players: dict[str, Player] | None = None) -> list[str]:
    warnings = []
    ids = owned(roster)
    starters = [p for p in roster.starters if p != "0"]
    if len(starters) != len(set(starters)):
        warnings.append("Duplicate starter IDs.")
    if not set(starters) <= ids:
        warnings.append("A starter is absent from the owned player list.")
    if len(roster.starters) != len([s for s in slots if s not in {"BN", "IR", "TAXI"}]):
        warnings.append("Starter slot count differs from league requirements.")
    if set(starters) & set(roster.reserve + roster.taxi):
        warnings.append("Starter also listed in IR/taxi.")
    if set(roster.reserve) & set(roster.taxi):
        warnings.append("Player listed in both IR and taxi.")
    if players:
        starter_slots = [s for s in slots if s not in {"BN", "IR", "TAXI"}]
        for slot, pid in zip(starter_slots, roster.starters):
            player = players.get(pid)
            if player and player.known and player.positions and not set(player.positions).intersection(FLEX_POSITIONS.get(slot, {slot})):
                warnings.append(f"{player.name} is ineligible for saved {slot} slot.")
    return warnings


def depth(snapshot: Snapshot, roster: Roster) -> dict[str, int]:
    # Multi-position players contribute to each position; this is not a strength score.
    return dict(Counter(pos for pid in owned(roster) for pos in snapshot.players[pid].positions))


def score_linear(stats: dict[str, float | None], rules: dict[str, float]) -> float:
    """Exact linear scoring only; refuse missing stats and nonlinear/unknown rules."""
    supported = {"pass_yd", "pass_td", "pass_int", "pass_2pt", "rush_yd", "rush_td",
                 "rush_2pt", "rec", "rec_yd", "rec_td", "rec_2pt", "fum_lost"}
    unsupported = {k for k, v in rules.items() if v and k not in supported}
    if unsupported:
        raise ValueError(f"Unsupported scoring rules: {sorted(unsupported)}")
    needed = [k for k, v in rules.items() if v]
    if any(stats.get(k) is None or not math.isfinite(stats[k]) for k in needed):
        raise ValueError("Missing or invalid scoring statistics")
    return round(sum(stats[k] * rules[k] for k in needed), 4)
