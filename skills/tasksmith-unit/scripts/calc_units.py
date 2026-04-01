#!/usr/bin/env python3
"""Calculate Tasksmith unit totals from scored buckets."""

from __future__ import annotations

import argparse
import json
import sys


RANGES = {
    "clarification": (0, 5),
    "context": (0, 8),
    "implementation": (1, 12),
    "validation": (0, 8),
    "coordination": (0, 6),
    "risk": (0, 6),
}


def validate(name: str, value: int) -> int:
    low, high = RANGES[name]
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}, got {value}")
    return value


def band_for(total: int) -> str:
    if total <= 1:
        return "atomic single-agent task"
    if total <= 4:
        return "small task"
    if total <= 8:
        return "multi-step task"
    if total <= 15:
        return "medium project"
    if total <= 30:
        return "large initiative"
    return "program-scale request"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sum Tasksmith unit buckets and print the total.",
    )
    parser.add_argument("--clarification", type=int, required=True)
    parser.add_argument("--context", type=int, required=True)
    parser.add_argument("--implementation", type=int, required=True)
    parser.add_argument("--validation", type=int, required=True)
    parser.add_argument("--coordination", type=int, required=True)
    parser.add_argument("--risk", type=int, required=True)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of text output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        scores = {
            name: validate(name, getattr(args, name))
            for name in RANGES
        }
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    total = max(1, sum(scores.values()))
    result = {
        "total_units": total,
        "band": band_for(total),
        "breakdown": scores,
    }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    print(f"Total units: {total}")
    print(f"Band: {result['band']}")
    print("Breakdown:")
    for name, value in scores.items():
        print(f"- {name}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
