"""
FIRMS configuration + connectivity diagnostic. Run this FIRST whenever
live data isn't showing up — it isolates whether the problem is
configuration loading (Task 1) or the actual NASA API call (Task 3).

Prints ONLY safe fields. The MAP_KEY value itself is NEVER printed,
logged, or included in any output this script produces — verified by
reading through this file: no line references `settings.firms_map_key`
except to compute its length.

Run with:  python -m scripts.test_firms   (from the backend/ directory)
"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.services.firms_fetcher import fetch_firms_hotspots


def status_line(label: str, ok: bool, detail: str = ""):
    marker = "OK" if ok else "FAIL"
    line = f"{label}: {marker}"
    if detail:
        line += f"  ({detail})"
    print(line)


def main():
    print("=" * 60)
    print("KAVACH — FIRMS DIAGNOSTIC")
    print("=" * 60)

    d = settings.diagnostic_snapshot()

    print("\n--- Configuration loading ---")
    print(f"Resolved .env path: {d['env_file_expected_path']}")
    print(f".env file found at that path: {d['env_file_found']}")
    print(f"Working directory: {d['resolved_working_directory']}")
    print(f"config.py loaded from: {d['config_module_actual_path']}")
    if not d["env_file_found"]:
        print("WARNING: .env was not found at the expected path — dotenv fell back to its own "
              "search, which is not guaranteed to find the file you edited. Move/create your "
              ".env at the path shown above.")

    status_line("FIRMS configuration", d["firms_configured"], f"key length={d['firms_map_key_length']}")
    print(f"FIRMS enabled: {d['firms_enabled']}")
    print(f"FIRMS area: {d['firms_area']}")
    print(f"FIRMS sources: {d['firms_sources']}")

    if d["firms_map_key_pre_existed_in_os_environ"] and not d["firms_configured"]:
        print("\nROOT CAUSE LIKELY FOUND: FIRMS_MAP_KEY already existed as an OS/shell environment "
              "variable BEFORE .env was loaded, and it was empty. Since real environment variables "
              "correctly take precedence over .env (by design), your .env file's value is being "
              "silently ignored. Check:")
        print("  - Your shell profile (.bashrc/.zshrc/PowerShell profile) for a stray FIRMS_MAP_KEY=")
        print("  - Your IDE's run configuration / 'envFile' setting (VS Code launch.json, etc.)")
        print("  - Whether you ran `set FIRMS_MAP_KEY=` or `export FIRMS_MAP_KEY=` earlier this session")
        print("  Fix: clear the stray variable from your shell/IDE config, restart the terminal, then re-run.")

    if not d["firms_configured"]:
        print("\nCannot proceed to API connectivity test — no key configured. Fix the above first.")
        return

    print("\n--- NASA FIRMS API connectivity ---")
    try:
        observations = fetch_firms_hotspots(day_range=1)
    except Exception as e:
        status_line("FIRMS API connectivity", False, str(e))
        print("\nThis means the HTTP request itself failed or NASA returned an error. Common causes:")
        print("  - Invalid or not-yet-activated MAP_KEY (new keys can take a few minutes to activate)")
        print("  - No internet access from this machine/environment")
        print("  - NASA FIRMS service temporarily down")
        return

    status_line("HTTP response", True)
    status_line("Records received", True, f"N={len(observations)}")

    if len(observations) == 0:
        print("\nNASA FIRMS returned 0 observations for this query. This is a VALID, non-error "
              "result — it means no thermal detections were reported in the configured area/time "
              "window during the last day, not that configuration is broken.")
        return

    latest = max(observations, key=lambda o: o["acq_date"])
    sources_seen = sorted(set(o.get("source_sensor", "unknown") for o in observations))

    print(f"Latest acquisition time: {latest['acq_date'].isoformat()}")
    print(f"Latest observation coordinates: ({latest['lat']:.4f}, {latest['lon']:.4f})")
    print(f"Sources returned: {sources_seen}")
    print("\nFIRMS pipeline diagnostic: ALL CHECKS PASSED.")


if __name__ == "__main__":
    main()
