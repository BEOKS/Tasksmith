#!/usr/bin/env python3
"""Create a Tasksmith task scaffold."""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
import unicodedata
from pathlib import Path

VALID_STATUSES = ("대기", "진행중", "완료", "보류", "차단됨")
STATUS_FILE = "현재상태.md"
DEPENDS_ON_FILE = "의존하는-작업-ID.md"
DEPENDED_BY_FILE = "의존되는-작업-ID.md"
GOAL_FILE = "목표.md"
QUANT_FILE = "통과기준-정량.md"
QUAL_FILE = "통과기준-정성.py"
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Tasksmith task scaffold under ./tasksmith/tasks.",
    )
    parser.add_argument("--root", help="Task root directory. Defaults to ./tasksmith/tasks.")
    parser.add_argument("--id", required=True, help="Task ID, for example TASK-001.")
    parser.add_argument("--title", required=True, help="Task title used in the directory name.")
    parser.add_argument(
        "--status",
        default="대기",
        help="Current task status. Prefer one of: 대기, 진행중, 완료, 보류, 차단됨.",
    )
    parser.add_argument(
        "--depends-on",
        action="append",
        default=[],
        help="Comma-separated IDs this task depends on. Repeatable.",
    )
    parser.add_argument(
        "--depended-by",
        action="append",
        default=[],
        help="Comma-separated IDs that depend on this task. Repeatable.",
    )
    parser.add_argument(
        "--goal",
        default="",
        help="Task goal text. If omitted, a placeholder is written.",
    )
    parser.add_argument(
        "--quant-criterion",
        action="append",
        default=[],
        help="Quantitative acceptance criterion. Repeatable.",
    )
    parser.add_argument(
        "--qual-criterion",
        action="append",
        default=[],
        help="Qualitative acceptance criterion for the Python checklist. Repeatable.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite files inside an existing task directory.",
    )
    parser.add_argument(
        "--no-sync-links",
        action="store_true",
        help="Do not update reciprocal dependency files in neighboring tasks.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable output.",
    )
    return parser.parse_args()


def normalize_root(raw_root: str | None) -> Path:
    if raw_root:
        return Path(raw_root).expanduser().resolve()
    return (Path.cwd() / "tasksmith" / "tasks").resolve()


def normalize_task_id(task_id: str) -> str:
    normalized = task_id.strip()
    if not normalized or not ID_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Task ID must use letters, digits, dots, underscores, or hyphens and cannot be empty."
        )
    return normalized


def normalize_title(title: str) -> str:
    normalized = unicodedata.normalize("NFC", title).strip()
    normalized = re.sub(r"[<>:\"/\\\\|?*\x00-\x1f]", "", normalized)
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-.")
    if not normalized:
        raise ValueError("Task title must contain at least one visible character.")
    return normalized


def normalize_display_title(title: str) -> str:
    normalized = unicodedata.normalize("NFC", title).strip()
    if not normalized:
        raise ValueError("Task title must contain at least one visible character.")
    return normalized


def parse_id_values(raw_values: list[str]) -> list[str]:
    parsed: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        for chunk in raw.split(","):
            candidate = chunk.strip()
            if not candidate:
                continue
            task_id = normalize_task_id(candidate)
            if task_id not in seen:
                seen.add(task_id)
                parsed.append(task_id)
    return parsed


def ensure_status(status: str) -> str:
    normalized = status.strip()
    if not normalized:
        raise ValueError("Status cannot be empty.")
    return normalized


def ensure_criteria(values: list[str], fallback: list[str]) -> list[str]:
    cleaned = [value.strip() for value in values if value.strip()]
    return cleaned if cleaned else fallback


def render_status(status: str) -> str:
    allowed = "\n".join(f"- {value}" for value in VALID_STATUSES)
    return textwrap.dedent(
        f"""\
        # 현재 상태

        - 상태: {status}

        ## 권장 상태값

        {allowed}
        """
    )


def render_id_list(title: str, ids: list[str]) -> str:
    bullets = "\n".join(f"- {task_id}" for task_id in ids) if ids else "- 없음"
    return f"# {title}\n\n{bullets}\n"


def render_goal(task_id: str, title: str, goal: str) -> str:
    body = goal.strip() or "[이 작업이 완료되었을 때 달성되어야 하는 결과를 구체적으로 작성]"
    return textwrap.dedent(
        f"""\
        # 목표

        - 작업 ID: {task_id}
        - 작업명: {title}

        ## 목표 설명

        {body}
        """
    )


