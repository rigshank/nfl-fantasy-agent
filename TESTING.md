# Verification record

Updated November 20, 2026, Windows, Python 3.13.3.

## Final local checks

- Project virtual environment: **140 tests passed in 31.53 seconds**.
- Compilation of app.py, fantasy_agent and tests passed; pip check reported no
  broken requirements. Use the README virtual-environment commands: the system
  Python does not have this application's dependencies.
- Real-league Streamlit AppTest opened all eight pages with zero exceptions and
  zero displayed errors. This includes actual waiver, breakout and lineup data;
  the trade calculations were also validated separately below. No Gemini final
  response was substituted during this live UI check.
- Running local preview: health endpoint returned HTTP 200 / ok.
- Every pinned runtime dependency has a compatible Python 3.13 Linux/x86_64 or
  pure-Python distribution, checked against official PyPI package metadata.
  GitHub Actions repeats installation, pip check, compilation and tests on Linux.

Focused coverage includes league scoring/bonuses and supported specialists,
explicit player identity, duplicate ownership, exact lineup assignment versus
brute force, flex/superflex, byes, injuries, IR/taxi, negative-point starters,
Eastern/DST kickoff locks, played bench restrictions, unknown kickoffs, legal
trade/waiver capacity and drops, dynasty evidence, opportunity-based breakouts,
FAAB missing/adjusted/exhausted balances, session invalidation, user exclusions,
AI exclusion sources, typed function calls, thought signatures/call IDs, source
URL validation, context limits, no-progress detection, partial failures,
provider retries/quota handling and free-only fallbacks. Broad strategy shares
one statistics load/evaluation across all five core calculations.

Test fixtures are confined to tests and never imported by production. Automated
provider mocks avoid repeated credit consumption; the separate checks below
used the existing credentials and actual network responses.

## Real-data final validation

Configured Sleeper league: **2026, week 11, 10-team dynasty**. All rosters,
scoring and current ownership loaded. Actual nflverse evidence through completed
week 10 was used; partial week 11 was not treated as a completed sample.

- **3,397** 1-for-1 / 2-for-1 trade packages evaluated, **10** ranked results.
  Warm discovery took **0.68 seconds**. Every returned trade passed ownership
  validation; all packages remain analyzed despite retaining only ranked results
  in memory. Initial uncached source ingestion takes longer.
- **236** available players had usable evaluations; **8** independent waiver
  alternatives returned. Every pickup was unowned and every proposed drop belonged
  to the selected team. The broader unowned catalog is not equated with usable
  current statistical evidence or immediate claim eligibility.
- **167** measured breakout signals across the evaluated league/free pool.
- **9** legal lineup slots, including **1** preserved kickoff lock. Full-game
  comparison totals are withheld where live locks prevent a fair comparison.
- Actual waiver_type was 1, despite a default budget field. FAAB was therefore
  not confirmed and no dollar bid was invented. Automated cases separately cover
  confirmed FAAB, minimum bids, remaining funds and uncertain adjustments.

## Gemini and Tavily

Existing key metadata verified gemini-4-hydrogen and gemini-3.8-flash. Auto prefers
Hydrogen with high reasoning and no artificial output/thinking budget. Official
free-tier eligibility was checked; API keys do not expose account billing state.
The app never enables billing or selects a paid-only fallback.

Tavily's real usage endpoint verified Researcher, 1,000 monthly plan credits,
997 remaining at the final account check. Earlier actual searches returned dated
linked sources. Search usage is cached and governed by the real free allowance.

Live unified strategy execution successfully completed get_league, team_needs,
waivers_and_breakouts, optimize_lineup and find_trades. **Broad final narrative
synthesis is not verified:** Hydrogen timed out after these tools; a separate
Flash attempt returned HTTP 504 before tool execution. Earlier attempts returned
503/high demand. Partial calculations remain visible; no fabricated answer or
paid fallback is substituted. Additional repeated large requests were stopped
because they could not resolve provider availability.

An earlier focused conversation completed four real tools and returned nine
sources. Review caught an unsupported inference that null injury metadata proved
full health. Prompts now explicitly prohibit this, distinguish dated status from
medical clearance, and distinguish historical quantiles from future bounds.
Source URLs must match retrieved evidence. Automated checks verify safeguards,
but revised live medical wording has not been revalidated because of upstream
503/timeouts. Do not treat that earlier response as proof of revised accuracy.

## Publication and hosted verification

Target: https://github.com/rigshank/nfl-fantasy-agent (initially empty).
Secrets, caches and the virtual environment are excluded from Git. Source and
staged-content scans check actual configured keys without printing them.
The prepared private .streamlit/secrets.toml is ignored; only the blank example
is publishable. **67 staged files passed the credential scan with zero findings.**
Application commit `6f73985` was pushed to main. The
[Linux CI run](https://github.com/rigshank/nfl-fantasy-agent/actions/runs/44744807075)
passed dependency installation, pip check, compilation and all automated tests.

Streamlit Community Cloud currently requires user sign-in and acceptance of its
terms. **No hosted app or hosted smoke check is claimed.** README contains exact
repository/main/app.py/Python 3.13 setup and secret instructions. After deployment,
verify the hosted health, league, eight pages and a sourced AI response.

Remaining limits: forecast calibration, late inactive/postponement feeds, rare
specialist scoring, complete future picks/keeper economics, and the external
Gemini/hosted checks above. No automated trade, waiver or lineup submission.
