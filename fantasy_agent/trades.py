"""Both-team lineup comparison across all eligible players and selected packages."""
from collections import Counter
from bisect import bisect_left, bisect_right
from itertools import combinations
import hashlib
import statistics

from .analysis import FLEX_POSITIONS, owned
from .config import Config
from .evaluation import OFFENSE, active_offense, evaluate_players
from .integrations.sleeper import DataUnavailable
from .lineup import LineupOptimizer, offensive_slots
from .models import Snapshot, utcnow
from .trade_models import TeamReport, TradeData, TradeOptions, TradeProposal, TradeRun


def validate_ownership(snapshot, my_id, opponent_id, send, receive):
    teams = {r.roster_id: r for r in snapshot.rosters}
    if my_id == opponent_id or my_id not in teams or opponent_id not in teams:
        raise ValueError("Trade must involve two distinct existing teams.")
    if not send or not receive or len(set(send)) != len(send) or len(set(receive)) != len(receive) or set(send) & set(receive):
        raise ValueError("Trade packages must have distinct players on each side.")
    ownership = Counter(pid for r in snapshot.rosters for pid in owned(r))
    if any(ownership[p] != 1 for p in send + receive):
        raise ValueError("Trade player has missing or conflicting ownership.")
    for rid, package in [(my_id, send), (opponent_id, receive)]:
        roster = teams[rid]
        if not set(package) <= owned(roster) - set(roster.reserve + roster.taxi):
            raise ValueError("Trade includes a player owned by the wrong team or assigned to IR/taxi.")


def active_capacity(snapshot):
    return len([s for s in snapshot.roster_positions if s not in {"IR", "TAXI"}])


