# Fantasy Analyst

A personal fantasy football analyst using your real Sleeper league, league-specific
Python calculations, public nflverse statistics, Gemini reasoning and Tavily news.
No local AI inference or paid infrastructure is required.

## Run locally

Use Python 3.13. From the repository directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open [localhost:8501](http://localhost:8501). On macOS/Linux replace the Python
executable above with `.venv/bin/python`. Existing keys in `.env`, environment
variables or Streamlit secrets are used directly; never paste keys into chat.
A configured league loads automatically. Otherwise enter a Sleeper username or
league ID, select a league and choose your team. No Sleeper password is needed.

## Daily workflow

- **Overview:** roster facts, standings and a button to request a complete AI plan.
- **My League:** every roster/bench/IR/taxi, scoring, matchups, weekly transactions,
  draft metadata and traded-pick records.
- **Trade Finder:** all eligible players, legal packages, required drops, exact
  both-team offensive lineup gains, replacement costs and dated dynasty values.
  Balance/confidence are heuristics, never acceptance probabilities. Larger trade
  structures take longer; no player shortlist or candidate-count cap is applied.
- **Waiver Wire:** specific pickup/drop alternatives, protections, roster fit,
  opportunity signals and optional current research. FAAB spending ranges require
  confirmed FAAB settings and reported spend, stay within remaining budget, and
  are subjective suggestions rather than forecasts of sealed bids. Unowned does
  not guarantee immediate claim eligibility. Each row is an independent alternative.
- **Breakout Radar:** independent available/my-team/league scouting using measured
  opportunities, snaps, targets/carries, shares and red-zone trends. Point or TD
  spikes do not drive the score. Inspect the underlying weekly observations.
- **Lineup Optimizer:** exact legal slot/flex/superflex assignment with current
  kickoff locks, byes, saved-starter comparisons and expected/upside/floor modes.
  You can exclude late inactives or other players from unlocked slots. An AI-added
  exclusion requires a retrieved source. Already-started starters stay locked.
- **AI Analyst:** natural questions, follow-ups, tool progress, evidence tables,
  dates and linked sources. Ask “Analyze my entire league and tell me the best
  moves I can make to improve my team.” The bundled strategy tool reuses one
  statistical evaluation across needs, trades, waivers and lineups, then Gemini
  can research relevant news. Focused questions use individual tools.
- **Settings:** session model/reasoning preferences, metadata access checks, actual
  Tavily allowance, recorded generation/search usage, refresh and snapshot export.

League data refreshes before analysis and is rechecked before AI advice is shown.
Ownership/rule/status changes invalidate calculations. Player catalog caching is
24 hours per Sleeper guidance; statistics normally cache six hours and kickoff
schedules five minutes. Source dates, observed coverage and cached timestamps are
shown separately. API failure never triggers fabricated replacement data. Numerical
pages remain usable when Gemini or Tavily is unavailable.

## Configuration and free operation

See `.env.example` and `.streamlit/secrets.toml.example`. Main variables:

| Variable | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Existing Google AI Studio API key |
| `TAVILY_API_KEY` | Existing free Researcher key |
| `GEMINI_MODEL` | `auto`, or a verified eligible model ID |
| `GEMINI_THINKING_LEVEL` | `high` by default |
| `SLEEPER_USERNAME` | Your Sleeper username/user ID |
| `SLEEPER_LEAGUE_ID` | League to load automatically |
| `CACHE_PATH` | Relative disposable cache path; `.cache/fantasy.sqlite3` |
| `LEAGUE_CACHE_SECONDS` / `STATS_CACHE_SECONDS` | Data freshness settings |

`auto` prefers `gemini-4-hydrogen`, then tries `gemini-3.8-flash`,
`gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`,
`gemini-3-flash-preview` and `gemini-2.5-flash-lite`. These exact IDs have documented
free standard text input/output pricing and are checked against the configured key.
Moving aliases, media-only models and deprecated automatic reroutes are excluded.
Model metadata access is checked against the key. Repeated model-unavailable
responses, timeouts and connection failures can select another eligible model;
quota exhaustion and authentication errors never cause model hopping. Overloaded
models cool down for two minutes across requests, then become eligible again.
After a tool-stage failure, the replacement starts a fresh transcript containing
completed evidence. Signatures and function-call IDs never cross models. There are
no custom token/reasoning/output budgets or arbitrary research caps. Actual context
limits, upstream minute-reset delays and free quotas are respected.

Keep the Gemini API project unbilled and Tavily on Researcher with pay-as-you-go
disabled. Google AI Pro is separate from API access. An API key does not expose
Google project billing settings; model free-tier eligibility alone cannot prove
an account is unbilled. The app never enables billing, selects paid-only fallback
models, enables paid grounding or changes provider plans. Tavily's actual free
allowance is checked before uncached searches. Duplicate queries are cached.

## Evidence and limitations

Explicit GSIS/PFR/FantasyPros-to-Sleeper mappings avoid guessed player identity.
Observed offensive points apply the league's scoring, including covered bonuses
and PBP supplements. Missing fields and unsupported scoring remain explicit.

Forecasts are transparent statistical estimates, not licensed expert projections
or calibrated win probabilities. Historical floor/upside quantiles are observations,
not future bounds. Active/null injury metadata is not medical clearance; current
health needs dated participation/game-status reporting. Late postponements and
inactive lists still require checking Sleeper before submitting a lineup.

Trade/waiver gains start next full week and hold K/DEF/IDP fixed. The lineup page
also covers supported specialist rules using nflverse player/team statistics;
rare custom categories and specialist matchup/role forecasting remain limited.
No full-game total is claimed when locks or missing evidence prevent comparison.
Keeper costs, complete future-pick inventory/value, sealed bids and playoff win
probabilities are not modeled. Draft/pick metadata is informational. No roster,
claim, trade or lineup is automatically submitted.

## Architecture and validation

`integrations/` handles Sleeper, nflverse, Gemini and Tavily. Normalization/scoring
and `evaluation.py` produce typed evidence. Trade, waiver, breakout and lineup
services power both Streamlit pages and the whitelisted agent dispatcher in
`agent.py`. SQLite is only a local TTL cache and usage ledger. There are no workers,
external databases or elaborate agent frameworks. Test fixtures live under tests.

The manual Gemini loop preserves thought signatures and function IDs, validates
arguments, detects repeated work, retains partial failures, and rejects source URLs
not retrieved by a tool. Sources remain evidence, never instructions.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app.py fantasy_agent
.\.venv\Scripts\python.exe -m pip check
```

See [TESTING.md](TESTING.md) for actual results and provider limitations,
[PLAN.md](PLAN.md) for the five-phase roadmap and remaining external checks, and the methodology
in [trade](docs/TRADE_MODEL.md) and [waiver](docs/WAIVER_MODEL.md) notes.

## Deploy on free Streamlit Community Cloud

Repository: [rigshank/nfl-fantasy-agent](https://github.com/rigshank/nfl-fantasy-agent).

1. Sign in at [Streamlit Community Cloud](https://share.streamlit.io/) and accept
   its deployment terms yourself if prompted.
2. Create app → “Yup, I have an app.” Enter repository
   `rigshank/nfl-fantasy-agent`, branch `main`, entry point `app.py`.
3. In **Advanced settings**, select **Python 3.13**. Every pinned runtime package
   was checked for a compatible Linux/Python 3.13 distribution on official PyPI.
4. In **Secrets**, populate the names from `.streamlit/secrets.toml.example` using
   the existing local credentials and Sleeper configuration. Do not upload `.env`
   or commit a populated secrets file. `requirements.txt` supplies runtime packages.
   If the ignored local `.streamlit/secrets.toml` is present, it is the prepared
   private TOML you can copy directly into Cloud's Secrets field.
5. Deploy. Verify health, league selection, all eight pages and an AI question on
   the hosted URL before relying on it. Keep sharing restricted to yourself because
   visitors would use the same server-side provider keys.

GitHub Actions runs dependency checks, compilation and tests without real keys.
Caches/usage records on Cloud disk are disposable; exports provide manual copies.
Hosting status is recorded in TESTING.md; preparation/publication is not a claim
that a hosted app has been deployed or tested.

Official references: [Gemini pricing](https://aistudio.google.com/docs/pricing),
[Python SDK function calling](https://github.com/googleapis/python-genai),
[Tavily usage](https://docs.tavily.com/documentation/api-reference/endpoint/usage),
[Sleeper API](https://docs.sleeper.com/),
[nflverse](https://github.com/nflverse/nflverse-data), and
[Community Cloud deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).
