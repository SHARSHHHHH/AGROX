#!/usr/bin/env python3
"""Carry your data from an older install into this one.

WHY YOU NEED THIS
-----------------
Every version of the project extracts into its own folder, and each folder has
its own `backend/agri.db`. Your farm profile, diagnoses and sensor history live
inside that file. Extracting a new zip does not touch the old folder — the data
is still there — but the new folder starts fresh, which looks exactly like
"everything was erased".

This script copies the old database across, after backing up the current one.

USAGE
    cd backend
    python scripts/migrate_data.py "C:\\Users\\You\\Documents\\old-version\\backend\\agri.db"

    python scripts/migrate_data.py --list      # show what is in both databases
    python scripts/migrate_data.py --backup    # just back up the current one
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
CURRENT_DB = BACKEND / "agri.db"

# Rows the seeder recreates on every startup. Copying these across would
# duplicate the demo accounts and schemes.
SEEDED_TABLES = {"users", "schemes"}


def summarise(db_path: Path) -> dict:
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(db_path)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        out = {}
        for t in sorted(tables):
            try:
                out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.Error:
                pass
        return out
    finally:
        conn.close()


def show(label: str, db_path: Path):
    print(f"\n{label}: {db_path}")
    if not db_path.exists():
        print("   (does not exist)")
        return
    size_kb = db_path.stat().st_size / 1024
    mtime = datetime.fromtimestamp(db_path.stat().st_mtime)
    print(f"   {size_kb:.0f} KB, last modified {mtime:%Y-%m-%d %H:%M}")
    rows = summarise(db_path)
    non_empty = {k: v for k, v in rows.items() if v}
    if not non_empty:
        print("   (empty)")
    for table, count in non_empty.items():
        marker = "  [reseeded on startup]" if table in SEEDED_TABLES else ""
        print(f"   {table:22} {count}{marker}")


def backup() -> Path:
    if not CURRENT_DB.exists():
        print("No current database to back up.")
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = CURRENT_DB.with_name(f"agri.backup-{stamp}.db")
    shutil.copy2(CURRENT_DB, dest)
    print(f"Backed up current database -> {dest.name}")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?", help="path to the OLD agri.db")
    ap.add_argument("--list", action="store_true",
                    help="show contents of both databases and exit")
    ap.add_argument("--backup", action="store_true",
                    help="back up the current database and exit")
    args = ap.parse_args()

    if args.backup:
        backup()
        return 0

    if args.list or not args.source:
        show("CURRENT", CURRENT_DB)
        if args.source:
            show("SOURCE", Path(args.source))
        if not args.source:
            print("\nTo migrate:  python scripts/migrate_data.py <path-to-old-agri.db>")
        return 0

    source = Path(args.source).expanduser().resolve()

    if not source.exists():
        print(f"ERROR: source database not found: {source}")
        return 1

    if source == CURRENT_DB.resolve():
        print("ERROR: source and destination are the same file.")
        return 1

    try:
        sqlite3.connect(source).execute("SELECT 1 FROM sqlite_master LIMIT 1")
    except sqlite3.Error as exc:
        print(f"ERROR: '{source}' is not a readable SQLite database ({exc}).")
        return 1

    show("SOURCE (will be copied in)", source)
    show("CURRENT (will be backed up first)", CURRENT_DB)

    reply = input("\nReplace the current database with the source? [y/N] ").strip().lower()
    if reply != "y":
        print("Cancelled. Nothing was changed.")
        return 0

    backup()
    shutil.copy2(source, CURRENT_DB)
    print(f"\nMigrated {source.name} -> {CURRENT_DB}")
    print("Restart the backend. Existing demo users and schemes are re-seeded "
          "automatically, so any that were missing will reappear.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
