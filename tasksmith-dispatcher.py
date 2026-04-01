#!/usr/bin/env python3
"""Watch a Tasksmith .tasksmith directory and dispatch processable tasks."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shlex
import signal
import stat as stat_module
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import TextIO

STATUS_FILE = "현재상태.md"
DEPENDS_ON_FILE = "의존하는-작업-ID.md"
GOAL_FILE = "목표.md"

STATUS_WAITING = "대기"
STATUS_RUNNING = "진행중"
STATUS_DONE = "완료"
STATUS_HOLD = "보류"
STATUS_BLOCKED = "차단됨"

DISPATCHER_NOTE_PREFIX = "[tasksmith-dispatcher]"


@dataclass
class TaskInfo:
    task_id: str
    task_dir: Path
    status: str
    depends_on: list[str]


@dataclass
class RunningDispatch:
    task_id: str
    task_dir: Path
    pid: int
    launched_at: str
    state_file: Path
    stdout_log: Path
    stderr_log: Path
    process: subprocess.Popen[str] | None = None
    stdout_handle: TextIO | None = None
    stderr_handle: TextIO | None = None

    @property
    def is_external(self) -> bool:
        return self.process is None

    def close_handles(self) -> None:
        if self.stdout_handle:
            self.stdout_handle.close()
            self.stdout_handle = None
        if self.stderr_handle:
            self.stderr_handle.close()
            self.stderr_handle = None


class DispatcherError(RuntimeError):
    """Raised when the dispatcher cannot continue safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Watch a Tasksmith .tasksmith directory, dispatch processable tasks "
            "to a non-interactive agent, and exit when every observed task is 완료."
        )
    )
    parser.add_argument(
        "tasksmith_dir",
        help="Absolute path to the .tasksmith directory that contains a tasks/ subdirectory.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds for filesystem changes. Default: 2.0",
    )
    parser.add_argument(
        "--runner",
        choices=("codex", "claude"),
        default="codex",
        help="Non-interactive agent runner to use. Default: codex",
    )
    parser.add_argument(
        "--runner-bin",
        help="Override the executable name for the chosen runner.",
    )
    parser.add_argument(
        "--log-file",
        help="Path to the main dispatcher log file. Defaults to .tasksmith/logs/tasksmith-dispatcher.log",
    )
    parser.add_argument(
        "--codex-model",
        help="Optional model override for codex exec.",
    )
    parser.add_argument(
        "--claude-model",
        help="Optional model override for claude -p.",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_tasksmith_dir(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise DispatcherError("tasksmith_dir must be an absolute path to .tasksmith.")
    resolved = path.resolve()
    if not resolved.exists():
        raise DispatcherError(f".tasksmith directory does not exist: {resolved}")
    if not resolved.is_dir():
        raise DispatcherError(f".tasksmith path is not a directory: {resolved}")
    return resolved


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_status(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- 상태:"):
            return stripped.split(":", 1)[1].strip()
    return "미정"


def read_status(path: Path) -> str:
    return parse_status(read_text(path))


def read_id_list(path: Path) -> list[str]:
    ids: list[str] = []
    for line in read_text(path).splitlines():
        if not line.startswith("- "):
            continue
        value = line[2:].strip()
        if value and value != "없음":
            ids.append(value)
    return ids


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


def infer_task_id(task_dir: Path) -> str:
    explicit_id, _ = parse_goal_metadata(task_dir / GOAL_FILE)
    if explicit_id:
        return explicit_id

    name = task_dir.name
    parts = name.split("-")
    if len(parts) >= 3 and parts[1].isdigit():
        return f"{parts[0]}-{parts[1]}"
    return name


def extract_heading_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    collected: list[str] = []
    capture = False
    for line in lines:
        stripped = line.strip()
        if stripped == heading:
            capture = True
            continue
        if capture and stripped.startswith("## "):
            break
        if capture:
            collected.append(line)
    return "\n".join(collected).strip()


def append_note_to_text(text: str, note: str) -> str:
    note_line = f"- {note}"
    if note_line in text:
        return text

    lines = text.rstrip("\n").splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "## 메모":
            continue

        insert_at = len(lines)
        for cursor in range(index + 1, len(lines)):
            if lines[cursor].strip().startswith("## "):
                insert_at = cursor
                break

        if insert_at > index + 1 and lines[insert_at - 1].strip():
            lines.insert(insert_at, "")
            insert_at += 1
        lines.insert(insert_at, note_line)
        return "\n".join(lines).rstrip() + "\n"

    return text.rstrip() + f"\n\n## 메모\n\n{note_line}\n"


def build_status_text(status: str, note: str, existing_text: str) -> str:
    lines = existing_text.splitlines()
    updated_lines: list[str] = []
    replaced_status = False

    for line in lines:
        if line.strip().startswith("- 상태:") and not replaced_status:
            updated_lines.append(f"- 상태: {status}")
            replaced_status = True
            continue
        updated_lines.append(line)

    if not updated_lines:
        updated_lines = ["# 현재 상태", "", f"- 상태: {status}"]
        replaced_status = True

    if not replaced_status:
        if updated_lines and updated_lines[0].strip() == "# 현재 상태":
            updated_lines.insert(1, "")
            updated_lines.insert(2, f"- 상태: {status}")
        else:
            updated_lines = ["# 현재 상태", "", f"- 상태: {status}", ""] + updated_lines

    updated_text = "\n".join(updated_lines).rstrip() + "\n"
    if note:
        updated_text = append_note_to_text(updated_text, note)

    return updated_text


def update_task_status(task_dir: Path, status: str, note: str) -> None:
    status_path = task_dir / STATUS_FILE
    updated = build_status_text(status, note, read_text(status_path))
    write_text(status_path, updated)


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def configure_logging(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("tasksmith-dispatcher")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S%z",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def iter_task_dirs(tasks_root: Path) -> list[Path]:
    if not tasks_root.exists():
        return []
    return sorted(path for path in tasks_root.iterdir() if path.is_dir())


def load_tasks(tasks_root: Path) -> dict[str, TaskInfo]:
    tasks: dict[str, TaskInfo] = {}
    for task_dir in iter_task_dirs(tasks_root):
        task_id = infer_task_id(task_dir)
        if task_id in tasks:
            raise DispatcherError(
                f"Duplicate task_id detected: {task_id} at {task_dir} and {tasks[task_id].task_dir}"
            )
        tasks[task_id] = TaskInfo(
            task_id=task_id,
            task_dir=task_dir,
            status=read_status(task_dir / STATUS_FILE),
            depends_on=read_id_list(task_dir / DEPENDS_ON_FILE),
        )
    return tasks


def find_task_dir(tasks_root: Path, task_ref: str) -> Path | None:
    matches = sorted(path for path in tasks_root.glob(f"{task_ref.strip()}-*") if path.is_dir())
    if len(matches) == 1:
        return matches[0]
    return None


def blocked_reasons(task: TaskInfo, tasks: dict[str, TaskInfo], tasks_root: Path) -> list[str]:
    reasons: list[str] = []
    if task.status != STATUS_WAITING:
        reasons.append(f"status={task.status}")

    for dep_id in task.depends_on:
        dep_task = tasks.get(dep_id)
        if dep_task is not None:
            if dep_task.status != STATUS_DONE:
                reasons.append(f"dependency {dep_id} is {dep_task.status}")
            continue

        dep_dir = find_task_dir(tasks_root, dep_id)
        if dep_dir is None:
            reasons.append(f"dependency {dep_id} is missing")
            continue

        dep_status = read_status(dep_dir / STATUS_FILE)
        if dep_status != STATUS_DONE:
            reasons.append(f"dependency {dep_id} is {dep_status}")

    return reasons


def is_processable(task: TaskInfo, tasks: dict[str, TaskInfo], tasks_root: Path) -> bool:
    return not blocked_reasons(task, tasks, tasks_root)


def compute_tree_signature(tasks_root: Path) -> str:
    digest = sha256()
    digest.update(str(tasks_root).encode("utf-8"))
    if not tasks_root.exists():
        digest.update(b"missing")
        return digest.hexdigest()

    for path in sorted(tasks_root.rglob("*")):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        relative = path.relative_to(tasks_root).as_posix()
        is_dir = stat_module.S_ISDIR(stat.st_mode)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0d" if is_dir else b"\0f")
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(b":")
        digest.update(str(stat.st_size).encode("ascii"))
    return digest.hexdigest()


def build_processor_prompt(task_dir: Path, tasksmith_dir: Path) -> str:
    return (
        "Use $tasksmith-processor to supervise one Tasksmith task.\n\n"
        f"Task directory: {task_dir}\n"
        f"Tasksmith root: {tasksmith_dir}\n"
        "Repository root: use the current working directory.\n"
        "Read the task files directly and run the full processor loop through fresh "
        "non-interactive worker/evaluator attempts until the task reaches a terminal outcome."
    )


def build_runner_command(
    runner: str,
    runner_bin: str,
    workspace_root: Path,
    prompt: str,
    codex_model: str | None,
    claude_model: str | None,
) -> list[str]:
    if runner == "codex":
        command = [
            runner_bin,
            "exec",
            "--skip-git-repo-check",
            "--full-auto",
            "--ephemeral",
            "--color",
            "never",
            "-C",
            str(workspace_root),
        ]
        if codex_model:
            command.extend(["-m", codex_model])
        command.append(prompt)
        return command

    command = [runner_bin, "-p"]
    if claude_model:
        command.extend(["--model", claude_model])
    command.append(prompt)
    return command


def write_runtime_state(state_file: Path, dispatch: RunningDispatch) -> None:
    payload = {
        "task_id": dispatch.task_id,
        "task_dir": str(dispatch.task_dir),
        "pid": dispatch.pid,
        "launched_at": dispatch.launched_at,
        "stdout_log": str(dispatch.stdout_log),
        "stderr_log": str(dispatch.stderr_log),
    }
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = state_file.with_name(
        f".{state_file.name}.tmp-{os.getpid()}-{time.time_ns()}"
    )
    try:
        temp_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_file, state_file)
    finally:
        try:
            temp_file.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def load_runtime_state(path: Path) -> dict[str, object]:
    return json.loads(read_text(path))


def remove_runtime_state(path: Path, logger: logging.Logger) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.warning("Failed to remove runtime state %s: %s", path, exc)


def extract_jsonish_string(raw: str, field: str) -> str | None:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    if match is None:
        return None

    try:
        return json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return match.group(1)


def extract_jsonish_int(raw: str, field: str) -> int | None:
    match = re.search(rf'"{re.escape(field)}"\s*:\s*(-?\d+)', raw)
    if match is None:
        return None

    try:
        return int(match.group(1))
    except ValueError:
        return None


def recover_unreadable_runtime_state(
    state_file: Path,
    raw: str,
    tasks_root: Path,
    logger: logging.Logger,
    reason: str,
) -> RunningDispatch | None:
    task_id = extract_jsonish_string(raw, "task_id")
    task_dir_value = extract_jsonish_string(raw, "task_dir")
    pid = extract_jsonish_int(raw, "pid")
    launched_at = extract_jsonish_string(raw, "launched_at") or now_iso()
    stdout_log_value = extract_jsonish_string(raw, "stdout_log")
    stderr_log_value = extract_jsonish_string(raw, "stderr_log")

    task_dir: Path | None = None
    if task_dir_value:
        task_dir = Path(task_dir_value)
    elif task_id:
        task_dir = find_task_dir(tasks_root, task_id)

    if task_id is None and task_dir is not None:
        task_id = infer_task_id(task_dir)

    if task_id and task_dir and pid is not None and is_pid_alive(pid):
        logger.warning(
            "Recovered partial runtime state %s for task_id=%s pid=%s despite %s",
            state_file,
            task_id,
            pid,
            reason,
        )
        return RunningDispatch(
            task_id=task_id,
            task_dir=task_dir,
            pid=pid,
            launched_at=launched_at,
            state_file=state_file,
            stdout_log=Path(stdout_log_value) if stdout_log_value else Path("/dev/null"),
            stderr_log=Path(stderr_log_value) if stderr_log_value else Path("/dev/null"),
        )

    if task_dir is not None:
        status = read_status(task_dir / STATUS_FILE)
        if status == STATUS_RUNNING:
            note = (
                f"{DISPATCHER_NOTE_PREFIX} {now_iso()} unreadable dispatcher runtime state "
                f"({reason}); status reset to 대기 for redispatch."
            )
            update_task_status(task_dir, STATUS_WAITING, note)
            logger.warning(
                "Recovered unreadable runtime state %s for task_id=%s and reset status to %s",
                state_file,
                task_id or infer_task_id(task_dir),
                STATUS_WAITING,
            )
        else:
            logger.info(
                "Removed unreadable runtime state %s for task_id=%s current_status=%s",
                state_file,
                task_id or infer_task_id(task_dir),
                status,
            )
    else:
        logger.warning(
            "Removed unreadable runtime state %s without task mapping: %s",
            state_file,
            reason,
        )

    remove_runtime_state(state_file, logger)
    return None


def recover_previous_dispatches(
    runtime_dir: Path,
    tasks_root: Path,
    logger: logging.Logger,
) -> dict[str, RunningDispatch]:
    running: dict[str, RunningDispatch] = {}
    runtime_dir.mkdir(parents=True, exist_ok=True)

    for state_file in sorted(runtime_dir.glob("*.json")):
        raw = read_text(state_file)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            recovered = recover_unreadable_runtime_state(
                state_file=state_file,
                raw=raw,
                tasks_root=tasks_root,
                logger=logger,
                reason=f"corrupt JSON: {exc}",
            )
            if recovered is not None:
                running[recovered.task_id] = recovered
            continue

        task_id = str(payload.get("task_id", "")).strip()
        task_dir_value = str(payload.get("task_dir", "")).strip()
        pid_value = payload.get("pid")
        launched_at = str(payload.get("launched_at", "")).strip() or now_iso()
        stdout_log = Path(str(payload.get("stdout_log", "")).strip())
        stderr_log = Path(str(payload.get("stderr_log", "")).strip())

        if not task_id or not task_dir_value or not isinstance(pid_value, int):
            recovered = recover_unreadable_runtime_state(
                state_file=state_file,
                raw=raw,
                tasks_root=tasks_root,
                logger=logger,
                reason="incomplete runtime metadata",
            )
            if recovered is not None:
                running[recovered.task_id] = recovered
            continue

        task_dir = Path(task_dir_value)
        if is_pid_alive(pid_value):
            running[task_id] = RunningDispatch(
                task_id=task_id,
                task_dir=task_dir,
                pid=pid_value,
                launched_at=launched_at,
                state_file=state_file,
                stdout_log=stdout_log,
                stderr_log=stderr_log,
            )
            logger.info(
                "Recovered running dispatch task_id=%s pid=%s task_dir=%s",
                task_id,
                pid_value,
                task_dir,
            )
            continue

        status = read_status(task_dir / STATUS_FILE)
        if status == STATUS_RUNNING:
            note = (
                f"{DISPATCHER_NOTE_PREFIX} {now_iso()} stale dispatch pid={pid_value} "
                "was not alive; status reset to 대기 for redispatch."
            )
            update_task_status(task_dir, STATUS_WAITING, note)
            logger.warning(
                "Recovered stale dispatch task_id=%s pid=%s and reset status to %s",
                task_id,
                pid_value,
                STATUS_WAITING,
            )
        else:
            logger.info(
                "Removed stale runtime state for task_id=%s pid=%s current_status=%s",
                task_id,
                pid_value,
                status,
            )
        remove_runtime_state(state_file, logger)

    return running


def dispatch_task(
    task: TaskInfo,
    tasksmith_dir: Path,
    workspace_root: Path,
    logs_dir: Path,
    runtime_dir: Path,
    args: argparse.Namespace,
    logger: logging.Logger,
) -> RunningDispatch:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    safe_task_id = task.task_id.replace("/", "_")
    stdout_log = logs_dir / f"{timestamp}-{safe_task_id}.stdout.log"
    stderr_log = logs_dir / f"{timestamp}-{safe_task_id}.stderr.log"
    state_file = runtime_dir / f"{safe_task_id}.json"

    prompt = build_processor_prompt(task.task_dir, tasksmith_dir)
    runner_bin = args.runner_bin or args.runner
    command = build_runner_command(
        runner=args.runner,
        runner_bin=runner_bin,
        workspace_root=workspace_root,
        prompt=prompt,
        codex_model=args.codex_model,
        claude_model=args.claude_model,
    )

    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_handle = stdout_log.open("w", encoding="utf-8")
    stderr_handle = stderr_log.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=workspace_root,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
    )

    dispatch = RunningDispatch(
        task_id=task.task_id,
        task_dir=task.task_dir,
        pid=process.pid,
        launched_at=now_iso(),
        state_file=state_file,
        stdout_log=stdout_log,
        stderr_log=stderr_log,
        process=process,
        stdout_handle=stdout_handle,
        stderr_handle=stderr_handle,
    )
    try:
        write_runtime_state(state_file, dispatch)
        note = (
            f"{DISPATCHER_NOTE_PREFIX} {now_iso()} dispatched to {args.runner} "
            "non-interactive processor."
        )
        update_task_status(task.task_dir, STATUS_RUNNING, note)
    except Exception:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        dispatch.close_handles()
        remove_runtime_state(state_file, logger)
        raise

    logger.info(
        "Dispatched task_id=%s pid=%s command=%s stdout=%s stderr=%s",
        task.task_id,
        process.pid,
        shlex.join(command),
        stdout_log,
        stderr_log,
    )
    return dispatch


def summarize_tasks(
    tasks: dict[str, TaskInfo],
    running: dict[str, RunningDispatch],
    tasks_root: Path,
) -> str:
    if not tasks:
        return "no tasks found"

    statuses: dict[str, int] = {}
    processable: list[str] = []
    waiting_blocked: list[str] = []
    for task in tasks.values():
        statuses[task.status] = statuses.get(task.status, 0) + 1
        if task.task_id in running:
            continue
        if is_processable(task, tasks, tasks_root):
            processable.append(task.task_id)
        elif task.status == STATUS_WAITING:
            waiting_blocked.append(task.task_id)

    status_summary = ", ".join(f"{name}:{count}" for name, count in sorted(statuses.items()))
    return (
        f"status_summary=[{status_summary}] "
        f"running={sorted(running)} "
        f"processable={processable} "
        f"waiting_blocked={waiting_blocked}"
    )


def finalize_dispatch(
    dispatch: RunningDispatch,
    return_code: int | None,
    logger: logging.Logger,
) -> None:
    remove_runtime_state(dispatch.state_file, logger)
    dispatch.close_handles()

    current_status = read_status(dispatch.task_dir / STATUS_FILE)
    if current_status == STATUS_RUNNING:
        note = (
            f"{DISPATCHER_NOTE_PREFIX} {now_iso()} processor exited "
            f"rc={return_code} without terminal task state; status moved to 보류."
        )
        update_task_status(dispatch.task_dir, STATUS_HOLD, note)
        current_status = STATUS_HOLD

    logger.info(
        "Dispatch finished task_id=%s pid=%s rc=%s current_status=%s stdout=%s stderr=%s",
        dispatch.task_id,
        dispatch.pid,
        return_code,
        current_status,
        dispatch.stdout_log,
        dispatch.stderr_log,
    )


def poll_running_dispatches(
    running: dict[str, RunningDispatch],
    logger: logging.Logger,
) -> bool:
    changed = False
    finished_ids: list[str] = []

    for task_id, dispatch in running.items():
        if dispatch.process is not None:
            return_code = dispatch.process.poll()
            if return_code is None:
                continue
            finalize_dispatch(dispatch, return_code, logger)
            finished_ids.append(task_id)
            changed = True
            continue

        if is_pid_alive(dispatch.pid):
            continue

        finalize_dispatch(dispatch, None, logger)
        finished_ids.append(task_id)
        changed = True

    for task_id in finished_ids:
        running.pop(task_id, None)

    return changed


def all_tasks_complete(tasks: dict[str, TaskInfo]) -> bool:
    return bool(tasks) and all(task.status == STATUS_DONE for task in tasks.values())


def install_signal_handlers(logger: logging.Logger) -> dict[str, bool]:
    state = {"stop": False}

    def handler(signum: int, _frame: object) -> None:
        state["stop"] = True
        logger.warning("Received signal=%s, stopping dispatcher loop.", signum)

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    return state


def main() -> int:
    args = parse_args()

    try:
        tasksmith_dir = normalize_tasksmith_dir(args.tasksmith_dir)
    except DispatcherError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    workspace_root = tasksmith_dir.parent.resolve()
    tasks_root = tasksmith_dir / "tasks"
    logs_root = tasksmith_dir / "logs"
    runtime_dir = tasksmith_dir / "runtime" / "dispatcher"
    dispatch_logs_dir = logs_root / "dispatcher-runs"
    log_file = Path(args.log_file).expanduser().resolve() if args.log_file else logs_root / "tasksmith-dispatcher.log"
    logger = configure_logging(log_file)

    logger.info(
        "Starting dispatcher tasksmith_dir=%s workspace_root=%s tasks_root=%s runner=%s",
        tasksmith_dir,
        workspace_root,
        tasks_root,
        args.runner,
    )

    if not tasks_root.exists():
        logger.warning("tasks directory does not exist yet: %s", tasks_root)

    running = recover_previous_dispatches(runtime_dir, tasks_root, logger)
    signal_state = install_signal_handlers(logger)

    saw_any_tasks = False
    signature = ""
    force_scan = True
    last_idle_summary = ""

    while not signal_state["stop"]:
        if poll_running_dispatches(running, logger):
            force_scan = True

        next_signature = compute_tree_signature(tasks_root)
        if force_scan or next_signature != signature:
            signature = next_signature
            force_scan = False

            try:
                tasks = load_tasks(tasks_root)
            except DispatcherError as exc:
                logger.error("Failed to load tasks: %s", exc)
                time.sleep(args.poll_interval)
                continue

            if tasks:
                saw_any_tasks = True

            logger.info("Task scan: %s", summarize_tasks(tasks, running, tasks_root))

            for task in sorted(tasks.values(), key=lambda item: item.task_id):
                if task.task_id in running:
                    continue
                if not is_processable(task, tasks, tasks_root):
                    reasons = blocked_reasons(task, tasks, tasks_root)
                    logger.info(
                        "Task not dispatchable task_id=%s reasons=%s",
                        task.task_id,
                        "; ".join(reasons),
                    )
                    continue

                try:
                    running[task.task_id] = dispatch_task(
                        task=task,
                        tasksmith_dir=tasksmith_dir,
                        workspace_root=workspace_root,
                        logs_dir=dispatch_logs_dir,
                        runtime_dir=runtime_dir,
                        args=args,
                        logger=logger,
                    )
                    force_scan = True
                except OSError as exc:
                    note = (
                        f"{DISPATCHER_NOTE_PREFIX} {now_iso()} failed to start {args.runner}: {exc}. "
                        "status moved to 보류."
                    )
                    update_task_status(task.task_dir, STATUS_HOLD, note)
                    logger.exception("Failed to dispatch task_id=%s", task.task_id)
                    force_scan = True

            if all_tasks_complete(tasks) and not running and saw_any_tasks:
                logger.info("All observed tasks are 완료. Exiting dispatcher.")
                return 0

            if saw_any_tasks and not running and tasks and not all_tasks_complete(tasks):
                idle_summary = summarize_tasks(tasks, running, tasks_root)
                if idle_summary != last_idle_summary:
                    logger.warning(
                        "No runnable tasks right now; waiting for task changes. %s",
                        idle_summary,
                    )
                    last_idle_summary = idle_summary

        time.sleep(args.poll_interval)

    logger.warning("Dispatcher stopped before completion; running tasks were left untouched.")
    return 130


if __name__ == "__main__":
    raise SystemExit(main())
