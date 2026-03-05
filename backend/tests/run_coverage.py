#!/usr/bin/env python3
import os
import sys
import trace
import unittest
from pathlib import Path


THRESHOLD = 85.0
ROOT = Path(__file__).resolve().parents[2]
TEST_DIR = Path(__file__).resolve().parent

TARGET_FILES = [
    ROOT / "backend" / "campus_calendar.py",
    ROOT / "backend" / "taskbar.py",
    ROOT / "backend" / "calendar_manager.py",
    ROOT / "backend" / "db_helpers.py",
    ROOT / "backend" / "uf_schedule.py",
]


def _norm(path):
    return os.path.realpath(str(path))


def _coverage_for_file(counts, file_path):
    normalized = _norm(file_path)
    executable_map = trace._find_executable_linenos(normalized)
    executable = {
        line
        for line in executable_map
        if isinstance(line, int) and line > 0
    }
    covered = {lineno for (filename, lineno), hits in counts.items() if _norm(filename) == normalized and hits > 0}
    covered_exec = executable & covered

    total = len(executable)
    hit = len(covered_exec)
    pct = (hit / total * 100.0) if total else 100.0
    return hit, total, pct


def main():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    tracer = trace.Trace(count=1, trace=0)
    runner = unittest.TextTestRunner(verbosity=2)

    def run_discovered_suite():
        suite = unittest.defaultTestLoader.discover(
            start_dir=str(TEST_DIR),
            pattern="test_*.py",
            top_level_dir=str(ROOT),
        )
        return runner.run(suite)

    test_result = tracer.runfunc(run_discovered_suite)
    if not test_result.wasSuccessful():
        return 1

    counts = tracer.results().counts

    print("\nCoverage Summary (target modules)")
    print("-------------------------------------------------------------")
    total_hit = 0
    total_exec = 0
    for file_path in TARGET_FILES:
        hit, total, pct = _coverage_for_file(counts, file_path)
        total_hit += hit
        total_exec += total
        print(f"{file_path.relative_to(ROOT)}: {hit}/{total} lines ({pct:.2f}%)")

    overall = (total_hit / total_exec * 100.0) if total_exec else 100.0
    print("-------------------------------------------------------------")
    print(f"Overall: {total_hit}/{total_exec} lines ({overall:.2f}%)")

    if overall < THRESHOLD:
        print(f"Coverage check failed: expected >= {THRESHOLD:.2f}%")
        return 2

    print(f"Coverage check passed: >= {THRESHOLD:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
