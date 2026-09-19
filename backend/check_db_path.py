"""Check actual database path being used."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings
from pathlib import Path

print(f"settings.database_url: {settings.database_url}")
db_path = settings.database_url.replace("sqlite:///", "")
print(f"Resolved relative path: {db_path}")
print(f"Absolute path: {Path(db_path).resolve()}")
print(f"Exists: {Path(db_path).resolve().exists()}")

# Check what init_db creates
from app.database import engine
print(f"Engine URL: {engine.url}")
print(f"Engine URL render: {engine.url.render_as_string()}")

# Check all sih.db files
import glob
for f in glob.glob("**/sih.db*", recursive=True):
    p = Path(f)
    print(f"Found: {p.resolve()} ({p.stat().st_size} bytes)")

# Check the actual file used by engine
print(f"\nEngine connects to: {Path(engine.url.database).resolve() if engine.url.database else 'unknown'}")