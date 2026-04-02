#!/usr/bin/env python3
"""Shared filesystem helpers for Tasksmith processor scripts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

STATUS_FILE = "현재상태.md"
GOAL_FILE = "목표.md"
REPORT_FILE = "평가결과.md"


def normalize_tasks_root(raw_root: str | None) -> Path:
    if raw_root:
        return Path(raw_root).expanduser().resolve()
    return (Path.cwd() / "tasksmith" / "tasks").resolve()


def infer_tasksmith_root(tasks_root: Path) -> Path:
    return tasks_root.parent if tasks_root.name == "tasks" else tasks_root


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse_status(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- 상태:"):
            return stripped.split(":", 1)[1].strip()
    return "미정"


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


def infer_task_identity(task_dir: Path) -> tuple[str, str]:
    meta_task_id, meta_title = parse_goal_metadata(task_dir / GOAL_FILE)
    if meta_task_id and meta_title:
        return meta_task_id, meta_title
    if meta_task_id and task_dir.name.startswith(f"{meta_task_id}-"):
        return meta_task_id, task_dir.name[len(meta_task_id) + 1 :]

    name = task_dir.name
    parts = name.split("-")
    if len(parts) >= 3 and parts[1].isdigit():
        task_id = f"{parts[0]}-{parts[1]}"
        return task_id, name[len(task_id) + 1 :]
    return name, name


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


def parse_report(path: Path) -> dict[str, object]:
    text = read_text(path)
    verdict = "없음"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- 판정:"):
            verdict = stripped.split(":", 1)[1].strip() or "없음"
            break

    unmet_items: list[str] = []
    unmet_section = extract_heading_section(text, "## 미충족 항목")
    for line in unmet_section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            unmet_items.append(stripped[2:].strip())
        elif stripped:
            unmet_items.append(stripped)

    return {
        "path": str(path),
        "exists": path.exists(),
        "verdict": verdict,
        "summary": extract_heading_section(text, "## 요약"),
        "unmet_items": unmet_items,
        "next_action": extract_heading_section(text, "## 다음 작업 제안"),
    }


def task_snapshot(task_dir: Path) -> str:
    digest = hashlib.sha256()
    digest.update(str(task_dir).encode("utf-8"))
    if not task_dir.exists():
        digest.update(b"missing")
        return digest.hexdigest()

    for path in sorted(task_dir.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        digest.update(path.relative_to(task_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(b":")
        digest.update(str(stat.st_size).encode("ascii"))
        if path.is_file():
            try:
                digest.update(path.read_bytes())
            except OSError:
                pass
    return digest.hexdigest()


def workspace_snapshot(workspace_root: Path) -> str:
    git_dir = workspace_root / ".git"
    if git_dir.exists():
        completed = subprocess.run(
            ["git", "status", "--short", "--untracked-files=all"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = {
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    else:
        payload = {"entries": []}
        for path in sorted(workspace_root.rglob("*")):
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            payload["entries"].append(
                {
                    "path": path.relative_to(workspace_root).as_posix(),
                    "mtime_ns": stat.st_mtime_ns,
                    "size": stat.st_size,
                }
            )
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def unmet_signature(unmet_items: list[str]) -> str:
    normalized = [re.sub(r"\s+", " ", item.strip()) for item in unmet_items if item.strip()]
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ensure_log_dir(tasksmith_root: Path, task_id: str) -> Path:
    log_dir = tasksmith_root / "logs" / "processor-runs" / task_id
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def build_processor_context(task_dir: Path, tasks_root: Path, workspace_root: Path) -> dict[str, object]:
    task_id, title = infer_task_identity(task_dir)
    return {
        "task_id": task_id,
        "title": title,
        "task_dir": str(task_dir),
        "tasks_root": str(tasks_root),
        "tasksmith_root": str(infer_tasksmith_root(tasks_root)),
        "workspace_root": str(workspace_root),
        "status": parse_status(read_text(task_dir / STATUS_FILE)),
        "evaluation_report": parse_report(task_dir / REPORT_FILE),
        "task_snapshot": task_snapshot(task_dir),
        "workspace_snapshot": workspace_snapshot(workspace_root),
    }
