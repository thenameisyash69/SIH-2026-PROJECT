# Sandbox-only compatibility stub — NOT part of the shipped product

This directory exists for ONE reason: the development sandbox used to build
this project has no network access (`pip install sqlalchemy` and
`apt-get install python3-sqlalchemy` both fail with 403 Forbidden — this was
verified, not assumed). Without SQLAlchemy installed, `app/models.py` and
`app/database.py` cannot be imported at all, which blocks running the real
pipeline even for a dry-run test.

This stub provides the minimal subset of SQLAlchemy's API surface
(`Column`, `Integer`, `String`, `Float`, `Boolean`, `DateTime`, `ForeignKey`,
`declarative_base`, `sessionmaker`, `relationship`) needed for `models.py` to
import successfully and for a plain Python list to stand in for a real table.

**What this proves:** that `app/services/pipeline.py`, `facility_fingerprint.py`,
`facility_matcher.py`, `baseline_engine.py`, `evidence_engine.py`,
`anomaly_engine.py`, `risk_engine.py`, and `classifier.py` — the REAL,
unmodified production code — produce the expected outputs when driven
end-to-end, for the seven scenarios in `docs/PIPELINE_VALIDATION.md`.

**What this does NOT prove:** real SQL correctness, index behavior, FastAPI
request/response handling, or Postgres-specific behavior. That requires
running `pip install -r requirements.txt` and the real test suite
(`tests/test_pipeline_integration.py`) in an environment with normal
internet access — which the person running this project locally has, and
this sandbox does not.

Never import this stub from application code. It is only ever added to
`sys.path` by `tests/run_pipeline_scenarios.py`, and only for the duration
of that script.
