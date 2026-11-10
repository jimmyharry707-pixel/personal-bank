"""Run source compilation and a temporary SQLite health check."""

from __future__ import annotations

import compileall
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    print("Compiling Python source...")
    if not compileall.compile_dir(str(ROOT / "personalbank"), quiet=1):
        print("Compilation failed.")
        return 1
    if not compileall.compile_dir(str(ROOT / "tests"), quiet=1):
        print("Test compilation failed.")
        return 1

    print("Checking a temporary SQLite database...")
    sys.path.insert(0, str(ROOT))
    from personalbank.db import Database
    from personalbank.advanced import MaintenanceService

    with tempfile.TemporaryDirectory() as temp_dir:
        database = Database(Path(temp_dir) / "check.sqlite3")
        database.initialize()
        report = MaintenanceService(database).integrity_report()
        if report["integrity"] != ["ok"] or report["foreign_key_issues"]:
            print(report)
            return 1
        print(f"SQLite integrity OK; {len(report['table_counts'])} tables created.")
    print("Project check passed. Run the unit tests separately with:")
    print("python -m unittest discover -s tests -v")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