def render_quantitative(criteria: list[str]) -> str:
    bullets = "\n".join(f"- [ ] {criterion}" for criterion in criteria)
    return textwrap.dedent(
        f"""\
        # 통과기준 정량

        다음 항목은 측정 가능해야 한다.

        {bullets}
        """
    )


def render_qualitative_python(task_id: str, title: str, criteria: list[str]) -> str:
    criteria_json = json.dumps(criteria, ensure_ascii=False, indent=4)
    return (
        "#!/usr/bin/env python3\n"
        f"\"\"\"Qualitative acceptance checks for {task_id}.\"\"\"\n\n"
        "from __future__ import annotations\n\n"
        "import argparse\n"
        "import json\n\n"
        f"TASK_ID = {task_id!r}\n"
        f"TASK_TITLE = {title!r}\n"
        "CHECKS = [\n"
        "    {\n"
        '        "name": criterion,\n'
        '        "status": "TODO",\n'
        '        "description": "Edit status to PASS once the qualitative review is complete.",\n'
        "    }\n"
        f"    for criterion in {criteria_json}\n"
        "]\n\n"
        "def build_result() -> dict[str, object]:\n"
        '    passed = all(check["status"] == "PASS" for check in CHECKS)\n'
        "    return {\n"
        '        "task_id": TASK_ID,\n'
        '        "task_title": TASK_TITLE,\n'
        '        "passed": passed,\n'
        '        "checks": CHECKS,\n'
        "    }\n\n"
        "def main() -> int:\n"
        "    parser = argparse.ArgumentParser(\n"
        '        description="Run qualitative acceptance checks for a Tasksmith task.",\n'
        "    )\n"
        '    parser.add_argument("--json", action="store_true", help="Print JSON output.")\n'
        "    args = parser.parse_args()\n\n"
        "    result = build_result()\n"
        "    if args.json:\n"
        "        print(json.dumps(result, ensure_ascii=False, indent=2))\n"
        "    else:\n"
        '        print(f"Task: {TASK_ID} - {TASK_TITLE}")\n'
        "        for check in CHECKS:\n"
        '            print(f"- [{check[\'status\']}] {check[\'name\']}")\n'
        '            print(f"  {check[\'description\']}")\n'
        '        print(f"Result: {\'PASS\' if result[\'passed\'] else \'FAIL\'}")\n\n'
        '    return 0 if result["passed"] else 1\n\n'
        'if __name__ == "__main__":\n'
        "    raise SystemExit(main())\n"
    )


