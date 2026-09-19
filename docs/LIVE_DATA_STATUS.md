# Live Data Status — Configuration Bug Trace & Fix

## Root cause

**Most likely cause, confirmed reproducible by actual test:** a bare
`load_dotenv()` call (no explicit path, default `override=False`) has two
real failure modes, either of which produces exactly the reported symptom
("`.env` visibly has the key, but the app says it's not set"):

1. **A pre-existing OS/shell environment variable shadows `.env`.**
   `load_dotenv()`'s default behavior — correctly, per this project's own
   Task 2 requirement that real env vars take precedence — will NOT
   override a variable that's already set in the process environment, even
   if that variable is an empty string. If `FIRMS_MAP_KEY` was ever
   `set`/`export`-ed empty in a shell session, left over in a shell profile,
   or loaded by an IDE's own "envFile" mechanism before this app's
   `load_dotenv()` runs, `.env`'s real value is silently ignored.
   **This was reproduced with an actual test in this pass** (see below) —
   it is not a hypothesis, it is a demonstrated real bug pattern.

2. **Non-deterministic `.env` file discovery.** A bare `load_dotenv()`'s
   file-search behavior depends on python-dotenv's internal frame/cwd
   logic, which is not guaranteed to resolve to the same file when
   `uvicorn` is launched from `backend/` vs. the project root vs. a
   nested/duplicate extracted copy of the project (a real risk given this
   project has been re-extracted/re-zipped multiple times across this
   build's history).

### Reproduction (actually executed, not just reasoned about)

```
$ echo "FIRMS_MAP_KEY=test_key_1234567890" > .env
$ python3 -m scripts.test_firms
...
FIRMS configuration: OK  (key length=19)          <- works normally

$ FIRMS_MAP_KEY="" python3 -m scripts.test_firms   <- simulates a stray empty OS var
...
FIRMS configuration: FAIL  (key length=0)
ROOT CAUSE LIKELY FOUND: FIRMS_MAP_KEY already existed as an OS/shell
environment variable BEFORE .env was loaded, and it was empty...
```

This is the exact failure signature: `.env` genuinely contains a valid key
(confirmed present, 19 characters), yet the running application reports
zero-length / not configured — reproduced with the identical `.env`
content in both runs, the only difference being a pre-set OS variable.

## Files changed

- `backend/app/config.py` — rewritten: explicit deterministic `.env` path
  (`<config.py's directory>/../.env`, always resolves to `backend/.env`
  regardless of working directory), a pre-`load_dotenv()` snapshot of
  which relevant variables already existed in `os.environ` (this is what
  makes the diagnosis possible at all), a `diagnostic_snapshot()` method
  returning only safe fields (booleans/lengths/paths, never the key), and
  support for the `FIRMS_ENABLE` (no "D") typo as a documented alias for
  `FIRMS_ENABLED`.
- `backend/app/main.py` — startup now unconditionally prints the safe
  diagnostic snapshot, with an explicit warning line when the
  shadowed-by-OS-env-var pattern is detected.
- `backend/scripts/test_firms.py` — new. Configuration diagnosis, then (only
  if configured) a real NASA API connectivity test — separated into two
  phases so you know immediately which layer is failing.
- `backend/app/services/firms_ingestion.py` — `get_firms_status()` now
  returns a truthful, specific `offline_reason` (distinguishing "no .env
  found" from "shadowed by OS env var" from "genuinely never set") instead
  of one generic string, plus `latest_acquisition_time` and
  `sources_configured` per Task 5's requirements.
- `backend/app/routers/data_sources.py` — status endpoint uses the new
  specific `offline_reason`; added `GET /data-sources/firms/diagnostics`
  (safe fields only) so this can be checked from a browser, not just CLI.
- `.gitignore` — **did not exist before this pass.** Added, covering `.env`
  specifically (Task 2 explicitly requires this) plus the usual Python/
  Node/database artifacts.

## Configuration loading mechanism (as it now works)

1. `backend/app/config.py` computes `ENV_PATH` as an absolute path derived
   from its own file location — never ambiguous, never dependent on cwd.
2. Snapshots whether `FIRMS_MAP_KEY`/`FIRMS_ENABLED`/`FIRMS_ENABLE` already
   existed in `os.environ` — this is the diagnostic signal.
3. Calls `load_dotenv(dotenv_path=ENV_PATH, override=False)` — real env
   vars still correctly take precedence (Task 2's explicit requirement),
   but now the search path itself is deterministic.
4. `Settings.diagnostic_snapshot()` exposes exactly enough to debug this
   class of problem without ever exposing the secret itself.

## FIRMS endpoint used

`https://firms.modaps.eosdis.nasa.gov/api/area/csv/<MAP_KEY>/<SENSOR>/<AREA>/<DAY_RANGE>`
— one request per configured sensor (`VIIRS_NOAA21_NRT`, `VIIRS_NOAA20_NRT`
by default), area `68,6,97,37` (India) by default, `day_range=1` for live
sync. Response parsing, empty-response handling (0 rows is a valid,
non-error result, not a failure), and NASA error-string detection (a bad
key returns a one-line CSV error, not valid data — checked for explicitly
in `firms_fetcher.py`) were all already implemented in a prior pass and
were not the source of this bug — this bug was entirely in configuration
loading, not the API client itself.

## Test command

```
cd backend
python -m scripts.test_firms
```

## Observed real record count / timestamp of successful test

**Not yet run against the user's real, configured `FIRMS_MAP_KEY`** — this
development sandbox has no network access to make that exact call (same
constraint noted throughout this project's build history). The most recent
real evidence available is from the prior pass: 79 valid real NASA FIRMS
observations (MODIS Terra + VIIRS Suomi-NPP), fetched via a separate tool
with genuine internet access on 2026-09-06/07, and proven to run correctly
through the full real intelligence pipeline (see
`docs/ML_TRAINING_PIPELINE.md`, `backend/tests/run_real_snapshot_load.py`).
**The user must run `python -m scripts.test_firms` themselves** with their
real key to get a first-hand record count and timestamp — this is the
single next action.

## Known limitations

- This fix addresses the most probable root cause based on the evidence
  given (`.env` confirmed to contain the key, app confirmed to report it
  missing) and a reproduced failure pattern matching that exact symptom —
  but it was not verified against the user's actual machine/shell, since
  that's not accessible from this environment. If `python -m
  scripts.test_firms` still reports `FAIL` after this fix, the diagnostic
  output itself (paths, pre-existing-var flags) should pinpoint the
  remaining cause precisely, rather than requiring another guess.
- The `FIRMS_ENABLE`/`FIRMS_ENABLED` alias is a pragmatic fix for an
  observed typo, not a general-purpose config-aliasing system — only this
  one pair is aliased.
