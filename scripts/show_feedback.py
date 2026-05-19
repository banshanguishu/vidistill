"""Print all user feedback from the local SQLite database.

Usage:
    poetry run python scripts/show_feedback.py

Searches a few common locations for vidistill.db (Windows dev, Docker volume).
Edit DB_CANDIDATES below if your db lives somewhere else.
"""

import sqlite3
import sys
from pathlib import Path

# Force UTF-8 stdout on Windows (default is cp936/GBK which mangles Chinese)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DB_CANDIDATES = [
    Path("/tmp/vidistill/vidistill.db"),     # local dev default (Windows resolves to current drive)
    Path("./data/vidistill.db"),             # docker volume mount on server
    Path("./vidistill.db"),                  # in-place
]


def find_db() -> Path:
    for p in DB_CANDIDATES:
        if p.exists():
            return p
    print("[err] vidistill.db not found in any of:", file=sys.stderr)
    for p in DB_CANDIDATES:
        print(f"  - {p.resolve()}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    db_path = find_db()
    print(f"[info] reading from {db_path.resolve()}\n")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, created_at, visitor_id, contact, content "
        "FROM feedback ORDER BY created_at DESC"
    ).fetchall()

    if not rows:
        print("(no feedback yet)")
        return

    print(f"Total: {len(rows)} feedback entries\n")
    for i, r in enumerate(rows, 1):
        print(f"#{i}  {r['created_at']}  visitor={r['visitor_id'][:8]}...")
        if r["contact"]:
            print(f"    contact: {r['contact']}")
        # Indent content body
        for line in r["content"].splitlines() or [r["content"]]:
            print(f"    {line}")
        print()


if __name__ == "__main__":
    main()
