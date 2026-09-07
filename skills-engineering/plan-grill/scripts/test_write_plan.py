#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("write_plan.py")
VALID_PLAN = """# Plan: Test

## Goal
Goal body

## Constraints & assumptions
- Constraint

## Approach
Approach body

## Key decisions & tradeoffs
- Decision

## Validation plan
- Test

## Risks / non-blocking open questions
- None

## Out of scope
- Nothing
"""


class WritePlanTests(unittest.TestCase):
    def test_writes_to_workspace_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--workspace-root",
                    directory,
                    "--slug",
                    "test-plan",
                ],
                input=VALID_PLAN,
                text=True,
                capture_output=True,
                check=False,
            )
            target = Path(directory) / ".plan-reviews" / "test-plan" / "PLAN.md"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()).resolve(), target.resolve())
            self.assertEqual(target.read_text(encoding="utf-8"), VALID_PLAN)

    def test_rejects_missing_section_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--workspace-root",
                    directory,
                    "--slug",
                    "bad-plan",
                ],
                input="# Plan: Bad\n\n## Goal\nOnly one section\n",
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((Path(directory) / ".plan-reviews").exists())

    def test_rejects_path_like_slug(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--workspace-root",
                    directory,
                    "--slug",
                    "../escape",
                ],
                input=VALID_PLAN,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((Path(directory) / ".plan-reviews").exists())


if __name__ == "__main__":
    unittest.main()
