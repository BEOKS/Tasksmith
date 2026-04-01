from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "skills" / "tasksmith-task-create" / "scripts" / "create_task.py"


def run_create_task(tasks_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(SCRIPT_PATH),
        "--root",
        str(tasks_root),
        *args,
    ]
    return subprocess.run(command, capture_output=True, text=True, check=False)


def read_id_list(path: Path) -> list[str]:
    ids: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- "):
            continue
        value = line[2:].strip()
        if value and value != "없음":
            ids.append(value)
    return ids


class CreateTaskScriptTests(unittest.TestCase):
    def test_rejects_duplicate_task_id_with_different_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_root = Path(tmpdir) / "tasksmith" / "tasks"

            first = run_create_task(tasks_root, "--id", "TASK-001", "--title", "Old title")
            self.assertEqual(first.returncode, 0, first.stderr)

            second = run_create_task(tasks_root, "--id", "TASK-001", "--title", "New title")
            self.assertEqual(second.returncode, 1, second.stderr)
            self.assertIn("Task ID already exists", second.stderr)
            self.assertFalse((tasks_root / "TASK-001-New-title").exists())

    def test_force_rewrite_removes_stale_reciprocal_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks_root = Path(tmpdir) / "tasksmith" / "tasks"

            for task_id in ("TASK-001", "TASK-002", "TASK-003", "TASK-004"):
                created = run_create_task(tasks_root, "--id", task_id, "--title", task_id)
                self.assertEqual(created.returncode, 0, created.stderr)

            created = run_create_task(
                tasks_root,
                "--id",
                "TASK-010",
                "--title",
                "Main task",
                "--depends-on",
                "TASK-001",
                "--depended-by",
                "TASK-003",
            )
            self.assertEqual(created.returncode, 0, created.stderr)

            self.assertEqual(
                read_id_list(tasks_root / "TASK-001-TASK-001" / "의존되는-작업-ID.md"),
                ["TASK-010"],
            )
            self.assertEqual(
                read_id_list(tasks_root / "TASK-003-TASK-003" / "의존하는-작업-ID.md"),
                ["TASK-010"],
            )

            rewritten = run_create_task(
                tasks_root,
                "--id",
                "TASK-010",
                "--title",
                "Main task",
                "--force",
                "--depends-on",
                "TASK-002",
                "--depended-by",
                "TASK-004",
            )
            self.assertEqual(rewritten.returncode, 0, rewritten.stderr)

            self.assertEqual(
                read_id_list(tasks_root / "TASK-001-TASK-001" / "의존되는-작업-ID.md"),
                [],
            )
            self.assertEqual(
                read_id_list(tasks_root / "TASK-002-TASK-002" / "의존되는-작업-ID.md"),
                ["TASK-010"],
            )
            self.assertEqual(
                read_id_list(tasks_root / "TASK-003-TASK-003" / "의존하는-작업-ID.md"),
                [],
            )
            self.assertEqual(
                read_id_list(tasks_root / "TASK-004-TASK-004" / "의존하는-작업-ID.md"),
                ["TASK-010"],
            )


if __name__ == "__main__":
    unittest.main()
