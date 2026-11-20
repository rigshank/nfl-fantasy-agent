"""Real ownership-aware pickup/drop comparison and opportunity-led breakout signals."""
from collections import Counter
from datetime import datetime
import statistics
import numpy as np
from pydantic import BaseModel, Field

from .analysis import owned, free_players
from .evaluation import evaluate_players, active_offense, OFFENSE
from .integrations.sleeper import DataUnavailable
from .lineup import LineupOptimizer
from .models import utcnow
from .trade_models import Evaluation, Lineup, SourceInfo
from .trades import active_capacity
from .faab import bid_guidance,waiver_budget


class UsageChange(BaseModel):
    metric: str
    recent: float | None
    prior: float | None
    change: float | None


class BreakoutSignal(BaseModel):
    player_id: str
    score: float
    label: str
    confidence: str
    recent_games: int
    prior_games: int
    changes: list[UsageChange]
    reasons: list[str]
    limitations: list[str]


class Pickup(BaseModel):
    player_id: str
    drop_id: str | None
    kind: str
    next_week_gain: float
    ros_gain: float
    bench_change: float
    dynasty_change: float | None = None
    confidence: str
    breakout_score: float
    after: Lineup
    reasons: list[str]
    risks: list[str]
    faab: dict = Field(default_factory=dict)


class WaiverRun(BaseModel):
    league_id: str
    roster_id: int
    snapshot_at: datetime
    analyzed_at: datetime = Field(default_factory=utcnow)
    start_week: int
    end_week: int
    evaluations: dict[str, Evaluation]
    pickups: list[Pickup]
    breakouts: list[BreakoutSignal]
    before: Lineup
    sources: list[SourceInfo]
    warnings: list[str]
    free_players_checked: int
    free_players_evaluated: int
    protected: list[str]
    strategy: str
    waiver_budget: dict = Field(default_factory=dict)


def _mean(rows, metric):
    values = [r[metric] for r in rows if r.get(metric) is not None]
    return statistics.mean(values) if values else None


def breakout_signals(values):
    """Compare recent three verified appearances against the previous three.

    Fantasy points/TDs never contribute to the signal score. A volume-exposure
    factor prevents tiny snap/target changes on scarcely used players dominating.
    """
    baselines = {}
    for pos in OFFENSE:
        samples = [v.recent_opportunities for v in values.values() if v.position == pos and v.available and v.recent_opportunities is not None]
        baselines[pos] = float(np.quantile(samples, .75)) if samples else 1
    signals = []
    for pid, v in values.items():
        if not v.available or not v.weekly_observed:
            continue
        rows = sorted(v.weekly_observed, key=lambda r: r["week"])
        # Preserve a comparison window when there are fewer than six games.
        split = max(1, len(rows) - 3) if len(rows) > 1 else 0
        recent, prior = rows[split:], rows[max(0, split - 3):split]
        metrics = ["opportunities", "targets", "carries", "snap_share", "target_share", "red_zone_opportunities"]
        changes = []
        for metric in metrics:
            now, then = _mean(recent, metric), _mean(prior, metric)
            changes.append(UsageChange(metric=metric, recent=now, prior=then,
                change=now - then if now is not None and then is not None else None))
        by_name = {c.metric: c for c in changes}
        volume = by_name["opportunities"]
        if volume.recent is None or volume.recent <= 0:
            continue
        exposure = min(1, volume.recent / max(1, baselines[v.position]))
        reasons, limits, weighted = [], [], []
        if volume.prior is None:
            score = 50 * exposure
            label = "New observed role"
            reasons.append(f"{volume.recent:.1f} weighted opportunities/game in {len(recent)} verified appearance(s).")
            limits.append("No prior appearance window; growth is not established.")
        else:
            weights = {"opportunities": (.5, max(3, abs(volume.prior))),
                       "snap_share": (.3, .25), "target_share": (.15, .15), "red_zone_opportunities": (.05, 2)}
            for metric, (weight, scale) in weights.items():
                c = by_name[metric]
                if c.change is not None:
                    weighted.append((weight, max(-1, min(1, c.change / scale))))
                else:
                    limits.append(f"Comparable {metric.replace('_', ' ')} unavailable.")
            score = 100 * exposure * max(0, sum(w * x for w, x in weighted) / sum(w for w, _ in weighted)) if weighted else 0
            if volume.change is None or volume.change <= 0:
                score = 0  # scoring spikes without more opportunity do not qualify
            label = "Opportunity increasing"
            if volume.change and volume.change > 0:
                reasons.append(f"Weighted opportunities/game increased from {volume.prior:.1f} to {volume.recent:.1f}.")
            snap = by_name["snap_share"]
            if snap.change is not None and snap.change > 0:
                reasons.append(f"Offensive snap share rose {snap.change * 100:.1f} percentage points.")
            target = by_name["target_share"]
            if target.change is not None and target.change > 0:
                reasons.append(f"Target share rose {target.change * 100:.1f} percentage points.")
        if score <= 0:
            continue
        confidence = "medium" if len(recent) >= 2 and len(prior) >= 2 and by_name["snap_share"].change is not None else "low"
        limits.extend(["Heuristic opportunity score, not a breakout probability.", "Role/coaching explanations need current reporting."])
        signals.append(BreakoutSignal(player_id=pid, score=round(score, 2), label=label, confidence=confidence,
            recent_games=len(recent), prior_games=len(prior), changes=changes, reasons=reasons, limitations=limits))
    return sorted(signals, key=lambda s: (-s.score, s.player_id))


