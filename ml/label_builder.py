"""
Explicit label provenance (Phase 3). Every label used anywhere downstream
must be traceable to HOW it was obtained — this module is the one place
that reconciles the two label vocabularies that exist in this codebase:

  - The PIPELINE's own rule-engine output (Hotspot.category):
    industrial_normal / industrial_alert / industrial_new / wildfire /
    agricultural_burning / unknown
  - The HUMAN analyst's verification (Verification.decision), mapped to
    the canonical 5-class training taxonomy:
    INDUSTRIAL / WILDFIRE / AGRICULTURAL / NORMAL_INDUSTRIAL_HEAT / UNKNOWN

These are NOT the same taxonomy and were never explicitly mapped before
this file existed.

Label quality tiers, in increasing order of trust (uppercase — matches
the exact vocabulary specified for this project):
  "WEAK"     — candidate label from deterministic/context rules only
               (i.e. the pipeline's own category) — NEVER used as a
               supervised training target, only as a fallback/reference.
               "Near a refinery" is NOT verified ground truth, however
               confident the rule engine is.
  "CURATED"  — a label a domain expert assigned to a demo/reference case
               (schema supports it for future curated benchmark sets;
               not currently produced anywhere in this codebase).
  "VERIFIED" — an analyst confirmed it via POST /hotspots/{id}/verify.
               The ONLY tier used for supervised training.
"""
from dataclasses import dataclass
from typing import Optional

# Maps a human verification decision to the canonical training label.
# "false_positive" is deliberately NOT mapped to any of the 4 substantive
# classes, and is also NOT mapped to UNKNOWN — a false positive means "this
# wasn't a real thermal event at all" (a sensor artifact), which is a
# different concept from "real event, ambiguous type." False positives are
# stored (useful for tracking FIRMS false-positive rate) but explicitly
# EXCLUDED from supervised training — see dataset_builder.py.
VERIFIED_LABEL_VOCABULARY = {
    "confirmed_industrial_fire": "INDUSTRIAL",
    "confirmed_normal_industrial_heat": "NORMAL_INDUSTRIAL_HEAT",
    "wildfire": "WILDFIRE",
    "agricultural": "AGRICULTURAL",
    "unknown": "UNKNOWN",
    # "false_positive" intentionally has no entry here — see dataset_builder.py's
    # EXCLUDED_DECISIONS, which filters these out before training rather than
    # mapping them to a class.
}

EXCLUDED_FROM_TRAINING = {"false_positive"}


@dataclass
class LabelRecord:
    hotspot_id: int
    label: str
    label_source: str      # "firms_context" (rule engine) / "curated" / "analyst_verified"
    label_quality: str      # "WEAK" / "CURATED" / "VERIFIED"
    label_notes: Optional[str] = None
    raw_decision: Optional[str] = None   # the original Verification.decision string, if applicable


def label_from_verification(hotspot_id: int, decision: str, note: Optional[str] = None):
    """
    The ONLY function that should produce a training-eligible label.
    Returns None for excluded decisions (currently just false_positive) —
    callers must handle this by skipping the row, not defaulting it to UNKNOWN.
    """
    if decision in EXCLUDED_FROM_TRAINING:
        return None
    canonical = VERIFIED_LABEL_VOCABULARY.get(decision, "UNKNOWN")
    return LabelRecord(
        hotspot_id=hotspot_id,
        label=canonical,
        label_source="analyst_verified",
        label_quality="VERIFIED",
        label_notes=note,
        raw_decision=decision,
    )


def weak_label_from_pipeline_category(hotspot_id: int, category: str) -> LabelRecord:
    """
    For REFERENCE/COMPARISON only (e.g. checking rule-engine vs. human
    agreement rate) — NEVER pass label_quality='WEAK' records to
    ml/train.py's supervised training. See dataset_builder.py, which
    only ever queries VERIFIED records.
    """
    return LabelRecord(
        hotspot_id=hotspot_id,
        label=category.upper(),
        label_source="firms_context",
        label_quality="WEAK",
        raw_decision=None,
    )


def should_include_unknown_in_training(verified_unknown_count: int, total_verified: int,
                                        min_examples: int = 10, min_fraction: float = 0.05) -> bool:
    """
    Phase 3's explicit question: should UNKNOWN be a normal supervised
    class? Answer implemented here (Option B — included ONLY if enough
    high-quality examples exist), rather than always-include (which risks
    the model learning "when in doubt, predict abstention" from too few
    examples) or always-exclude (which would make the model incapable of
    ever outputting UNKNOWN itself, contradicting Phase 12's abstention
    requirement — though classifier.py's score-threshold abstention covers
    that separately regardless of what the training set contains).
    """
    if total_verified == 0:
        return False
    return verified_unknown_count >= min_examples and (verified_unknown_count / total_verified) >= min_fraction
