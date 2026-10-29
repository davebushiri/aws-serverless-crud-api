"""Render JUnit XML test reports as a Markdown summary (for $GITHUB_STEP_SUMMARY).

Usage: python scripts/ci_summary.py reports/unit.xml reports/integration.xml
Missing report files are listed as "not run", so a failed setup step is visible.
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def summarize(path):
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "time": 0.0}
    problems = []
    for suite in suites:
        for key in ("tests", "failures", "errors", "skipped"):
            totals[key] += int(suite.get(key, 0))
        totals["time"] += float(suite.get("time", 0))
        for case in suite.iter("testcase"):
            if case.find("failure") is not None or case.find("error") is not None:
                problems.append(f"{case.get('classname')}::{case.get('name')}")
    return totals, problems


def main(paths):
    lines = ["## Test results", "", "| Suite | Tests | Passed | Failed | Errors | Skipped | Time |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    all_problems = []
    for path in map(Path, paths):
        if not path.exists():
            lines.append(f"| {path.stem} | not run | | | | | |")
            continue
        t, problems = summarize(path)
        passed = t["tests"] - t["failures"] - t["errors"] - t["skipped"]
        lines.append(f"| {path.stem} | {t['tests']} | {passed} | {t['failures']} | {t['errors']} | {t['skipped']} | {t['time']:.1f}s |")
        all_problems += problems
    if all_problems:
        lines += ["", "### Failing tests", ""] + [f"- `{p}`" for p in all_problems]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
