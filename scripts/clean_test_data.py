#!/usr/bin/env python3
"""
clean_test_data.py — remove leftovers written by the OLD test suite.

Before the November 2026 fixes, running `pytest` or `python src/database.py`
used the real project folders, which left behind:

  * fake events in data/database/suddwatch.db
      (scene_id TEST_SCENE_001 / fake_scene / scene_001 / scene_002, …)
  * fake entries in data/downloaded_scenes.json
      ("scene-uuid-001": "/data/raw/scene1.zip", …)

Because some of those fake events have a flood mask with IoU 0.72, the
dashboard would show them as real events. This script removes them.

It is safe to run more than once. A timestamped backup of each file is
written next to it before anything is changed.

Usage:
    python scripts/clean_test_data.py            # show what would be removed
    python scripts/clean_test_data.py --apply    # remove it
"""
import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "database" / "suddwatch.db"
REGISTRY = ROOT / "data" / "downloaded_scenes.json"

FAKE_SCENES = ("TEST_SCENE_001", "TEST_SCENE_002", "fake_scene", "scene_001", "scene_002")
FAKE_PATH_PREFIXES = ("/data/raw/", "/tmp/")
CHILD_TABLES = ["flood_masks", "affected_populations", "infrastructure_impacts",
                "alerts", "processing_logs"]


def backup(path: Path) -> Path:
    dst = path.with_name(f"{path.stem}.backup_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}")
    shutil.copy2(path, dst)
    return dst


def clean_db(apply: bool) -> None:
    if not DB.exists():
        print(f"No database at {DB} — nothing to do.")
        return
    conn = sqlite3.connect(DB)
    marks = ",".join("?" * len(FAKE_SCENES))
    rows = conn.execute(
        f"SELECT event_id, scene_id, scene_path, status FROM events "
        f"WHERE scene_id IN ({marks}) OR scene_path LIKE '/data/raw/%' "
        f"OR scene_path LIKE '/tmp/%'", FAKE_SCENES).fetchall()
    if not rows:
        print("Database: no test events found.")
        return
    print(f"Database: {len(rows)} test event(s):")
    for r in rows:
        print(f"   event {r[0]:>3}  {r[1]:<20} {r[2] or '':<25} {r[3]}")
    if not apply:
        return
    print(f"   backup → {backup(DB).name}")
    ids = [r[0] for r in rows]
    q = ",".join("?" * len(ids))
    for table in CHILD_TABLES:
        conn.execute(f"DELETE FROM {table} WHERE event_id IN ({q})", ids)
    conn.execute(f"DELETE FROM events WHERE event_id IN ({q})", ids)
    conn.commit()
    conn.close()
    print("   removed.")


def clean_registry(apply: bool) -> None:
    if not REGISTRY.exists():
        print("Registry: not present.")
        return
    try:
        reg = json.loads(REGISTRY.read_text())
    except ValueError:
        print("Registry: unreadable JSON — leaving it alone.")
        return
    fake = {k: v for k, v in reg.items()
            if k.startswith("scene-uuid-") or k.startswith("test-")
            or str(v).startswith(FAKE_PATH_PREFIXES)}
    if not fake:
        print("Registry: no test entries found.")
        return
    print(f"Registry: {len(fake)} test entr{'y' if len(fake) == 1 else 'ies'}: {list(fake)}")
    if not apply:
        return
    print(f"   backup → {backup(REGISTRY).name}")
    REGISTRY.write_text(json.dumps({k: v for k, v in reg.items() if k not in fake}, indent=2))
    print("   removed.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually remove the test data")
    args = ap.parse_args()
    clean_db(args.apply)
    clean_registry(args.apply)
    if not args.apply:
        print("\nDry run only. Re-run with --apply to remove the items listed above.")
