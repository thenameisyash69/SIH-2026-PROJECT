# SIH Evaluator Review — Ruthless Assessment

*Written as a skeptical technical judge would write it. No score is
inflated to make the project look better than the evidence supports.*

## Scores (0-10)

| Criterion | Score | Why |
|---|---|---|
| Problem understanding | 8 | The team correctly identified that FIRMS' real gap isn't detection, it's interpretation. `docs/DIFFERENTIATION.md` states this precisely and doesn't overclaim against FIRMS' actual capabilities. |
| Innovation | 7 | Facility-specific baselining + PERSISTENT_EXPECTED vs UNEXPECTED is a genuinely useful, non-obvious idea. Not novel in a research sense (facility-level anomaly detection is a known pattern in industrial monitoring), but rarely applied to public satellite fire data. |
| Technical depth | 7 | Real feature engineering, real evidence fusion, real facility-aware ML split. Docked because the ML model has never actually been trained in this environment (correctly disclosed, but still a gap) and the risk/anomaly formulas, while sound, use hand-picked thresholds with no empirical calibration. |
| AI/ML credibility | 5 | This is the weakest technical area. "Model score, not probability" is the right instinct, but there IS no deployed model right now — `/model-performance` will honestly report `NO_TRAINED_MODEL` if run today. A judge who asks "show me your model's accuracy" gets an honest "we haven't trained one yet," which is better than a fake number but is still a real gap. |
| GIS capability | 6 | Leaflet map, real NASA GIBS imagery, facility markers — solid but conventional. No routing, no polygon-based exposure analysis, no clustering at scale. |
| Data credibility | 8 | This is a real strength. Real/demo separation is enforced at the schema level (`source` column), surfaced in the UI (mode indicator, DetailPanel flag), and in `/stats`. Few hackathon projects are this disciplined about it. |
| Explainability | 9 | The strongest area. `reason`, `reason_codes`, supporting/contradicting evidence lists, and the "Generate assessment" report are all built from real stored fields, not LLM invention. This is genuinely differentiated. |
| Feasibility | 7 | The architecture is realistic for a real deployment path (facility registry ingestion, verification loop feeding future retraining). Held back only by the fact that a production facility database at national scale is explicitly out of scope, correctly disclosed. |
| Demo strength | 7 | The 8-scenario walkthrough in `docs/DEMO_RUNBOOK.md` is strong and rehearsed logic, not just architecture — but it depends entirely on the presenter actually running `seed.py` fresh, since the schema changed multiple times across this build. A demo-day database mismatch is a real risk (see Known Risks below). |
| Scalability | 5 | `landcover_fetcher.py` still does one live Overpass call per point — a real bottleneck at scale, documented but not fixed. Facility registry is 12 hardcoded rows. Both honestly flagged, but a technical judge would press on this. |
| Social/strategic impact | 7 | Believable, well-articulated use case (illegal/unregulated industrial burning detection, pollution enforcement) with a real Indian regulatory angle (CPCB/SPCB). Not quantified with real field data (correctly not fabricated). |
| Judge confidence | 7 | The documentation trail (audit → validation → limitations → evaluator review) is unusually thorough for a hackathon project and itself builds credibility — assuming the presenter actually references it instead of hiding it. |

**Overall: 6.9/10** — a technically serious, honestly-documented prototype with a real architectural differentiator, held back mainly by an untrained ML model and unvalidated statistical thresholds.

## What a strong SIH judge would like

- The FIRMS-vs-Kavach differentiation table — most competing projects will not have thought this through.
- The `PERSISTENT_EXPECTED` vs `PERSISTENT_UNEXPECTED` distinction — this is the one idea in the whole project a judge is likely to remember afterward.
- The willingness to say "insufficient data" / "unknown" / "no trained model yet" instead of a polished lie — increasingly, judges are primed to distrust confident AI demos and reward honesty.

## What a technical judge would attack

1. **"Your model has never actually been trained — walk me through why I should believe your ML story at all."** Answer honestly: the rule engine is real and load-bearing; the ML path is architecturally complete and will activate automatically once trained; `ml/train.py` has a facility-aware split specifically to avoid a leakage criticism. Do not claim more than this.
2. **"Your risk/anomaly thresholds (1.5σ, 2.5σ, the specific weight numbers in risk_engine.py) — where do these come from?"** Answer honestly: standard statistical convention, not empirically validated against real incidents. This is explicitly stated in `docs/LIMITATIONS.md` — reference it directly rather than getting defensive.
3. **"12 facilities isn't a real industrial monitoring system."** Answer: correct, and `docs/LIMITATIONS.md` says so explicitly; the schema and ingestion architecture support scaling (`source: osm_derived`), the ingestion job itself just wasn't built in hackathon time.
4. **"Your duplicate-detection key is still imperfect — two real fires at the same facility on the same exact minute would still collide."** This is true and should be conceded directly if asked — it's documented as a known trade-off.

## What still looks like FIRMS

- The base map + colored dots view (Command Center) is, visually, still "a fire map." The differentiation lives in what happens when you click a dot, not in the map itself. Make sure the demo doesn't linger on the map — get to a click within the first 30 seconds.

## What is genuinely differentiated

- `facility_fingerprint.py` + `baseline_engine.py` working together to produce `PERSISTENT_EXPECTED` — no other tool built on public FIRMS data does this.
- The evidence engine's supporting/contradicting split, shown directly in the UI.
- The verification loop (`POST /hotspots/{id}/verify`) — a real human-in-the-loop feedback mechanism, not just a "future work" bullet.

## What could cause rejection

- Demoing without re-seeding the database first (schema has changed several times; an old `sih.db` will not have the new columns and the app may error or show blank fields).
- Claiming the ML model works when a judge asks to see live metrics and `/model-performance` returns `NO_TRAINED_MODEL`.
- Overstating facility registry coverage as if it were comprehensive.

## Single biggest remaining weakness

**No trained, validated ML model exists yet.** Everything else in the intelligence layer is real and tested; this is the one place where the story is currently "architecturally ready" rather than "actually done." Running `ml/train.py` against a larger combined real+demo dataset before demo day is the single highest-leverage remaining action.

## Single strongest demo moment

Clicking a facility in **Facility Intelligence**, showing `PERSISTENT_EXPECTED` with its actual baseline numbers, then switching to a facility (or a later reading at the same one) showing `PERSISTENT_UNEXPECTED`/`ABNORMAL` with the evidence list — this is the moment that proves the product isn't "another fire map" in under 15 seconds.
