#!/usr/bin/env python3
"""Allocate sequential Tasksmith task IDs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Allocate the next sequential Tasksmith task IDs.",
    )
    parser.add_argument(
        "--root",
        help="Task root directory. Defaults to ./tasksmith/tasks.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of new IDs to allocate.",
    )
    parser.add_argument(
        "--prefix",
        default="TASK",
        help="Task ID prefix before the numeric sequence.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=3,
        help="Zero-padding width for the numeric sequence.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )
    return parser.parse_args()


def normalize_root(raw_root: str | None) -> Path:
    if raw_root:
        return Path(raw_root).expanduser().resolve()
    return (Path.cwd() / "tasksmith" / "tasks").resolve()


def validate_positive(name: str, value: int) -> int:
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0, got {value}")
    return value


def validate_prefix(prefix: str) -> str:
    normalized = prefix.strip()
    if not normalized:
        raise ValueError("prefix cannot be empty")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", normalized):
        raise ValueError("prefix may contain only letters, digits, dots, underscores, or hyphens")
    return normalized


def find_max_sequence(tasks_root: Path, prefix: str) -> int:
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)(?:-|$)")
    max_sequence = 0
    if not tasks_root.exists():
        return 0

    for path in tasks_root.iterdir():
        if not path.is_dir():
            continue
        match = pattern.match(path.name)
        if match:
            max_sequence = max(max_sequence, int(match.group(1)))

    return max_sequence


def allocate_ids(tasks_root: Path, prefix: str, width: int, count: int) -> list[str]:
    start = find_max_sequence(tasks_root, prefix) + 1
    stop = start + count
    return [f"{prefix}-{number:0{width}d}" for number in range(start, stop)]


def main() -> int:
    args = parse_args()

    try:
        tasks_root = normalize_root(args.root)
        count = validate_positive("count", args.count)
        width = validate_positive("width", args.width)
        prefix = validate_prefix(args.prefix)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    ids = allocate_ids(tasks_root, prefix, width, count)

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(tasks_root),
                    "prefix": prefix,
                    "width": width,
                    "ids": ids,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    for task_id in ids:
        print(task_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
