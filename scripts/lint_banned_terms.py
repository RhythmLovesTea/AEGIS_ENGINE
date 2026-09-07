#!/usr/bin/env python3
"""
AEGIS-Marine CI Linter: Banned Term Enforcement (Rule 6)

Enforces PRD Section 17 & rules.md Section 1 Rule 6:
Language matters — enforce it in code, not just copy review.

Banned Terms in UI copy, PDF templates, API error messages, and notification text:
- "responsible vessel"
- "guilty"
- "polluter" (as a determination rather than category label)
- "proven"
- "confirmed the culprit"

Approved Phrasing:
- "most correlated vessel"
- "candidate suspect"
- "potential source"
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

BANNED_RULES: list[dict[str, str]] = [
    {
        "pattern": r"\bresponsible\s+vessel\b",
        "name": "responsible vessel",
        "suggestion": "most correlated vessel / candidate suspect",
    },
    {
        "pattern": r"\bguilty\b",
        "name": "guilty",
        "suggestion": "candidate suspect / potential source",
    },
    {
        "pattern": r"\bconfirmed\s+(?:the\s+)?culprit\b",
        "name": "confirmed the culprit",
        "suggestion": "most correlated candidate",
    },
    {
        "pattern": r"\bproven\b",
        "name": "proven",
        "suggestion": "statistically correlated / physically consistent",
    },
    {
        "pattern": r"\b(?:identified|the|this|is\s+a)\s+polluter\b",
        "name": "polluter (as determination)",
        "suggestion": "potential discharge source / candidate suspect",
    },
]

DEFAULT_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".html",
    ".jinja",
    ".jinja2",
    ".json",
    ".yaml",
    ".yml",
}

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "__pycache__",
    "dist",
    "build",
    "data",
}

DEFAULT_EXCLUDED_FILES = {
    "rules.md",
    "AEGIS-Marine_PRD.md",
    "AEGIS-Marine_Architecture.md",
    "TODO.md",
    "prompt_for_best_response.md",
    "lint_banned_terms.py",
    "test_lint_banned_terms.py",
}


@dataclass
class Violation:
    file_path: Path
    line_number: int
    rule_name: str
    suggestion: str
    line_content: str


def check_content(content: str, file_path: Path) -> List[Violation]:
    violations: List[Violation] = []
    lines = content.splitlines()

    for line_idx, line in enumerate(lines, start=1):
        # Skip commented-out meta discussions citing Rule 6 or linter directives
        if "# noqa: banned-terms" in line or "// noqa: banned-terms" in line:
            continue

        for rule in BANNED_RULES:
            if re.search(rule["pattern"], line, re.IGNORECASE):
                violations.append(
                    Violation(
                        file_path=file_path,
                        line_number=line_idx,
                        rule_name=rule["name"],
                        suggestion=rule["suggestion"],
                        line_content=line.strip(),
                    )
                )
    return violations


def scan_directory(
    root_dir: Path,
    extensions: set[str] = DEFAULT_EXTENSIONS,
    excluded_dirs: set[str] = DEFAULT_EXCLUDED_DIRS,
    excluded_files: set[str] = DEFAULT_EXCLUDED_FILES,
) -> List[Violation]:
    all_violations: List[Violation] = []

    for path in root_dir.rglob("*"):
        if path.is_dir():
            continue
        if any(part in excluded_dirs for part in path.parts):
            continue
        if path.name in excluded_files:
            continue
        if path.suffix.lower() not in extensions:
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        violations = check_content(content, path)
        all_violations.extend(violations)

    return all_violations


def run_self_tests() -> bool:
    """Self-verification test suite for the linter."""
    print("Running lint_banned_terms self-tests...")

    # Case 1: Clean approved string
    clean_sample = "The most correlated vessel is candidate suspect IMO 9234567."
    v1 = check_content(clean_sample, Path("dummy_clean.py"))
    assert len(v1) == 0, f"Expected 0 violations for clean text, got {len(v1)}"

    # Case 2: Banned "responsible vessel"
    vessel_sample = "We identified the responsible vessel yesterday."
    v2 = check_content(vessel_sample, Path("dummy_vessel.py"))
    assert len(v2) == 1, f"Expected 1 violation for 'responsible vessel', got {len(v2)}"
    assert v2[0].rule_name == "responsible vessel"

    # Case 3: Banned "guilty"
    guilty_sample = "This ship is guilty of the discharge."
    v3 = check_content(guilty_sample, Path("dummy_guilty.py"))
    assert len(v3) == 1, f"Expected 1 violation for 'guilty', got {len(v3)}"

    # Case 4: Banned "confirmed the culprit"
    culprit_sample = "Analysis confirmed the culprit with 99% accuracy."
    v4 = check_content(culprit_sample, Path("dummy_culprit.py"))
    assert len(v4) == 1, f"Expected 1 violation for 'confirmed the culprit', got {len(v4)}"

    # Case 5: Banned "proven"
    proven_sample = "The origin has been proven beyond doubt."
    v5 = check_content(proven_sample, Path("dummy_proven.py"))
    assert len(v5) == 1, f"Expected 1 violation for 'proven', got {len(v5)}"

    # Case 6: Banned "the polluter" determination
    polluter_sample = "Tracking the polluter along the coastline."
    v6 = check_content(polluter_sample, Path("dummy_polluter.py"))
    assert len(v6) == 1, f"Expected 1 violation for 'the polluter', got {len(v6)}"

    # Case 7: Ignored via noqa comment
    noqa_sample = "responsible vessel # noqa: banned-terms"
    v7 = check_content(noqa_sample, Path("dummy_noqa.py"))
    assert len(v7) == 0, f"Expected 0 violations for noqa comment, got {len(v7)}"

    print("All 7 self-tests passed successfully!")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AEGIS-Marine Rule 6 Banned Term Linter")
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("."),
        help="Root path to scan (defaults to repository root)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run linter self-tests and exit",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-error messages",
    )

    args = parser.parse_args(argv)

    if args.test:
        success = run_self_tests()
        return 0 if success else 1

    violations = scan_directory(args.path)

    if violations:
        print("\n❌ Rule 6 Banned Term Violations Detected:")
        print("=" * 70)
        for v in violations:
            print(f"File: {v.file_path}:{v.line_number}")
            print(f"  Violation : Found '{v.rule_name}'")
            print(f"  Snippet   : {v.line_content}")
            print(f"  Suggested : Replace with '{v.suggestion}'")
            print("-" * 70)
        print(f"\nTotal violations: {len(violations)}")
        print("CI Check Failed: Please update to approved terminology per rules.md Section 1.")
        return 1

    if not args.quiet:
        print("✅ Rule 6 Terminology Compliance: Clean! No banned terms found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
