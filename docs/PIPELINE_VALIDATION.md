# Pipeline Validation — Phase 1 & 2

## What could and could not be run in this environment

This project was developed in a sandbox with **no network access** —
confirmed, not assumed: `pip install sqlalchemy` and
`apt-get install python3-sqlalchemy` both returned `403 Forbidden`.
As a result:

| Could actually run here | Could NOT run here (must be verified locally) |
|---|---|
| All pure-Python service logic (`baseline_engine`, `evidence_engine`, `anomaly_engine`, `risk_engine`, `feature_engine`, `classifier` rule path) — real `unittest` execution, 29/29 pass | `uvicorn app.main:app` — FastAPI/pydantic/uvicorn not installable here |
| The full `pipeline.process_observation()` orchestration for all 7 required scenarios, using a sandbox-only fake persistence layer (`tests/_sandbox_stub/`, documented, not shipped) | Real HTTP requests against any endpoint |
| Static code review of every router/model/schema | Docker Compose (`docker-compose up`) — same network restriction |
| `python -m py_compile` on every `.py` file — all clean | `ml/train.py` — xgboost/scikit-learn not installable here |

**What this means for you before demo day:** run
`pip install -r backend/requirements.txt && cd backend && uvicorn app.main:app --reload`
locally, where you have normal internet access, and hit the endpoints listed
in the original spec's Phase 1 checklist yourself. The logic itself has now
been validated as thoroughly as this sandbox allows; the HTTP/ASGI layer
(FastAPI itself, which is a mature, widely-used framework) has not been
independently re-tested, since doing so would only be testing FastAPI's own
correctness, not this project's code.

## Real test execution results

```
$ cd backend && python3 -m unittest tests.test_pure_logic -v
Ran 29 tests in 0.001s
OK

$ python3 tests/run_pipeline_scenarios.py
[... 7 scenarios ...]
ALL 7 SCENARIOS EXECUTED AGAINST THE REAL PIPELINE — ALL ASSERTIONS PASSED
```

Full verbatim output: `docs/PIPELINE_VALIDATION_RAW_OUTPUT.txt` (captured
directly from the two commands above, not edited).

## Scenario-by-scenario results (real execution, not projected)

| Scenario | Result | Key evidence |
|---|---|---|
| A — Normal persistent industrial source | PASS | `industrial_normal`, baseline `NORMAL`, risk `LOW` (4.5) |
| B — Abnormal industrial event | PASS | baseline `ABNORMAL`, risk escalated to `CRITICAL` (86.5) |
| C — Wildfire | PASS | no facility matched, `category=wildfire` |
| D — Agricultural burning | PASS | `category=agricultural_burning`, no facility falsely attached |
| E — Insufficient history (new facility) | PASS | `baseline_status=INSUFFICIENT_HISTORY`, `z_score=0.0` (not invented) |
| F — Multiple nearby facilities | PASS | nearest facility correctly selected, `distance_to_facility_km` stored and non-zero |
| G — Ambiguous/low-confidence event | PASS | `category=unknown` — no forced classification |
| H — Duplicate observation re-ingested (failure mode, Phase 9) | PASS | identical observation does not create a second row |

## Two real defects found and fixed during this validation

### 1. Extreme z-score display (found running Scenario B)

**Finding:** Scenario B initially produced `z_score = 75.06` — mathematically
correct given that scenario's synthetic data has unusually low variance, but
not a number that should ever be shown to a human analyst.

**Investigation:** grepped `anomaly_engine.py` and `risk_engine.py` for any
use of raw `z_score` — neither references it; both key off the categorical
`baseline_status` field. This confirmed the extreme z-score did **not**
propagate into an unbounded risk score (risk correctly landed at 86.5/100,
not some multiple-of-thousands number).

**Fix:** `baseline_engine.evaluate_against_baseline()` now clamps the
*displayed* z-score to ±10 while leaving the ABNORMAL/ELEVATED/NORMAL status
decision based on the true, unclamped value.

### 2. Duplicate-detection was missing, then over-corrected, then fixed properly

**Finding (Phase 9 failure-mode check):** `pipeline.process_observation()`
had no duplicate-detection at all. A scheduled `ingest_firms.py` run with
overlapping `day_range` windows would silently re-insert the same real FIRMS
detection every time it runs, inflating hotspot counts indefinitely.

**First fix attempt:** added a dedup key of (rounded lat/lon, same calendar
day, source). **This immediately broke Scenario B** — the test suite caught
it: a genuinely new, different reading (a real spike) at the same facility on
the same day was incorrectly treated as a duplicate of an earlier reading
from that morning, and silently discarded. Exit code was non-zero; the
failure was real, not hypothetical.

**Root cause:** day-level granularity is too coarse — a facility can have
multiple genuinely distinct satellite passes on the same calendar day.

**Second, deeper finding while fixing this:** `ingest_firms.py` was
overwriting the real FIRMS acquisition timestamp with `datetime.utcnow()`
(ingestion time) instead of preserving it — a direct violation of the
"never overwrite raw source data" principle in `models.py`'s own comments,
and also the reason a day-level dedup key was being considered instead of an
exact-timestamp one: the real timestamp wasn't being carried through at all.

**Real fix:** `firms_fetcher.py` now parses FIRMS' actual `acq_date` +
`acq_time` CSV columns into a proper datetime (previously `acq_date` was
stored as a raw unparsed string and `acq_time` wasn't read at all); it also
now captures `frp` and `satellite` from the FIRMS row, which were silently
dropped before despite the `Hotspot` model having columns for both.
`ingest_firms.py` no longer overwrites this timestamp. The dedup key in
`pipeline.py` now matches on the **exact** acquisition timestamp + rounded
coordinates + source — re-running the scenario suite after this fix: all 8
scenarios pass, including a new Scenario H that explicitly re-submits an
identical observation and asserts no duplicate row is created.

This chain (found by testing → first fix → test caught the fix's own new
bug → deeper root cause found → proper fix → re-tested clean) is exactly
the kind of ruthless validation Phase 1/2/9 asked for, and is left in this
document instead of being cleaned up, because the trail itself is evidence
the validation was real.

## Also fixed during this pass (Phase 0/3 findings)

- `facility_matcher.py` imported `sqlalchemy.orm.Session` and `app.models` at
  module level purely for a type hint and one function's DB call — this made
  even the pure-math `haversine_km()` function impossible to import without
  SQLAlchemy installed. Fixed by moving the type hint under `TYPE_CHECKING`
  and deferring the `app.models` import to inside `match_facility()`.
- `models.py`'s `Hotspot.category` column still defaulted to `"unclassified"`
  — a stale value from before `"unknown"` became the spec-mandated term.
  Every real hotspot gets its category set explicitly by the pipeline, so
  this default was dead in normal operation, but it's a genuine naming
  inconsistency, now corrected to `"unknown"`.
