#!/usr/bin/env python3
"""Resolve one Tasksmith task and summarize its processor-loop context."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from task_io import build_processor_context, find_task_dir, normalize_tasks_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve a Tasksmith task and summarize processor-loop inputs.",
    )
    parser.add_argument("--task", required=True, help="Task ID such as TASK-001 or a task directory path.")
    parser.add_argument(
        "--root",
        help="Task root directory. Defaults to ./tasksmith/tasks under the current working directory.",
    )
    parser.add_argument(
        "--workspace-root",
        help="Repository root. Defaults to the current working directory.",
    )
    parser.add_argument("--format", choices=("json", "brief"), default="json")
    return parser.parse_args()


def render_brief(result: dict[str, object]) -> str:
    report = result["evaluation_report"]
    lines = [
        f"Task ID: {result['task_id']}",
        f"Title: {result['title']}",
        f"Task Directory: {result['task_dir']}",
        f"Tasks Root: {result['tasks_root']}",
        f"Tasksmith Root: {result['tasksmith_root']}",
        f"Workspace Root: {result['workspace_root']}",
        f"Current Status: {result['status']}",
        f"Latest Verdict: {report['verdict']}",
        f"Evaluation Report: {report['path']}",
        "",
        "Unmet Items:",
    ]
    if report["unmet_items"]:
        for item in report["unmet_items"]:
            lines.append(f"- {item}")
    else:
        lines.append("- 없음")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    workspace_root = Path(args.workspace_root).expanduser().resolve() if args.workspace_root else Path.cwd().resolve()

    try:
        tasks_root = normalize_tasks_root(args.root)
        task_dir = find_task_dir(tasks_root, args.task)
        result = build_processor_context(task_dir, tasks_root, workspace_root)
    except (FileNotFoundError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.format == "brief":
        sys.stdout.write(render_brief(result))
    else:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
