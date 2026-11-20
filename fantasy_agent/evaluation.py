"""Transparent statistical forecasts, not expert projections or trained values."""
from collections import defaultdict
from datetime import date
import statistics
import numpy as np

from .analysis import owned
from .models import Snapshot, utcnow
from .scoring import BONUSES, EVENT_FIELDS, STAT_FIELDS, number, score_offense, unsupported_rules
from .play_events import OPPORTUNITY_FIELDS
from .trade_models import Evaluation, TradeData
from .integrations.sleeper import DataUnavailable


OFFENSE = {"QB", "RB", "WR", "TE"}
UNAVAILABLE = {"OUT", "O", "IR", "PUP", "SUS", "SUSPENDED", "INACTIVE", "DOUBTFUL", "D"}


def team_code(team):
    return {"LAR": "LA", "WSH": "WAS", "JAC": "JAX", "OAK": "LV", "SD": "LAC"}.get(team, team)


def id_index(rows, field):
    """Only unambiguous one-to-one IDs. Never use names or silently pick a row."""
    forward, reverse = defaultdict(set), defaultdict(set)
    for row in rows:
        source, sleeper = str(row.get(field) or "").strip(), str(row.get("sleeper_id") or "").strip()
        if source and sleeper and source.upper() not in {"NA", "NAN"} and sleeper.upper() not in {"NA", "NAN"}:
            forward[source].add(sleeper)
            reverse[sleeper].add(source)
    return {source: next(iter(ids)) for source, ids in forward.items()
            if len(ids) == 1 and len(reverse[next(iter(ids))]) == 1}


def active_offense(snapshot, roster):
    return {pid for pid in owned(roster) - set(roster.reserve + roster.taxi)
            if pid in snapshot.players and OFFENSE.intersection(snapshot.players[pid].positions)}


def _mean(rows, field):
    vals = [number(r.get(field)) for r in rows]
    return statistics.mean(v for v in vals if v is not None) if any(v is not None for v in vals) else None


def _blend(rows, field):
    full, recent = _mean(rows, field), _mean(rows[-4:], field)
    return .35 * full + .65 * recent if full is not None and recent is not None else None


def _ratio(rows, numerator, denominator):
    pairs = [(number(r.get(numerator)), number(r.get(denominator))) for r in rows]
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    den = sum(b for _, b in pairs)
    return sum(a for a, _ in pairs) / den if den > 0 else 0.0


def _forecast(rows, population, rules, position):
    fields = set(STAT_FIELDS.values()) | {"attempts", "completions", "targets", "carries"}
    expected = {field: _blend(rows, field) for field in fields}
    weight = len(rows) / (len(rows) + 8)
    for volume, outcomes in [("attempts", ["passing_yards", "completions", "passing_tds", "passing_interceptions", "passing_pick_sixes", "passing_tds_40_plus", "passing_tds_50_plus", "passing_40"]),
                              ("carries", ["rushing_yards", "rushing_tds", "rushing_tds_40_plus", "rushing_tds_50_plus", "rushing_40"]),
                              ("targets", ["receptions", "receiving_yards", "receiving_tds", "receiving_tds_40_plus", "receiving_tds_50_plus", "receiving_40"])]:
        volume_value = _blend(rows, volume)
        if volume_value is None:
            continue
        expected[volume] = volume_value
        for field in outcomes:
            # TD efficiency is shrunk more strongly to avoid chasing touchdown spikes.
            w = len(rows) / (len(rows) + 12) if "_tds" in field else weight
            rate = w * _ratio(rows, field, volume) + (1 - w) * _ratio(population, field, volume)
            if _mean(rows, field) is not None:
                expected[field] = volume_value * rate
    base = score_offense(expected, {k: v for k, v in rules.items() if k not in BONUSES}, position)
    # Expected bonus points use observed threshold frequency, not thresholding a mean.
    for rule, (field, lo, hi) in BONUSES.items():
        if rules.get(rule):
            personal = [number(r.get(field)) for r in rows]
            prior = [number(r.get(field)) for r in population]
            personal, prior = [x for x in personal if x is not None], [x for x in prior if x is not None]
            if not personal or not prior:
                raise ValueError("Missing bonus-scoring evidence")
            probability = weight * np.mean([lo <= x < hi for x in personal]) + (1 - weight) * np.mean([lo <= x < hi for x in prior])
            base += rules[rule] * probability
    return max(0, base)