class WaiverEngine:
    def __init__(self, snapshot, data, config, roster_id, protected=None, strategy="balanced", start_week=None, end_week=17,evaluations=None):
        self.snapshot, self.config = snapshot, config
        self.roster = next((r for r in snapshot.rosters if r.roster_id == roster_id), None)
        if self.roster is None:
            raise ValueError("Selected team is not in the refreshed league.")
        self.start = start_week if start_week is not None else snapshot.week + 1
        self.end = end_week
        if not snapshot.week < self.start <= end_week <= 18:
            raise DataUnavailable("Select a future full NFL week through week 18 for waiver comparisons.")
        if (utcnow() - snapshot.refreshed_at).total_seconds() > config.league_cache_seconds:
            raise DataUnavailable("League ownership is stale; refresh before ranking pickups.")
        if (utcnow() - snapshot.catalog_at).total_seconds() > 86400:
            raise DataUnavailable("Player catalog is stale; refresh the daily catalog before ranking pickups.")
        ownership = Counter(p for r in snapshot.rosters for p in owned(r))
        if any(n != 1 for n in ownership.values()):
            raise DataUnavailable("Conflicting league ownership prevents reliable pickup/drop recommendations.")
        self.active = owned(self.roster) - set(self.roster.reserve + self.roster.taxi)
        if len(self.active) > active_capacity(snapshot):
            raise DataUnavailable("Your active roster exceeds league capacity. Resolve the excess slots in Sleeper first.")
        self.protected = set(protected or [])
        if not self.protected <= owned(self.roster):
            raise ValueError("Protected players must belong to your team.")
        self.strategy = strategy
        if strategy not in {"balanced", "win now"}:
            raise ValueError("Choose balanced or win now roster priority.")
        self.values, self.warnings = evaluations if evaluations is not None else evaluate_players(snapshot, data, self.start, self.end, config.dynasty_max_age_days)
        missing_starters = (set(self.roster.starters) & active_offense(snapshot, self.roster)) - self.values.keys()
        if missing_starters:
            raise DataUnavailable("Saved offensive starter data is missing: " + ", ".join(snapshot.players[p].name for p in sorted(missing_starters)) + ". Pickup gains cannot be established reliably.")
        self.sources = data.sources
        self.weeks = list(range(self.start, self.end + 1))
        self.scores = {w: {p: v.weekly[w] for p, v in self.values.items() if v.available} for w in self.weeks}
        self.neutral = {p: v.projected_ppg for p, v in self.values.items() if v.available}
        self.optimizer = LineupOptimizer(snapshot.players, snapshot.roster_positions)
        self.cache = {}
        self.before = {w: self.lineup(self.active, w) for w in self.weeks}
        self.signals = breakout_signals(self.values)
        self.free = free_players(snapshot)
        self.free_ids = {p.player_id for p in self.free}
        self.replacement = {}
        for pos in OFFENSE:
            scores = sorted((v.projected_ppg for p, v in self.values.items() if p in self.free_ids and v.available and v.position == pos), reverse=True)
            self.replacement[pos] = statistics.median(scores[:5]) if scores else 0

    def lineup(self, ids, week=None):
        key = (tuple(sorted(ids)), week)
        if key not in self.cache:
            if len(self.cache) >= 6000:
                self.cache.clear()
            self.cache[key] = self.optimizer.solve(ids, self.neutral if week is None else self.scores[week])
        return self.cache[key]

    def bench(self, ids):
        starters = {pid for _, pid, _ in self.lineup(ids).assignments if pid}
        return sum(max(0, self.values[p].projected_ppg - self.replacement[self.values[p].position]) for p in ids - starters
                   if p in self.values and self.values[p].available)

    def find(self):
        room = len(self.active) < active_capacity(self.snapshot)
        drops = [None] if room else sorted(p for p in self.active - self.protected if p in self.values and self.values[p].position in OFFENSE)
        signal_by_id = {s.player_id: s for s in self.signals}
        pickups, evaluated, dynasty_skipped = [], 0, 0
        before_bench = self.bench(self.active)
        for pid in sorted(self.free_ids):
            value = self.values.get(pid)
            if value is None or not value.available:
                continue
            evaluated += 1
            best = None
            for drop in drops:
                after_ids = (self.active - ({drop} if drop else set())) | {pid}
                dynasty_change = None
                if self.snapshot.league_type == "dynasty" and drop:
                    old_value = self.values[drop].dynasty_value
                    if value.dynasty_value is None or old_value is None:
                        dynasty_skipped += 1
                        continue
                    dynasty_change = value.dynasty_value - old_value
                    if self.strategy == "balanced" and dynasty_change < 0:
                        continue
                lineups = {w: self.lineup(after_ids, w) for w in self.weeks}
                if any(lineups[w].missing_slots > self.before[w].missing_slots for w in self.weeks):
                    continue
                deltas = {w: lineups[w].total - self.before[w].total for w in self.weeks}
                ros = sum(deltas.values())
                bench = self.bench(after_ids) - before_bench
                if ros < -.01 or (ros <= .01 and bench <= .01 and (dynasty_change is None or dynasty_change <= 0)):
                    continue
                if dynasty_change is not None and dynasty_change < 0 and ros <= .01:
                    continue
                sort_key = (round(ros, 4), round(bench, 4), dynasty_change or 0)
                if best is None or sort_key > best[0]:
                    best = (sort_key, drop, deltas, bench, dynasty_change, lineups)
            if best is None:
                continue
            _, drop, deltas, bench, dynasty_change, after = best
            ros = sum(deltas.values())
            uncertainty = value.consistency_sd + (self.values[drop].consistency_sd if drop else 0)
            confidence = "medium" if value.games >= 5 and ros / len(self.weeks) > max(1, uncertainty * .25) and not self.snapshot.players[pid].injury_status else "low"
            kind = "Lineup upgrade" if ros > .01 else "Depth / dynasty addition"
            reasons = [f"Modeled offensive lineup change: {deltas[self.start]:+.2f} points in week {self.start}; {ros:+.2f} across weeks {self.start}–{self.end}.",
                       "All starter/flex assignments and your remaining bench were recomputed after this exact pickup/drop."]
            if room:
                reasons.append("An active roster spot is open; no player needs to be dropped.")
            if dynasty_change is not None:
                reasons.append(f"Dated dynasty community value change: {dynasty_change:+.0f} index units, separate from fantasy points.")
            if pid in signal_by_id:
                reasons.extend(signal_by_id[pid].reasons)
            risks = ["Statistical projections are uncalibrated; small gains may be noise.",
                     "Unowned does not guarantee claim eligibility, FAAB availability or a successful waiver claim.",
                     "Daily injury metadata may lag; verify current reports before claiming."]
            if dynasty_change is not None and dynasty_change < 0:
                risks.append("Win-now strategy accepts a measured loss in long-term community value.")
            if self.snapshot.league_type == "keeper":
                risks.append("Keeper costs are not modeled. Confirm the proposed drop is not a valuable keeper.")
            pickup=Pickup(player_id=pid, drop_id=drop, kind=kind, next_week_gain=deltas[self.start], ros_gain=ros,
                bench_change=bench, dynasty_change=dynasty_change, confidence=confidence,
                breakout_score=signal_by_id[pid].score if pid in signal_by_id else 0, after=after[self.start], reasons=reasons, risks=risks)
            pickup.faab=bid_guidance(self.snapshot,self.roster.roster_id,pickup,len(self.weeks))
            pickups.append(pickup)
        pickups.sort(key=lambda p: (-p.ros_gain, -p.bench_change, -p.breakout_score, p.player_id))
        warnings = list(self.warnings)
        if dynasty_skipped:
            warnings.append("Pickup/drop pairs lacking trustworthy dynasty values were excluded; balanced mode also preserves measured long-term value.")
        if not pickups:
            warnings.append("No supported pickup/drop combination improved the modeled roster under these protections and strategy. Review the opportunity watch list; no upgrade was invented.")
        missing = len(self.free_ids) - evaluated
        warnings.append(f"Checked all {len(self.free_ids):,} eligible unowned catalog players; {evaluated} have usable current statistical evaluations. {missing:,} have missing/insufficient/availability data, not zero-valued projections.")
        return WaiverRun(league_id=self.snapshot.league_id, roster_id=self.roster.roster_id, snapshot_at=self.snapshot.refreshed_at,
            start_week=self.start, end_week=self.end, evaluations=self.values, pickups=pickups, breakouts=self.signals,
            before=self.before[self.start], sources=self.sources, warnings=warnings, free_players_checked=len(self.free_ids),
            free_players_evaluated=evaluated, protected=sorted(self.protected), strategy=self.strategy,
            waiver_budget=waiver_budget(self.snapshot,self.roster.roster_id))
