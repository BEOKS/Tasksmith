#!/usr/bin/env python3
"""Resolve one Tasksmith task directory and summarize its evaluation contract."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

STATUS_FILE = "현재상태.md"
DEPENDS_ON_FILE = "의존하는-작업-ID.md"
DEPENDED_BY_FILE = "의존되는-작업-ID.md"
GOAL_FILE = "목표.md"
QUANT_FILE = "통과기준-정량.md"
QUAL_FILE = "통과기준-정성.py"
REPORT_FILE = "평가결과.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve a Tasksmith task and print a summary for evaluation.",
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Task ID such as TASK-001 or an absolute/relative task directory path.",
    )
    parser.add_argument(
        "--root",
        help="Task root directory. Defaults to ./tasksmith/tasks under the current working directory.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "brief"),
        default="json",
        help="Output format.",
    )
    return parser.parse_args()


def normalize_root(raw_root: str | None) -> Path:
    if raw_root:
        return Path(raw_root).expanduser().resolve()
    return (Path.cwd() / "tasksmith" / "tasks").resolve()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_id_list(path: Path) -> list[str]:
    ids: list[str] = []
    for line in read_text(path).splitlines():
        if line.startswith("- "):
            value = line[2:].strip()
            if value and value != "없음":
                ids.append(value)
    return ids


def parse_status(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- 상태:"):
            return stripped.split(":", 1)[1].strip()
    return "미정"


def extract_heading_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    capture = False
    collected: list[str] = []
    target = heading.strip()
    for line in lines:
        stripped = line.strip()
        if stripped == target:
            capture = True
            continue
        if capture and stripped.startswith("## "):
            break
        if capture:
            collected.append(line)
    return "\n".join(collected).strip()


def parse_goal(path: Path) -> str:
    text = read_text(path)
    section = extract_heading_section(text, "## 목표 설명")
    if section:
        return section
    return text.strip()


def parse_goal_metadata(path: Path) -> tuple[str | None, str | None]:
    task_id = None
    title = None
    for line in read_text(path).splitlines():
        stripped = line.strip()
        if stripped.startswith("- 작업 ID:"):
            task_id = stripped.split(":", 1)[1].strip() or None
        elif stripped.startswith("- 작업명:"):
            title = stripped.split(":", 1)[1].strip() or None
    return task_id, title


def parse_quantitative(path: Path) -> list[dict[str, object]]:
    criteria: list[dict[str, object]] = []
    pattern = re.compile(r"^- \[(?P<mark>[ xX])\] (?P<text>.+)$")
    for line in read_text(path).splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        criteria.append(
            {
                "text": match.group("text").strip(),
                "checked": match.group("mark").lower() == "x",
            }
        )
    return criteria


def parse_qualitative_criteria(path: Path) -> list[str]:
    text = read_text(path)
    match = re.search(r"for criterion in (\[[\s\S]*?\])", text)
    if not match:
        return []
    try:
        values = ast.literal_eval(match.group(1))
    except (SyntaxError, ValueError):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def extract_statuses_from_result(payload: dict[str, object]) -> list[str]:
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return []

    statuses: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        status = check.get("status")
        if isinstance(status, str) and status.strip():
            statuses.append(status.strip())
    return statuses


def run_qualitative_check(task_dir: Path) -> dict[str, object]:
    qual_path = task_dir / QUAL_FILE
    if not qual_path.exists():
        return {
            "exists": False,
            "exit_code": None,
            "passed": False,
            "checks": [],
            "statuses": [],
            "stdout": "",
            "stderr": f"Missing file: {qual_path}",
            "parse_error": None,
        }

    completed = subprocess.run(
        [sys.executable, str(qual_path), "--json"],
        cwd=task_dir,
        capture_output=True,
        text=True,
    )

    payload: dict[str, object] | None = None
    parse_error = None
    if completed.stdout.strip():
        try:
            decoded = json.loads(completed.stdout)
            if isinstance(decoded, dict):
                payload = decoded
            else:
                parse_error = "Qualitative script JSON output was not an object."
        except json.JSONDecodeError as exc:
            parse_error = f"Failed to parse qualitative script output: {exc}"

    checks = payload.get("checks", []) if payload else []
    passed = bool(payload.get("passed")) if payload else completed.returncode == 0

    return {
        "exists": True,
        "exit_code": completed.returncode,
        "passed": passed,
        "checks": checks,
        "statuses": extract_statuses_from_result(payload or {}),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "parse_error": parse_error,
    }


def find_task_dir(tasks_root: Path, task_ref: str) -> Path:
    candidate = Path(task_ref).expanduser()
    if candidate.exists():
        resolved = candidate.resolve()
        if not resolved.is_dir():
            raise FileNotFoundError(f"Task path is not a directory: {resolved}")
        return resolved

    matches = sorted(path for path in tasks_root.glob(f"{task_ref.strip()}-*") if path.is_dir())
    if not matches:
        raise FileNotFoundError(f"No task directory found for {task_ref} under {tasks_root}")
    if len(matches) > 1:
        rendered = ", ".join(str(path) for path in matches)
        raise RuntimeError(f"Multiple task directories found for {task_ref}: {rendered}")
    return matches[0]


def inspect_dependency(tasks_root: Path, task_id: str) -> dict[str, object]:
    try:
        task_dir = find_task_dir(tasks_root, task_id)
    except (FileNotFoundError, RuntimeError) as exc:
        return {
            "task_id": task_id,
            "ready": False,
            "missing": True,
            "status": "없음",
            "task_dir": None,
            "reason": str(exc),
        }

    status = parse_status(read_text(task_dir / STATUS_FILE))
    ready = status == "완료"
    return {
        "task_id": task_id,
        "ready": ready,
        "missing": False,
        "status": status,
        "task_dir": str(task_dir),
        "reason": None if ready else f"Dependency status is {status}",
    }


def summarize_status_notes(path: Path) -> str:
    return extract_heading_section(read_text(path), "## 메모")


def build_result(task_dir: Path, tasks_root: Path) -> dict[str, object]:
    task_name = task_dir.name
    meta_task_id, meta_title = parse_goal_metadata(task_dir / GOAL_FILE)
    fallback_task_id = task_name
    fallback_title = task_name
    if meta_task_id and task_name.startswith(f"{meta_task_id}-"):
        fallback_task_id = meta_task_id
        fallback_title = task_name[len(meta_task_id) + 1 :]
    depends_on = read_id_list(task_dir / DEPENDS_ON_FILE)
    depended_by = read_id_list(task_dir / DEPENDED_BY_FILE)
    dependencies = [inspect_dependency(tasks_root, dep_id) for dep_id in depends_on]
    blocked_by = [dep["task_id"] for dep in dependencies if not dep["ready"]]
    quantitative = parse_quantitative(task_dir / QUANT_FILE)
    qualitative = run_qualitative_check(task_dir)

    result = {
        "task_dir": str(task_dir),
        "tasks_root": str(tasks_root),
        "task_id": meta_task_id or fallback_task_id,
        "title": meta_title or fallback_title,
        "status": parse_status(read_text(task_dir / STATUS_FILE)),
        "status_notes": summarize_status_notes(task_dir / STATUS_FILE),
        "goal": parse_goal(task_dir / GOAL_FILE),
        "depends_on": depends_on,
        "depended_by": depended_by,
        "dependency_statuses": dependencies,
        "blocked_by": blocked_by,
        "ready": not blocked_by,
        "quantitative_criteria": quantitative,
        "unchecked_quantitative_criteria": [
            item["text"] for item in quantitative if not bool(item["checked"])
        ],
        "qualitative_criteria": parse_qualitative_criteria(task_dir / QUAL_FILE),
        "qualitative_check": qualitative,
        "evaluation_report_path": str(task_dir / REPORT_FILE),
    }
    return result


def render_brief(result: dict[str, object]) -> str:
    blocked_by = result["blocked_by"]
    dependency_statuses = result["dependency_statuses"]
    quantitative = result["quantitative_criteria"]
    qualitative = result["qualitative_check"]

    lines = [
        f"Task ID: {result['task_id']}",
        f"Title: {result['title']}",
        f"Task Directory: {result['task_dir']}",
        f"Current Status: {result['status']}",
        f"Ready: {'yes' if result['ready'] else 'no'}",
        f"Evaluation Report: {result['evaluation_report_path']}",
        "",
        "Goal:",
        str(result["goal"]).strip() or "[목표 없음]",
        "",
        "Depends On:",
    ]

    if dependency_statuses:
        for dep in dependency_statuses:
            lines.append(f"- {dep['task_id']}: {dep['status']}")
    else:
        lines.append("- 없음")

    lines.extend(["", "Blocked By:"])
    if blocked_by:
        for dep_id in blocked_by:
            lines.append(f"- {dep_id}")
    else:
        lines.append("- 없음")

    lines.extend(["", "Quantitative Criteria:"])
    if quantitative:
        for index, item in enumerate(quantitative, start=1):
            mark = "x" if item["checked"] else " "
            lines.append(f"- [{mark}] {index}. {item['text']}")
    else:
        lines.append("- 없음")

    lines.extend(["", "Qualitative Check:"])
    if qualitative["exists"]:
        lines.append(f"- exit_code: {qualitative['exit_code']}")
        lines.append(f"- passed: {'yes' if qualitative['passed'] else 'no'}")
        statuses = qualitative["statuses"]
        if statuses:
            lines.append(f"- statuses: {', '.join(statuses)}")
        if qualitative["parse_error"]:
            lines.append(f"- parse_error: {qualitative['parse_error']}")
    else:
        lines.append("- missing")

    notes = str(result["status_notes"]).strip()
    if notes:
        lines.extend(["", "Status Notes:", notes])

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()

    try:
        tasks_root = normalize_root(args.root)
        task_dir = find_task_dir(tasks_root, args.task)
        result = build_result(task_dir, tasks_root)
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
