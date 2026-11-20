# Sideline — five-phase delivery plan

Updated November 20, 2026. Extend the existing application; real APIs and data
are the production path. Test fixtures stay under `tests/`.

## Phase 1 — Foundation (implemented)
Sleeper username/league connection, owner selection, all-team rosters, bench/IR/
taxi, scoring, standings, matchups, transactions, draft metadata and traded picks.
On-demand refresh retains the prior dated snapshot on failure. Gemini connectivity
uses existing environment variables or deployment secrets. No demo fallback.

## Phase 2 — Trade Intelligence (implemented)
Explicit player IDs, league scoring, nflverse weekly/snaps/PBP evidence,
statistical forecasts, replacement costs and dated dynasty market evidence.
Discovery evaluates every eligible package in the selected structures, exact
both-team offensive lineups, required drops, ownership and capacity. Explicit
comparisons also explain unfavorable trades. Ranked results are heuristics,
not acceptance probabilities. Future-pick valuation and keeper costs remain
disclosed limitations rather than fabricated prices.

## Phase 3 — Waiver Wire and Breakout Detection (implemented)
Actual free-player ownership, independent pickup/drop alternatives, protected
players, legal capacity, dynasty opportunity cost and next-week/ROS estimates.
Opportunity growth uses targets/carries, snaps, target share and red-zone work.
Independent Breakout Radar supports available, own and all-player scouting.
FAAB ranges require confirmed settings and reported remaining budget; uncertain
budget adjustments suppress dollar guidance. All spending ranges are subjective.

## Phase 4 — Lineup Optimization and AI Agent Integration (implemented)
Exact slot/flex/superflex assignment, covered K/DEF/IDP scoring, byes, conservative
kickoff locks, saved-lineup comparisons and expected/upside/floor objectives.
Explicit exclusions apply only to unlocked players; AI exclusions require
retrieved reporting. Missing health data is not medical clearance.

Twelve typed, read-only tools share dashboard services. One broad strategy tool
reuses league/statistical evidence across needs, trades, waivers and lineups.
Focused tools retrieve players, statistics and Tavily news. The Gemini loop keeps
thought signatures and call IDs, validates arguments and retrieved source URLs,
detects repeated work, and preserves partial results. No arbitrary step, player,
output-token or thinking budget is imposed.

## Phase 5 — Final Application (implementation complete; external checks pending)
Eight integrated pages, lean Settings, session invalidation on team/league/rule/
ownership changes, concurrent Sleeper reads, bounded result storage without
candidate truncation, shared evaluations, source validation, actual FAAB safety,
and real-league numerical/UI verification. See TESTING.md for measured results.

The selected GitHub repository is `rigshank/nfl-fantasy-agent`; it was empty at
the initial audit. Publication includes a secret scan, Python 3.13 Linux package
compatibility checks, CI, deployment examples and exact setup instructions.
Streamlit Cloud deployment and hosted verification require the user's account
sign-in and terms acceptance. Broad final Gemini synthesis is not verified after
Google timeouts/503/504 responses; every underlying calculation completed.
Neither external outcome is represented as complete.

Within this final phase, remaining validation is to complete the hosted smoke
check and retry sourced broad/focused narratives when Gemini is available.
Forecast calibration, late inactive/postponement feeds, rare specialist scoring,
complete pick inventory/value and keeper economics remain documented analytical
limits. No additional development phase is introduced.

## Architecture and operating rules
Streamlit -> Sleeper refresh -> shared normalized evidence/evaluation -> trade,
waiver, breakout and lineup services -> tables or Gemini tools -> sourced advice.
Tavily supplies dated reporting when it materially improves a decision. SQLite
is a disposable TTL cache and actual usage ledger, with no workers or external DB.

The configured key verified `gemini-4-hydrogen` and `gemini-3.8-flash` metadata.
Auto prefers Hydrogen; only documented accessible free-tier text models are
eligible. Availability fallback restarts a fresh transcript with completed evidence and no cross-model signatures; quota
exhaustion never causes model hopping. Actual context and rate limits apply.
High reasoning uses no custom output/thinking allowance. Tavily's actual free
Researcher plan/remaining credits are checked before uncached searches.

Keys never enter prompts, exports or Git. The app never enables billing or paid
grounding. Gemini API keys do not disclose project billing status: keep the
project unbilled; an AI Pro subscription is separate. Unknown IDs, stale sources,
unsupported rules and missing statistics remain explicit. Observations, estimates,
market evidence and AI opinion are distinguished. No roster action is submitted.

Official references: [Gemini pricing](https://aistudio.google.com/docs/pricing),
[Google Python SDK](https://github.com/googleapis/python-genai),
[Tavily usage](https://docs.tavily.com/documentation/api-reference/endpoint/usage),
[Sleeper](https://docs.sleeper.com/),
[nflverse](https://github.com/nflverse/nflverse-data),
[DynastyProcess](https://github.com/dynastyprocess/data),
[Cloud deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).
