# Waiver and breakout methodology

All candidates come from actual Sleeper ownership and real NFL evidence.
`free_players` excludes every team's players, IR and taxi. Positions and current
statistical availability are validated before recommending a move. The full
unowned directory stays visible even when some players lack usable projections.

## Pickup/drop comparison

For each evaluated free player, enumerate legal active-roster drops, or no drop
when a slot is open. Protected players, IR and taxi are never dropped. Use the
existing exact slot-assignment solver before and after the specific move for
every forecast week. Reject moves that create an unfillable slot or worsen total
modeled remaining-season lineup points. A zero-lineup-gain addition must improve
measured bench depth or trustworthy dynasty value to qualify. Keep the best
roster-specific drop per incoming player; rows are alternatives, not a sequence.

Rank by ROS lineup gain, then bench improvement and opportunity signal. Report
next-week gain, ROS gain, confidence and dynasty index change separately. Bench
surplus uses forecast points above the available-player position baseline; no
imaginary extra waiver claims enter a lineup calculation. Small edges relative
to observed variability are low confidence. A claim is not assumed to succeed.

Dynasty balanced mode does not discard known long-term market value. Win-now mode
can permit a disclosed market loss for actual modeled lineup improvement. If a
drop or incoming player lacks trustworthy dynasty evidence, do not invent a price
or recommend an automatic dynasty cut. Custom keeper costs remain a user-review
limitation; protect valuable keepers before running the analysis.

## Breakout opportunity evidence

Use the most recent three verified appearances versus the prior three. Shorter
histories retain a prior window where possible. Non-QB weighted opportunities
are carries + 1.5 times targets; QB opportunities are passing attempts. Report
actual target/carry means alongside that heuristic. Compare snap share, target
share and red-zone opportunities independently. Missing comparisons stay null.

The ranking signal is a weighted mean of normalized changes: opportunities 50%,
snap share 30%, target share 15%, red-zone work 5%, renormalizing over available
measurements. Scale by recent exposure versus the position's observed upper
quartile of opportunities, so tiny-volume changes do not dominate. Scores are
0–100 descriptive heuristics, never probabilities. No positive opportunity change
means no established-growth signal, regardless of touchdowns or fantasy points.

A player with only one observed role receives a low-confidence new-role label,
not a claim of proven growth. Comparable prior/recent appearances and snaps are
needed for medium confidence; no high-confidence predictive claim is made.
Current-role/coaching/injury explanations come from real sourced research.

## Sources, availability and reasoning

FAAB dollar guidance is enabled only for confirmed FAAB leagues with reported
starting budget and spend. Unknown or nonzero unverified budget adjustments
suppress a numeric balance. Suggested ranges obey the minimum bid and remaining
budget. Their rate is a subjective 2% plus 3% per estimated weekly lineup point,
capped at 25% of remaining funds; depth-only additions use 1% and low confidence
halves the rate. The lower end is half the upper end, subject to legal bounds.
These are spending preferences, not estimates of opponents' sealed bids.

Use nflverse weekly stats, PFR snaps and PBP, with explicit ID crosswalks and
league scoring. Keep completed-week fitting and future-week projections distinct.
A missed verified appearance in the team's latest completed game requires role
verification; absence in a bye does not. Injury return dates are not invented.

`Research and explain` refreshes league ownership, verifies that the pickup remains
unowned and the drop remains yours, and passes the fixed calculations, observed
usage, source dates, protected players and strategy to Gemini. Tavily researches
the relevant player and actual account credits govern usage. Research cannot
silently change numerical facts or assume a medical return date. General chat
can invoke this same waiver service as a Gemini tool, combine it with lineup and
trade results, and request targeted Tavily research in a subsequent tool step.
Waiver gains still start next full week; current-week lineups use their own locks.
