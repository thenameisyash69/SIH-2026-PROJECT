"""Debug: test production _parse_confidence directly."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.firms_fetcher import _parse_confidence

# Test all values
test_cases = [
    ('n', 60.0),
    ('l', 30.0),
    ('h', 90.0),
    ('low', 30.0),
    ('nominal', 60.0),
    ('high', 90.0),
    ('75', 75.0),
    ('42', 42.0),
    ('xyz', 0.0),
    (None, 0.0),
    ('N', 60.0),
    ('H', 90.0),
    ('Low', 30.0),
]

print("Testing production _parse_confidence:")
all_pass = True
for raw, expected in test_cases:
    result = _parse_confidence(raw)
    status = "PASS" if result == expected else "FAIL"
    if result != expected:
        all_pass = False
    print(f"  {status}: _parse_confidence({raw!r}) = {result} (expected {expected})")

print(f"\nAll pass: {all_pass}")