class TradeEngine:
    def __init__(self, snapshot: Snapshot, data: TradeData, config: Config, start_week=None, end_week=17, evaluations=None):
        self.snapshot, self.config = snapshot, config
        self.start = start_week if start_week is not None else snapshot.week + 1
        self.end = end_week
        if not snapshot.week < self.start <= self.end <= 18:
            raise DataUnavailable("Use a future full NFL week and an ending week through 18.")
        if (utcnow() - snapshot.refreshed_at).total_seconds() > config.league_cache_seconds:
            raise DataUnavailable("League snapshot is stale. Refresh before finding trades.")
        if (utcnow() - snapshot.catalog_at).total_seconds() > 86400:
            raise DataUnavailable("Player catalog is stale. Refresh its daily cache before finding trades.")
        if any("Archived/future" in w for w in snapshot.warnings):
            raise DataUnavailable("Archived/future leagues cannot produce current trade recommendations.")
        if snapshot.league_status and snapshot.league_status != "in_season":
            raise DataUnavailable("Trade forecasts require an in-season league.")
        if snapshot.settings.get("disable_trades"):
            raise DataUnavailable("Trades are disabled in this league.")
        deadline = int(snapshot.settings.get("trade_deadline") or 0)
        if deadline and snapshot.week > deadline:
            raise DataUnavailable("The league trade deadline has passed.")
        if snapshot.league_type not in {"redraft", "dynasty"}:
            raise DataUnavailable("Keeper/unknown leagues need verified keeper costs and rules before numerical trade rankings; no redraft values were substituted.")
        ids = [pid for r in snapshot.rosters for pid in owned(r)]
        if len(ids) != len(set(ids)):
            raise DataUnavailable("League has conflicting player ownership. Refresh Sleeper before finding trades.")
        self.values, self.warnings = evaluations if evaluations is not None else evaluate_players(snapshot, data, self.start, self.end, config.dynasty_max_age_days)
        self.sources = data.sources
        if not self.values:
            raise DataUnavailable("No players could be evaluated under these league rules.")
        self.dynasty = snapshot.league_type == "dynasty"
        if self.dynasty and not any(v.dynasty_value is not None for v in self.values.values()):
            raise DataUnavailable("Fresh, ID-mapped dynasty market values are unavailable. Numerical dynasty trades are disabled; no redraft fallback was used.")
        self.weeks = list(range(self.start, self.end + 1))
        self.week_scores = {week: {pid: v.weekly[week] for pid, v in self.values.items() if v.available} for week in self.weeks}
        self.neutral_scores = {pid: v.projected_ppg for pid, v in self.values.items() if v.available}
        rostered = set(ids)
        self.replacement = {}
        for pos in OFFENSE:
            free = sorted((v.projected_ppg for pid, v in self.values.items() if pid not in rostered and v.position == pos and v.available and v.games >= 3), reverse=True)
            self.replacement[pos] = statistics.median(free[:5]) if free else 0.0
            if not free:
                self.warnings.append(f"No evaluated free {pos} baseline; replacement set to zero, balance is less reliable.")
        self.rosters = {r.roster_id: r for r in snapshot.rosters}
        self.optimizer = LineupOptimizer(snapshot.players, snapshot.roster_positions)
        self.cache = {}
        self.reports = self._reports()

    def lineup(self, ids, week=None):
        key = (tuple(sorted(ids)), week)
        if key not in self.cache:
            # Bound memory for free Streamlit hosting during league-wide searches.
            if len(self.cache) >= 6000:
                self.cache.clear()
            self.cache[key] = self.optimizer.solve(ids, self.neutral_scores if week is None else self.week_scores[week])
        return self.cache[key]

    def asset(self, pid):
        value = self.values.get(pid)
        if not value:
            return None
        if self.dynasty:
            return value.dynasty_value
        return max(0, value.projected_ppg - self.replacement[value.position])

    def _reports(self):
        reports = []
        for roster in self.snapshot.rosters:
            ids = owned(roster) - set(roster.reserve + roster.taxi)
            offense = active_offense(self.snapshot, roster)
            coverage = len(offense & self.values.keys()) / len(offense) if offense else 0
            neutral = self.lineup(ids)
            starters = {pid for _, pid, _ in neutral.assignments if pid}
            known_starters = {pid for pid in roster.starters if pid in offense}
            missing_saved = known_starters - self.values.keys()
            warnings = []
            if missing_saved:
                warnings.append("Saved offensive starter(s) missing data: " + ", ".join(sorted(missing_saved)))
            if coverage < self.config.trade_min_team_coverage:
                warnings.append("Insufficient active offensive player coverage.")
            if len(ids) > active_capacity(self.snapshot):
                warnings.append("Active roster currently exceeds league capacity.")
            positions = {pos for pos in OFFENSE if any(pos in ({s} if s in OFFENSE else FLEX_POSITIONS.get(s, set())) for s in offensive_slots(self.snapshot.roster_positions))}
            surplus = {pos: max([self.values[p].projected_ppg for p in offense if p in self.values and self.values[p].position == pos and self.values[p].available] or [0]) - self.replacement[pos] for pos in positions}
            bench = Counter(self.values[p].position for p in offense - starters if p in self.values and self.values[p].available and self.values[p].projected_ppg > self.replacement[self.values[p].position])
            report = TeamReport(roster_id=roster.roster_id, manager=roster.manager, coverage=coverage,
                next_lineup=self.lineup(ids, self.start), ros_total=sum(self.lineup(ids, w).total for w in self.weeks),
                positional_surplus=surplus, bench_depth=dict(bench), strengths=[], needs=[],
                injured=sorted(p for p in owned(roster) if self.snapshot.players[p].injury_status or not self.snapshot.players[p].active),
                expendable=sorted((p for p in offense - starters if p in self.values and self.values[p].available and self.values[p].games >= 3), key=lambda p: -self.values[p].projected_ppg),
                eligible_partner=not warnings and coverage >= self.config.trade_min_team_coverage, warnings=warnings)
            reports.append(report)
        for report in reports:
            relative = {pos: value - statistics.mean(r.positional_surplus.get(pos, 0) for r in reports)
                        for pos, value in report.positional_surplus.items()}
            report.strengths = sorted(relative, key=relative.get, reverse=True)[:2]
            report.needs = sorted(relative, key=relative.get)[:2]
        return reports

    def _trim(self, ids, incoming):
        excess = len(ids) - active_capacity(self.snapshot)
        if excess <= 0:
            return set(ids), []
        protected = {pid for _, pid, _ in self.lineup(ids).assignments if pid}
        candidates = [p for p in ids - protected - set(incoming) if self.asset(p) is not None]
        if len(candidates) < excess:
            return None, []
        drops = sorted(candidates, key=lambda p: (self.asset(p), self.values[p].projected_ppg, p))[:excess]
        return set(ids) - set(drops), drops

    def _bench(self, ids):
        starters = {pid for _, pid, _ in self.lineup(ids).assignments if pid}
        return sum(max(0, self.values[p].projected_ppg - self.replacement[self.values[p].position])
                   for p in ids - starters if p in self.values and self.values[p].available)

    def compare(self, my_id, opponent_id, send, receive, options: TradeOptions, enforce_preferences=True, _generated=False):
        if not _generated:
            validate_ownership(self.snapshot, my_id, opponent_id, list(send), list(receive))
        for pid in list(send) + list(receive):
            if pid not in self.values or not self.values[pid].available or self.values[pid].games < 3 or self.asset(pid) is None:
                return None
        mine = owned(self.rosters[my_id]) - set(self.rosters[my_id].reserve + self.rosters[my_id].taxi)
        theirs = owned(self.rosters[opponent_id]) - set(self.rosters[opponent_id].reserve + self.rosters[opponent_id].taxi)
        my_after, my_drops = self._trim((mine - set(send)) | set(receive), receive)
        opp_after, opp_drops = self._trim((theirs - set(receive)) | set(send), send)
        if my_after is None or opp_after is None:
            return None
        if any(self.asset(p) is None for p in my_drops + opp_drops):
            return None
        sent, received = sum(self.asset(p) for p in send), sum(self.asset(p) for p in receive)
        # Compare all relinquished value, including mandatory drops, in both directions.
        my_lost = sent + sum(self.asset(p) for p in my_drops)
        opp_lost = received + sum(self.asset(p) for p in opp_drops)
        imbalance = max(abs(received - my_lost) / max(received, my_lost, .01),
                        abs(sent - opp_lost) / max(sent, opp_lost, .01))
        if enforce_preferences and imbalance > options.max_value_imbalance:
            return None
        if enforce_preferences and self.dynasty and (received < my_lost * (1 - options.max_dynasty_loss) or sent < opp_lost * (1 - options.max_dynasty_loss)):
            return None
        gains = []
        for before, after in [(mine, my_after), (theirs, opp_after)]:
            deltas = {w: self.lineup(after, w).total - self.lineup(before, w).total for w in self.weeks}
            # A proposal must not create a newly unfillable offensive slot.
            if any(self.lineup(after, w).missing_slots > self.lineup(before, w).missing_slots for w in self.weeks):
                return None
            gains.append(deltas)
        my_ros, opp_ros = sum(gains[0].values()), sum(gains[1].values())
        if enforce_preferences and (my_ros < options.min_my_ros_gain or opp_ros < options.min_opponent_ros_gain):
            return None
        my_bench, opp_bench = self._bench(my_after) - self._bench(mine), self._bench(opp_after) - self._bench(theirs)
        risk = statistics.mean(self.values[p].risk for p in list(send) + list(receive))
        consolidation = max(0, len(send) - len(receive))
        rank = (my_ros + options.opponent_weight * opp_ros) / len(self.weeks)
        rank += options.consolidation_weight * consolidation * max(self.values[p].projected_ppg for p in receive)
        rank -= imbalance + options.risk_weight * risk * 5 + .05 * max(0, -my_bench)
        playoff_start = int(self.snapshot.settings.get("playoff_week_start") or 0)
        playoff = [sum(v for w, v in delta.items() if w >= playoff_start) if playoff_start else None for delta in gains]
        low = any(self.values[p].games < 5 or self.values[p].risk > .4 for p in list(send) + list(receive))
        noise = statistics.mean(self.values[p].consistency_sd for p in list(send) + list(receive))
        marginal_gain = min(my_ros, opp_ros) / len(self.weeks) < max(1, noise * .25)
        low |= marginal_gain
        risks = ["Projection and balance scores are uncalibrated heuristics; acceptance is not predicted.",
                 "Future availability assumes currently eligible players remain available; no injury return dates are assumed.",
                 "No successful waiver claims are included in lineup gains."]
        if my_drops or opp_drops:
            risks.append("Conditional on completing the listed roster drops; their lost value is included.")
        if marginal_gain:
            risks.append("At least one team's projected benefit is small relative to historical variability; that incentive is uncertain.")
        if any(self.snapshot.players[p].injury_status for p in list(send) + list(receive)):
            risks.append("A package player has an injury designation; verify the current report.")
        if playoff_start:
            risks.append("Playoff points are conditional on qualifying, not a playoff probability.")
        reasons = [f"Your modeled offensive starters gain {my_ros:.1f} total points across weeks {self.start}–{self.end}.",
                   f"Opponent modeled offensive starters gain {opp_ros:.1f}; positional depth and all flex slots are recomputed.",
                   f"Package balance is {100 * (1 - imbalance):.0f}/100 using {'dated dynasty market values' if self.dynasty else 'projected points above free-agent replacement'}."]
        partner = next(r for r in self.reports if r.roster_id == opponent_id)
        reasons.append(f"Opponent receives {'/'.join(sorted({self.values[p].position for p in send}))}; their relative positional needs are {'/'.join(partner.needs)}. This is a roster incentive, not an acceptance prediction.")
        if consolidation:
            reasons.append("Consolidates roster spots into fewer incoming players; bench opportunity cost is included.")
        tid = hashlib.sha256(str((my_id, opponent_id, sorted(send), sorted(receive))).encode()).hexdigest()[:12]
        return TradeProposal(trade_id=tid, my_roster_id=my_id, opponent_id=opponent_id,
            send=sorted(send), receive=sorted(receive), my_drops=my_drops, opponent_drops=opp_drops,
            my_week_gain=gains[0][self.start], opponent_week_gain=gains[1][self.start],
            my_ros_gain=my_ros, opponent_ros_gain=opp_ros,
            my_playoff_gain=playoff[0], opponent_playoff_gain=playoff[1],
            my_bench_change=my_bench, opponent_bench_change=opp_bench,
            balance_score=100 * (1 - imbalance), value_imbalance=imbalance,
            value_basis="DynastyProcess long-term community market values" if self.dynasty else "Projected per-game points above available-player replacement",
            my_dynasty_gain=received - my_lost if self.dynasty else None,
            opponent_dynasty_gain=sent - opp_lost if self.dynasty else None,
            rank_score=rank, confidence="low" if low else "medium", my_after=self.lineup(my_after, self.start),
            opponent_after=self.lineup(opp_after, self.start), reasons=reasons, risks=risks)

    def discover(self, my_id, options=None):
        options = options or TradeOptions()
        if my_id not in self.rosters:
            raise ValueError("Selected roster is not in this league.")
        if not next(r for r in self.reports if r.roster_id == my_id).eligible_partner:
            raise DataUnavailable("Your team lacks sufficient trustworthy starter data or has an invalid active roster. Review the team-needs matrix.")
        if not set(options.must_send) <= owned(self.rosters[my_id]):
            raise ValueError("Selected outgoing player is not owned by your team.")
        def pool(rid):
            ids = [p for p in active_offense(self.snapshot, self.rosters[rid]) if p in self.values and self.values[p].available and self.values[p].games >= 3 and self.asset(p) is not None]
            ids.sort(key=lambda p: (-self.asset(p), p))
            return ids
        mine = pool(my_id)
        if not set(options.must_send) <= set(mine):
            raise DataUnavailable("Selected outgoing player has insufficient evidence, an unavailable status, or is on IR/taxi.")
        trades, evaluated = [], 0
        for report in self.reports:
            rid = report.roster_id
            if rid == my_id or not report.eligible_partner or (options.opponent_id is not None and rid != options.opponent_id):
                continue
            theirs = pool(rid)
            for n_send, n_receive in options.structures:
                if not 1 <= n_send <= 3 or not 1 <= n_receive <= 3:
                    raise ValueError("Automatic trade structures support one to three players per side.")
                outgoing = [p for p in combinations(mine, n_send) if set(options.must_send) <= set(p)]
                incoming = [p for p in combinations(theirs, n_receive) if options.receive_position is None or any(self.values[pid].position == options.receive_position for pid in p)]
                incoming_by_value = sorted((sum(self.asset(p) for p in package), package) for package in incoming)
                incoming_values = [v for v, _ in incoming_by_value]
                def pairs():
                    for send in outgoing:
                        a = sum(self.asset(p) for p in send)
                        lo = bisect_left(incoming_values, a * (1 - options.max_value_imbalance))
                        hi = bisect_right(incoming_values, a / (1 - options.max_value_imbalance))
                        for b, receive in incoming_by_value[lo:hi]:
                            diff = abs(a - b) / max(a, b, .01)
                            if diff <= options.max_value_imbalance:
                                yield send, receive
                for send, receive in pairs():
                    evaluated += 1
                    # Pools were constructed from verified unique ownership and
                    # active non-IR/taxi players in this immutable analysis turn.
                    trade = self.compare(my_id, rid, send, receive, options, _generated=True)
                    if trade:
                        trades.append(trade)
                        if len(trades)>options.max_results:
                            trades.sort(key=lambda t:(-t.rank_score,-t.my_ros_gain,t.trade_id))
                            del trades[options.max_results:]
        trades.sort(key=lambda t: (-t.rank_score, -t.my_ros_gain, t.trade_id))
        warnings = list(self.warnings)
        if not trades:
            warnings.append("No mutually improving, evidence-supported trade met the selected filters and balance constraints. No recommendation was invented.")
        return TradeRun(league_id=self.snapshot.league_id, my_roster_id=my_id,
            snapshot_at=self.snapshot.refreshed_at, start_week=self.start, end_week=self.end,
            evaluations=self.values, teams=self.reports, trades=trades[:options.max_results],
            replacement=self.replacement, sources=self.sources, warnings=warnings,
            candidates_evaluated=evaluated)
