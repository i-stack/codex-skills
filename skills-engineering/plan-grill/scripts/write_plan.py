#!/usr/bin/env python3
"""Atomically persist and verify a plan-grill PLAN.md artifact."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sys
import tempfile


REQUIRED_SECTIONS = (
    "Goal",
    "Constraints & assumptions",
    "Approach",
    "Key decisions & tradeoffs",
    "Validation plan",
    "Risks / non-blocking open questions",
    "Out of scope",
)
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a validated PLAN.md below a workspace's .plan-reviews directory."
    )
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument(
        "--input",
        type=Path,
        help="Read plan Markdown from this file; otherwise read standard input.",
    )
    return parser.parse_args()


def validate_content(content: str) -> None:
    if not re.search(r"^#\s+Plan:\s+\S", content, re.MULTILINE):
        raise ValueError("missing non-empty '# Plan:' title")

    matches = list(re.finditer(r"^##\s+(.+?)\s*$", content, re.MULTILINE))
    section_bodies: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        section_bodies[match.group(1).strip()] = content[start:end].strip()

    missing = [name for name in REQUIRED_SECTIONS if not section_bodies.get(name)]
    if missing:
        raise ValueError("missing or empty required sections: " + ", ".join(missing))


def resolve_target(workspace_root: str, slug: str) -> tuple[Path, Path]:
    if not SLUG_PATTERN.fullmatch(slug):
        raise ValueError("slug must be lowercase kebab-case using ASCII letters and digits")

    root = Path(workspace_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("workspace root is not a directory")

    target = root / ".plan-reviews" / slug / "PLAN.md"
    resolved_parent = target.parent.resolve(strict=False)
    if os.path.commonpath((str(root), str(resolved_parent))) != str(root):
        raise ValueError("target escapes workspace root")
    return root, target


def atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".PLAN.md.", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            if not content.endswith("\n"):
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    args = parse_args()
    try:
        content = args.input.read_text(encoding="utf-8") if args.input else sys.stdin.read()
        validate_content(content)
        root, target = resolve_target(args.workspace_root, args.slug)
        atomic_write(target, content)

        persisted = target.read_text(encoding="utf-8")
        validate_content(persisted)
        if target.resolve().parent.parent.parent != root:
            raise RuntimeError("persisted path is outside the workspace root")

        print(target)
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"plan-grill write failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
