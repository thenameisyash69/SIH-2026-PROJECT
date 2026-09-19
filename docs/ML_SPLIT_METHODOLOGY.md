# ML Train/Validation/Test Split Methodology

## Why not a random row-level split

A naive random split would let rows from the same facility appear in both
train and test — the model could then partially memorize that specific
facility's baseline/behavior rather than learn features that generalize to
facilities it has never seen. This is real leakage, not a theoretical
concern, for a system whose core differentiator is facility-specific
baselining.

## What Kavach actually does: facility-aware split

`ml/train.py`'s `facility_aware_split()`:
1. Groups all verified real observations by `facility_id` (rows with no
   facility get grouped under a synthetic `-1` bucket, since they share no
   facility-specific information to leak).
2. Shuffles the list of *groups* (not rows) with a fixed seed (42) for
   reproducibility.
3. Assigns ~20% of *groups* to the test set — every row from a given
   facility goes entirely to one side or the other, never split.

## Temporal separation — not yet implemented, honestly

The spec's preferred methodology also suggests temporal separation (train
on earlier observations, test on later ones or a held-out future period).
This is **not implemented** in the current `ml/train.py` — the facility-aware
split is time-agnostic within each facility's data. Reason: with the
current real data volume (0 verified observations at the time of this
pass), there isn't enough data to support a combined facility+temporal
split without the test set becoming too small to mean anything. This is
flagged in `docs/ML_LIMITATIONS.md` as a concrete next step once real
verified data volume grows — implementing it prematurely with too little
data would produce a test set of 1-2 facilities' worth of very recent rows,
which is worse than the current, simpler facility-aware split.

## Minimum data bar before any split is attempted

`MIN_VERIFIED_FOR_TRAINING = 30` (in both `ml/train.py` and
`GET /ml/labeling/stats`). Below this, `train()` returns early — no split
is even attempted, because a "held-out set" of fewer than ~6 rows (20% of
30) is not a meaningful evaluation regardless of split strategy.
