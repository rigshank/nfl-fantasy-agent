# Trade intelligence methodology

This engine is deterministic numerical analysis with optional AI interpretation.
It does not claim learned or calibrated projections, trade acceptance chances,
or simulated playoff qualification probabilities.

## Evidence and identity

Sources are public and free:

- [nflverse weekly statistics](https://github.com/nflverse/nflverse-data/releases/tag/stats_player)
- [nflverse play-by-play](https://github.com/nflverse/nflverse-data/releases/tag/pbp)
- [PFR snap counts through nflverse](https://github.com/nflverse/nflverse-data/releases/tag/snap_counts)
- [NFL schedule](https://github.com/nflverse/nfldata/blob/master/data/games.csv)
- [DynastyProcess IDs and dynasty values](https://github.com/dynastyprocess/data)
- [DynastyProcess market-value methodology](https://dynastyprocess.com/values/)
- [Sleeper scoring categories](https://support.sleeper.com/en/articles/3998131-what-scoring-options-are-available)
- [Sleeper stacking rules](https://support.sleeper.com/en/articles/3186339-what-stacks)

GSIS, PFR and FantasyPros IDs join to Sleeper IDs only through an unambiguous
one-to-one crosswalk. Ambiguous mappings, duplicate player/week records and
conflicting league ownership are rejected. No fuzzy names, cross-season fallback
or inferred player identities. Production code reads actual feeds only; test fixtures live under tests.

Core statistics and IDs must be freshly retrieved (maximum 48 hours), and the
latest completed statistics may lag the league by at most two weeks. League data
must be refreshed within its configured TTL and player catalog within 24 hours.
Statistical datasets cache six hours; crosswalk/market CSVs cache 24 hours.
PBP downloads stream to a temporary file with a 96 MB cap; selected columns are
processed in batches, and only compact aggregates persist. Optional snap/PBP
failure is disclosed; PBP failure blocks rules requiring PBP-derived bonuses.

Current partial NFL weeks are excluded from model fitting. A missing boxscore
game is zero-filled only when positive offensive snaps confirm appearance in a
game contained in the completed statistics release. Otherwise missing remains
missing. Per-game averages concern recorded/verified appearances, not invented
availability. Upcoming production uses the player's current team schedule;
production on previous teams stays observed history.

## Scoring and forecasts

Observed scores apply covered Sleeper offense rules to actual NFL fields.
Unsupported offense rules or absent scoring fields are errors, never stock-PPR
substitutes. K/DEF/IDP production is held constant outside the trade model.
Milestone ranges are exclusive. 40+/50+ TD bonuses stack. PBP game coverage is
required before a missing long-TD/pick-six event count can be interpreted as zero.

For each supported player:

1. Report season and last-four-game fantasy PPG, targets, carries, receptions,
   offensive snaps, snap percentage and opportunity change. Non-QB opportunity
   is carries + 1.5 × targets, an explicitly heuristic usage indicator. QB usage
   is attempts. Snap-derived zero-production games are included where verified.
2. Forecast passing attempts, carries and targets as 65% recent four-game mean +
   35% season mean. Estimate yards/catches/TDs from volume times efficiency.
   Efficiency blends personal and positional rates with personal weight
   `games / (games + 8)`; TD rates use `games / (games + 12)`. Other covered
   per-game fields use the same recent/season blend. This shrinks rare TD spikes
   instead of treating recent points as a future projection.
3. Expected yardage milestone points use a blend of empirical personal/positional
   threshold frequencies, rather than comparing an expected yardage to a cutoff.
4. Recent snap-share change adjusts the forecast by at most ±5%. Red-zone pass
   looks, red-zone carries and carries inside the five are PBP-derived contextual
   evidence when available. Kneels do not count as rushing opportunity. NFL team
   points/game is also context, not another correlated multiplier.
5. For each upcoming NFL week, shrink position-specific opponent points allowed
   toward league average with weight `opponent games / (opponent games + 8)`.
   Cap the final matchup factor at 0.85–1.15. Opponent allowed totals use all
   available NFL players, not just fantasy rosters. Validated full-season
   schedules distinguish byes from missing schedule data.
6. Report historical 20th/80th percentile game scores and population SD. These are
   observations, not prediction confidence intervals. "Improving"/"declining"
   usage uses ±15% opportunity changes. Regression labels compare forecast to
   observed PPG and do not assert a causal injury/coaching explanation.

Injured players, including out, doubtful, PUP and IR assets, can be included in
offers when trustworthy evaluations and required valuation evidence exist.
Trade eligibility is separate from forecast lineup availability: unavailable
injured players remain excluded from forecast lineups, without invented return
weeks or recovery probabilities. These packages have low confidence and explicit
recovery uncertainty. Questionable designations increase risk. Unverified roles
without an injury designation, suspended/inactive players without a documented
injury, and taxi players remain excluded. Healthy future lineups assume currently
eligible players remain available. Daily catalog injury data may lag.

## Lineups, needs and roster legality

SciPy's exact maximum-weight assignment handles every supported starter and flex
slot, unique player use and vacancies. The engine computes both teams' optimal
offensive lineups for each modeled future week, before and after the exchange.
This is an optimal hindsight-style assignment **under forecast inputs**, not a
claim that real managers can know outcomes or retroactively choose starters.

Coverage defaults to at least 80% of active offensive players, with no missing
data for saved offensive starters. Missing players retain ownership and capacity
but receive no invented value and are never automatically dropped. Team strength
and needs compare best positional surplus to other league teams; counts/needs
are signals, while exact lineup recomputation determines trade benefit.

Active capacity is starter + bench slots. IR assets are tradable; taxi assets
remain excluded. Sending an IR asset frees no active slot, and incoming assets
count against active capacity; no automatic IR placement is assumed. A receiving side that exceeds capacity must drop
evaluated, nonincoming bench players, protecting its neutral optimal starters.
Drop losses enter balance and depth; every week is recomputed and newly unfillable
offensive slots are rejected in automatic recommendations. Exact comparisons
can show such proposals with an explicit vacancy warning. Vacant bench spots remain vacant. No successful
waiver claims are assumed. The UI lists drops as conditions, not executed actions.

Replacement is the median projected PPG of the best five eligible, evaluated free
players per position. It informs scarcity and bench opportunity cost. If no such
players exist, baseline zero is disclosed as less reliable. Free players are not
automatically added or counted toward lineup gains.

## Search, balance and ranking

Automatic packages support one to three players per side. Filters constrain
opponent, incoming position and required outgoing players. All eligible players
participate; there are no player shortlists or comparison-count caps. Sorted
package values prune mathematically impossible balance matches before exact
both-team evaluation. Large selected structures take longer. Lineup-cache memory
is bounded for free hosting without restricting how many players are analyzed.

Redraft asset balance uses projected per-game points above free replacement.
For unavailable injured assets this is conditional when-available production,
not an injury-adjusted expected ROS valuation; recovery timing may materially
change fairness. Their potential return contributes no forecast lineup points.
Dynasty balance uses dated DynastyProcess 1QB/2QB community market values instead.
These dated prices are not asserted to reflect the latest injury report.
Those values already embody long-term community expectations and are separate
from fantasy points; age/data dates are displayed. Missing or older-than-30-day
values are not used. Both dynasty teams are limited to 10% market-value loss by
default, including necessary drops. No unsupported redraft fallback or pick values.

Balance score is `100 × (1 − maximum relative package imbalance)`, considering
all relinquished/drop value in both directions. Default imbalance ceiling is
40%; this is a heuristic screen, not an acceptance probability or price guarantee.
Default minimum ROS lineup gains are 1 point for you and 0 for the opponent.

Ranking formula (configurable weights):

```text
(my ROS gain + opponent_weight × opponent ROS gain) / forecast_weeks
+ consolidation_weight × freed_roster_spots × best_incoming_projected_PPG
− relative_package_imbalance
− risk_weight × average_package_risk × 5
− 0.05 × max(0, lost_bench_surplus)
```

Risk combines observed variability, small samples and catalog injury flags; it is
not a calibrated probability. Gains small relative to observed package variability
also force low confidence and an explicit uncertainty notice.
Confidence is low/medium, never high pending
out-of-time evaluation. Conditional playoff-week point changes use the league's
playoff start setting; qualification, brackets and championship odds are not
simulated. Results can legitimately contain no trade.

## AI interpretation and remaining limitations

Numerical trade discovery uses no Gemini/Tavily credits. Selected-trade analysis
revalidates league ownership/rules and batches relevant names into cached Tavily
research, respecting the real free-plan allowance. Gemini receives fixed calculations, observed metrics, dated evidence
and limitations; it may explain but must not invent valuations or acceptance
probabilities. Search/model failures leave deterministic results available.

Known limitations: future role/coaching changes need research, injuries lack
verified return timelines, target quality and offensive-line changes are not
modeled, and projections/market values are not calibrated to your league's trade
behavior. Very rare scoring/lateral plays and NFL stat corrections warrant
verification against Sleeper. Draft picks and keeper costs need dedicated
contracts. Phase 4 adds shared current-week lineup handling and covered specialist
scoring; trade/waiver comparisons continue to hold K/DEF/IDP fixed. The Gemini
agent invokes these same services. An explicitly requested trade can return
negative gains and market losses for review; discovery still rejects proposals
that fail the configured both-team benefit/balance criteria. The numerical pages
remain usable when Gemini or research is unavailable. See TESTING.md for actual
verification and deployment status.