def write_file(path: Path, content: str, executable: bool = False) -> None:
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def unique_ids(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def find_task_dirs(tasks_root: Path, task_id: str) -> list[Path]:
    return sorted(path for path in tasks_root.glob(f"{task_id}-*") if path.is_dir())


def find_task_dir(tasks_root: Path, task_id: str) -> Path | None:
    matches = find_task_dirs(tasks_root, task_id)
    if not matches:
        return None
    if len(matches) > 1:
        raise RuntimeError(f"Multiple task directories found for {task_id}: {matches}")
    return matches[0]


def read_id_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    ids: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- "):
            value = line[2:].strip()
            if value and value != "없음":
                ids.append(value)
    return ids


def write_id_file(path: Path, title: str, ids: list[str]) -> None:
    write_file(path, render_id_list(title, unique_ids(ids)))


def update_id_file(path: Path, title: str, additional_ids: list[str]) -> None:
    current = read_id_list(path)
    write_id_file(path, title, [*current, *additional_ids])


def remove_id_file_entries(path: Path, title: str, removed_ids: list[str]) -> None:
    if not removed_ids and not path.exists():
        return
    removed = set(removed_ids)
    kept = [task_id for task_id in read_id_list(path) if task_id not in removed]
    write_id_file(path, title, kept)


def sync_links(
    tasks_root: Path,
    task_id: str,
    depends_on: list[str],
    depended_by: list[str],
    previous_depends_on: list[str] | None = None,
    previous_depended_by: list[str] | None = None,
) -> list[str]:
    notes: list[str] = []
    stale_upstream = sorted(set(previous_depends_on or []) - set(depends_on))
    stale_downstream = sorted(set(previous_depended_by or []) - set(depended_by))

    for upstream_id in stale_upstream:
        upstream_dir = find_task_dir(tasks_root, upstream_id)
        if upstream_dir is None:
            notes.append(f"Skipped removing reverse link for missing upstream task {upstream_id}.")
            continue
        remove_id_file_entries(upstream_dir / DEPENDED_BY_FILE, "의존되는 작업 ID", [task_id])
        notes.append(f"Removed {task_id} from {upstream_id}/{DEPENDED_BY_FILE}.")

    for upstream_id in depends_on:
        upstream_dir = find_task_dir(tasks_root, upstream_id)
        if upstream_dir is None:
            notes.append(f"Skipped reverse link for missing upstream task {upstream_id}.")
            continue
        update_id_file(upstream_dir / DEPENDED_BY_FILE, "의존되는 작업 ID", [task_id])
        notes.append(f"Added {task_id} to {upstream_id}/{DEPENDED_BY_FILE}.")

    for downstream_id in stale_downstream:
        downstream_dir = find_task_dir(tasks_root, downstream_id)
        if downstream_dir is None:
            notes.append(f"Skipped removing reverse link for missing downstream task {downstream_id}.")
            continue
        remove_id_file_entries(downstream_dir / DEPENDS_ON_FILE, "의존하는 작업 ID", [task_id])
        notes.append(f"Removed {task_id} from {downstream_id}/{DEPENDS_ON_FILE}.")

    for downstream_id in depended_by:
        downstream_dir = find_task_dir(tasks_root, downstream_id)
        if downstream_dir is None:
            notes.append(f"Skipped reverse link for missing downstream task {downstream_id}.")
            continue
        update_id_file(downstream_dir / DEPENDS_ON_FILE, "의존하는 작업 ID", [task_id])
        notes.append(f"Added {task_id} to {downstream_id}/{DEPENDS_ON_FILE}.")

    return notes


def main() -> int:
    args = parse_args()

    try:
        tasks_root = normalize_root(args.root)
        task_id = normalize_task_id(args.id)
        display_title = normalize_display_title(args.title)
        dir_title = normalize_title(args.title)
        status = ensure_status(args.status)
        depends_on = parse_id_values(args.depends_on)
        depended_by = parse_id_values(args.depended_by)
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if task_id in depends_on or task_id in depended_by:
        print("A task cannot depend on itself.", file=sys.stderr)
        return 2

    task_dir = tasks_root / f"{task_id}-{dir_title}"
    existing_depends_on: list[str] = []
    existing_depended_by: list[str] = []
    try:
        existing_task_dir = find_task_dir(tasks_root, task_id)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if existing_task_dir is not None and existing_task_dir != task_dir:
        print(
            f"Task ID already exists at {existing_task_dir}; refusing to create a second directory for {task_id}.",
            file=sys.stderr,
        )
        return 1

    if task_dir.exists():
        existing_depends_on = read_id_list(task_dir / DEPENDS_ON_FILE)
        existing_depended_by = read_id_list(task_dir / DEPENDED_BY_FILE)

    if task_dir.exists() and not args.force:
        print(f"Task directory already exists: {task_dir}", file=sys.stderr)
        return 1

    tasks_root.mkdir(parents=True, exist_ok=True)
    task_dir.mkdir(parents=True, exist_ok=True)

    quant_criteria = ensure_criteria(
        args.quant_criterion,
        [
            "관련 산출물이 지정된 위치에 생성된다.",
            "측정 가능한 검증 명령 또는 점검 결과가 기록된다.",
        ],
    )
    qual_criteria = ensure_criteria(
        args.qual_criterion,
        [
            "산출물이 목표 설명과 실제로 일치한다.",
            "의존 관계와 상태가 작업 맥락에 맞게 정리되었다.",
        ],
    )

    write_file(task_dir / STATUS_FILE, render_status(status))
    write_file(task_dir / DEPENDS_ON_FILE, render_id_list("의존하는 작업 ID", depends_on))
    write_file(task_dir / DEPENDED_BY_FILE, render_id_list("의존되는 작업 ID", depended_by))
    write_file(task_dir / GOAL_FILE, render_goal(task_id, display_title, args.goal))
    write_file(task_dir / QUANT_FILE, render_quantitative(quant_criteria))
    write_file(
        task_dir / QUAL_FILE,
        render_qualitative_python(task_id, display_title, qual_criteria),
        executable=True,
    )

    sync_notes: list[str] = []
    if not args.no_sync_links:
        try:
            sync_notes = sync_links(
                tasks_root,
                task_id,
                depends_on,
                depended_by,
                previous_depends_on=existing_depends_on,
                previous_depended_by=existing_depended_by,
            )
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    result = {
        "task_dir": str(task_dir),
        "status": status,
        "depends_on": depends_on,
        "depended_by": depended_by,
        "sync_notes": sync_notes,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Created Tasksmith task scaffold: {task_dir}")
        for note in sync_notes:
            print(f"- {note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
