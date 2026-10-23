"""Decide whether the test run passed from the JUnit report, not from the process exit code.

On Windows CI, the test process can crash while the interpreter shuts down, after every test
has finished. That crash changes the exit code but not the test results. This script reads
the report written by pytest and fails only when a test failed or errored, or when no tests
ran at all.

Usage: python scripts/check_junit.py test-results.xml
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


def main(path: str) -> int:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        print(f"Could not read test report {path}: {exc}")
        return 1
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    total = failures = errors = skipped = 0
    for suite in suites:
        total += int(suite.get("tests", 0))
        failures += int(suite.get("failures", 0))
        errors += int(suite.get("errors", 0))
        skipped += int(suite.get("skipped", 0))
    passed = total - failures - errors - skipped
    print(f"Tests: {total}, passed: {passed}, skipped: {skipped}, failed: {failures}, errors: {errors}")
    if total == 0:
        print("No tests were recorded.")
        return 1
    if failures or errors:
        print("Some tests failed. See the test log above.")
        return 1
    print("All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "test-results.xml"))