def evaluate_players(snapshot: Snapshot, data: TradeData, start_week: int, end_week: int, dynasty_max_age=30):
    if data.season != int(snapshot.season):
        raise DataUnavailable("Statistical season differs from the league season.")
    if unsupported_rules(snapshot.scoring):
        raise DataUnavailable("Trade engine cannot accurately score these rules: " + ", ".join(unsupported_rules(snapshot.scoring)))
    if not any(v and not k.startswith(("fg", "xp", "def", "idp")) for k, v in snapshot.scoring.items()):
        raise DataUnavailable("No supported offensive scoring configured.")
    for source in data.sources[:2]:
        if source.stale or (utcnow() - source.retrieved_at).total_seconds() > 172800:
            raise DataUnavailable("Core statistical evidence is stale; refresh data before ranking trades.")
    events = {(r["player_id"], int(r["week"])): r for r in data.scoring_events}
    raw = [r.copy() for r in data.stats if r.get("position") in OFFENSE and r.get("season_type", "REG") == "REG"
           and int(r.get("season", data.season)) == data.season and int(r["week"]) < snapshot.week]
    for row in raw:
        if row.get("game_id") in data.event_games:
            row.update({f: 0 for f in EVENT_FIELDS | OPPORTUNITY_FIELDS})
            row.update({k: v for k, v in events.get((row["player_id"], int(row["week"])), {}).items() if k not in {"player_id", "week"}})
    if not raw or max(int(r["week"]) for r in raw) < snapshot.week - 2:
        raise DataUnavailable("Statistics lag the league by more than two weeks, or no completed-week data exists.")
    last_week = max(int(r["week"]) for r in raw)
    warnings = list(data.warnings)
    warnings.append(f"Observed stats through week {last_week}. Current partial-week games are excluded.")
    gsis, pfr, fp = (id_index(data.ids, field) for field in ["gsis_id", "pfr_id", "fantasypros_id"])
    histories = defaultdict(list)
    for row in raw:
        pid = gsis.get(row["player_id"])
        if pid in snapshot.players:
            histories[pid].append(row)
    snaps = defaultdict(dict)
    for row in data.snaps:
        pid = pfr.get(row.get("pfr_player_id"))
        if pid in snapshot.players and row.get("game_type", "REG") == "REG" and int(row["week"]) <= last_week:
            week = int(row["week"])
            if week in snaps[pid]:
                snaps[pid][week] = None  # duplicate snap rows are ambiguous
            else:
                snaps[pid][week] = row
    # Include documented zero-offense games only when positive snaps confirm a
    # player appeared in a game present in the completed weekly stats release.
    stat_games = {r.get("game_id") for r in raw} - {None, ""}
    for pid, weeks in snaps.items():
        existing = {int(r["week"]) for r in histories[pid]}
        player = snapshot.players[pid]
        for week, row in weeks.items():
            if row and week not in existing and row.get("game_id") in stat_games and (number(row.get("offense_snaps")) or 0) > 0 and OFFENSE.intersection(player.positions):
                histories[pid].append({**{f: 0 for f in set(STAT_FIELDS.values()) | {"targets", "attempts", "completions"}},
                                       "week": week, "position": next(p for p in player.positions if p in OFFENSE),
                                       "team": row.get("team"), "opponent_team": row.get("opponent"),
                                       "zero_boxscore_from_snaps": True})
    populations = {pos: [r for rows in histories.values() for r in rows if r["position"] == pos] for pos in OFFENSE}
    # Defense allowed: sum all offensive players by position/opponent/game, not
    # just a user's roster; shrink small samples and cap adjustment to +/-15%.
    allowed_games = defaultdict(float)
    for row in raw:
        try:
            points = score_offense(row, snapshot.scoring, row["position"])
        except ValueError:
            continue
        if row.get("opponent_team"):
            allowed_games[(row["position"], team_code(row["opponent_team"]), int(row["week"]))] += points
    allowed, pos_allowed = defaultdict(list), defaultdict(list)
    for (pos, team, _), points in allowed_games.items():
        allowed[(pos, team)].append(points)
        pos_allowed[pos].append(points)
    schedule = {}
    scheduled_weeks = defaultdict(set)
    environment = defaultdict(list)
    for row in data.schedule:
        if row.get("game_type", "REG") != "REG" or int(row.get("season", data.season)) != data.season:
            continue
        week = int(row["week"])
        home, away = team_code(row["home_team"]), team_code(row["away_team"])
        schedule[(home, week)], schedule[(away, week)] = away, home
        scheduled_weeks[home].add(week)
        scheduled_weeks[away].add(week)
        for team, key in [(home, "home_score"), (away, "away_score")]:
            if week <= last_week and number(row.get(key)) is not None:
                environment[team].append(number(row[key]))
    if not schedule or not any(start_week <= week <= end_week for _, week in schedule):
        raise DataUnavailable("Upcoming schedule is unavailable; ROS trade comparisons cannot be calculated.")
    dynasty_values = {}
    superflex = snapshot.roster_positions.count("QB") >= 2 or "SUPER_FLEX" in snapshot.roster_positions
    for row in data.dynasty:
        pid = fp.get(row.get("fp_id"))
        try:
            age_days = (utcnow().date() - date.fromisoformat(row["scrape_date"][:10])).days
        except (KeyError, ValueError):
            continue
        value = number(row.get("value_2qb" if superflex else "value_1qb"))
        if pid and 0 <= age_days <= dynasty_max_age and value is not None and value > 0:
            if pid in dynasty_values:
                dynasty_values[pid] = None
            else:
                dynasty_values[pid] = (value, row["scrape_date"], number(row.get("age")))
    evaluations, rejected = {}, 0
    for pid, rows in histories.items():
        if not rows:
            continue
        weeks = [int(r["week"]) for r in rows]
        if len(weeks) != len(set(weeks)):
            rejected += 1
            continue
        rows.sort(key=lambda r: int(r["week"]))
        player = snapshot.players[pid]
        pos = rows[-1]["position"]
        if pos not in player.positions:
            rejected += 1
            continue
        try:
            points = [score_offense(r, snapshot.scoring, pos) for r in rows]
            projection = _forecast(rows, populations[pos], snapshot.scoring, pos)
        except ValueError:
            rejected += 1
            continue
        missing = ["Statistical forecast is uncalibrated; no verified recovery timeline."]
        if _mean(rows, "red_zone_targets") is None:
            missing.append("Red-zone and goal-line usage unavailable in compact feeds.")
        full_opp = None
        recent_opp = None
        if pos == "QB":
            full_opp, recent_opp = _mean(rows, "attempts"), _mean(rows[-4:], "attempts")
        else:
            a, b = _mean(rows, "carries"), _mean(rows, "targets")
            ar, br = _mean(rows[-4:], "carries"), _mean(rows[-4:], "targets")
            if None not in (a, b, ar, br):
                full_opp, recent_opp = a + 1.5 * b, ar + 1.5 * br
        trend = recent_opp / full_opp - 1 if full_opp and recent_opp is not None else None
        snap_rows = [r for w, r in sorted(snaps[pid].items()) if r is not None and w >= max(weeks) - 3]
        snap_values = [number(r.get("offense_pct")) for r in snap_rows]
        snap_values = [v if v <= 1 else v / 100 for v in snap_values if v is not None and 0 <= v <= 100]
        if not snap_values:
            missing.append("Recent snap percentage unavailable.")
        elif len(snap_values) > 1:
            # Small, disclosed snap signal; opportunity volume remains primary.
            projection *= max(.95, min(1.05, 1 + .25 * (snap_values[-1] - snap_values[0])))
        team = team_code(player.team)
        if not team or not any(t == team for t, _ in schedule):
            rejected += 1
            continue
        if len(scheduled_weeks[team]) != 17:
            rejected += 1
            continue
        available = player.active and player.known and str(player.injury_status or "").upper() not in UNAVAILABLE and str(player.status or "").upper() not in UNAVAILABLE
        risk = min(1, (statistics.pstdev(points) / max(1, abs(statistics.mean(points)))) * .25
                   + (0.2 if player.injury_status else 0) + (0.2 if len(rows) < 5 else 0))
        if max(weeks) < last_week - 1:
            available = False
            missing.append("No recent appearance; availability is unverified, excluded from projected lineups.")
        elif max(weeks) < last_week and (team, last_week) in schedule:
            available = False
            missing.append("No verified appearance in the team's latest completed game; current role/availability requires research. A bye is not counted as a missed appearance.")
        if not available:
            missing.append("Excluded from forecast lineups until availability/role is verified; no return week was assumed. This is not an inferred medical designation.")
        dv = dynasty_values.get(pid)
        label = "improving opportunities" if trend is not None and trend > .15 else "declining opportunities" if trend is not None and trend < -.15 else "stable/uncertain"
        if projection < statistics.mean(points) * .8 and (trend is None or trend <= .05):
            label += "; production may regress"
        elif projection > statistics.mean(points) * 1.2 and trend is not None and trend > .15:
            label += "; opportunity-led upside"
        weekly, opponents, factors = {}, {}, {}
        for week in range(start_week, end_week + 1):
            opponent = schedule.get((team, week))
            if opponent is None:
                weekly[week], opponents[week], factors[week] = 0.0, "BYE", 1.0
                continue
            values = allowed.get((pos, opponent), [])
            league_avg = statistics.mean(pos_allowed[pos]) if pos_allowed[pos] else 0
            adjustment = (statistics.mean(values) / league_avg - 1) * len(values) / (len(values) + 8) if values and league_avg > 0 else 0
            factor = max(.85, min(1.15, 1 + adjustment))
            weekly[week] = round(projection * factor, 3) if available else 0.0
            opponents[week], factors[week] = opponent, round(factor, 3)
        td_points = sum((number(r.get(f)) or 0) * snapshot.scoring.get(k, 0) for r in rows
                        for k, f in [("pass_td", "passing_tds"), ("rush_td", "rushing_tds"), ("rec_td", "receiving_tds")])
        observed = []
        for row, points_in_game in zip(rows, points):
            w = int(row["week"])
            snap = snaps[pid].get(w) or {}
            share = number(snap.get("offense_pct"))
            if share is not None and share > 1:
                share /= 100
            carries, targets, attempts = (number(row.get(f)) for f in ("carries", "targets", "attempts"))
            opportunity = attempts if pos == "QB" else carries + 1.5 * targets if carries is not None and targets is not None else None
            observed.append({"week": w, "fantasy_points": points_in_game, "targets": targets, "carries": carries,
                "receptions": number(row.get("receptions")), "opportunities": opportunity,
                "snap_share": share, "snaps": number(snap.get("offense_snaps")),
                "target_share": number(row.get("target_share")),
                "red_zone_opportunities": (number(row.get("red_zone_targets")) + number(row.get("red_zone_carries")))
                    if number(row.get("red_zone_targets")) is not None and number(row.get("red_zone_carries")) is not None else None})
        evaluations[pid] = Evaluation(player_id=pid, position=pos, games=len(rows), last_week=max(weeks),
            season_ppg=statistics.mean(points), recent_ppg=statistics.mean(points[-4:]), projected_ppg=projection,
            floor=float(np.quantile(points, .2)), upside=float(np.quantile(points, .8)), consistency_sd=statistics.pstdev(points),
            opportunities=full_opp, recent_opportunities=recent_opp, opportunity_trend=trend,
            snap_pct=statistics.mean(snap_values) if snap_values else None,
            recent_snaps=_mean(snap_rows, "offense_snaps"),
            snap_trend=snap_values[-1] - snap_values[0] if len(snap_values) > 1 else None,
            targets=_mean(rows[-4:], "targets"), carries=_mean(rows[-4:], "carries"), receptions=_mean(rows[-4:], "receptions"),
            red_zone_targets=_mean(rows[-4:], "red_zone_targets"), red_zone_carries=_mean(rows[-4:], "red_zone_carries"),
            goal_line_carries=_mean(rows[-4:], "goal_line_carries"),
            td_share=td_points / sum(points) if sum(points) > 0 else None,
            offensive_environment=statistics.mean(environment[team]) if environment[team] else None,
            trend=label, age=dv[2] if dv else None, dynasty_value=dv[0] if dv else None,
            dynasty_date=dv[1] if dv else None, available=available, risk=risk,
            weekly=weekly, opponents=opponents, schedule_factors=factors, limitations=missing, weekly_observed=observed)
    if rejected:
        warnings.append(f"{rejected} player histories excluded for ambiguous IDs/rows, missing scoring fields, position conflicts or missing team schedule.")
    missing_roster = set().union(*(active_offense(snapshot, r) for r in snapshot.rosters)) - evaluations.keys()
    if missing_roster:
        warnings.append(f"{len(missing_roster)} active offensive roster players lack trustworthy evaluations; no values were invented.")
    warnings.extend(["K/DEF/IDP held unchanged; all lineup point comparisons cover QB/RB/WR/TE slots only.",
                     "Red-zone/goal-line usage is reported only when verified PBP game coverage exists; recovery timelines remain unavailable.",
                     "Snap-share trend adjusts the volume forecast by at most ±5%; offensive team scoring is contextual evidence only.",
                     "Floor/upside are historical game quantiles, not calibrated prediction intervals.",
                     "Injury status is daily Sleeper catalog metadata. Verify current reports before offering a trade."])
    if snapshot.league_type == "dynasty":
        warnings.append("DynastyProcess 1QB/2QB market heuristics constrain long-term trade balance; no draft picks are proposed without a complete verified ownership inventory.")
    return evaluations, warnings
