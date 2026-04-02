#!/usr/bin/env python3
"""Run a deterministic Tasksmith processor loop with non-interactive worker/evaluator calls."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

from task_io import (
    build_processor_context,
    ensure_log_dir,
    find_task_dir,
    infer_tasksmith_root,
    normalize_tasks_root,
    parse_report,
    task_snapshot,
    unmet_signature,
    workspace_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch isolated worker/evaluator loops until one Tasksmith task reaches a terminal outcome.",
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
    parser.add_argument("--runner", choices=("codex", "claude"), default="codex")
    parser.add_argument("--runner-bin", help="Override the runner executable name.")
    parser.add_argument(
        "--worker-command",
        help="Command template for worker runs. Supports {task_id}, {task_dir}, {tasks_root}, {tasksmith_root}, {workspace_root}, {evaluation_report}, {prompt}.",
    )
    parser.add_argument(
        "--evaluator-command",
        help="Command template for evaluator runs. Supports {task_id}, {task_dir}, {tasks_root}, {tasksmith_root}, {workspace_root}, {evaluation_report}, {prompt}.",
    )
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def build_worker_prompt(context: dict[str, str]) -> str:
    lines = [
        "Use $tasksmith-worker to execute one Tasksmith task.",
        f"Task directory: {context['task_dir']}",
        f"Tasksmith root: {context['tasksmith_root']}",
        f"Tasks root: {context['tasks_root']}",
        f"Repository root: {context['workspace_root']}",
    ]
    if Path(context["evaluation_report"]).exists():
        lines.append(f"Latest evaluator feedback: {context['evaluation_report']}")
        lines.append("Address only the concrete unmet items in that evaluation report.")
    lines.append("Run in a fresh non-interactive session. Do not use spawn_agent.")
    return "\n".join(lines)


def build_evaluator_prompt(context: dict[str, str]) -> str:
    return "\n".join(
        [
            "Use $tasksmith-evaluator to evaluate one Tasksmith task.",
            f"Task directory: {context['task_dir']}",
            f"Tasksmith root: {context['tasksmith_root']}",
            f"Tasks root: {context['tasks_root']}",
            f"Repository root: {context['workspace_root']}",
            "Run in a fresh non-interactive session. Do not use spawn_agent.",
        ]
    )


def build_preset_command(runner: str, runner_bin: str, workspace_root: Path, prompt: str) -> list[str]:
    if runner == "codex":
        return [
            runner_bin,
            "exec",
            "--skip-git-repo-check",
            "--full-auto",
            "--ephemeral",
            "--color",
            "never",
            "-C",
            str(workspace_root),
            prompt,
        ]
    return [runner_bin, "-p", prompt]


def build_command(
    template: str | None,
    runner: str,
    runner_bin: str,
    workspace_root: Path,
    prompt: str,
    context: dict[str, str],
) -> list[str]:
    if not template:
        return build_preset_command(runner, runner_bin, workspace_root, prompt)

    values = {key: shell_quote(value) for key, value in context.items()}
    values["prompt"] = shell_quote(prompt)
    return shlex.split(template.format(**values))


def log_step(
    log_dir: Path,
    attempt: int,
    step_name: str,
    command: list[str],
    completed: subprocess.CompletedProcess[str],
) -> None:
    prefix = log_dir / f"attempt-{attempt:03d}.{step_name}"
    prefix.with_suffix(".command.txt").write_text(
        " ".join(shell_quote(part) for part in command) + "\n",
        encoding="utf-8",
    )
    prefix.with_suffix(".stdout.log").write_text(completed.stdout, encoding="utf-8")
    prefix.with_suffix(".stderr.log").write_text(completed.stderr, encoding="utf-8")


def run_step(
    log_dir: Path,
    attempt: int,
    step_name: str,
    command: list[str],
    workspace_root: Path,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=workspace_root,
        capture_output=True,
        text=True,
        check=False,
    )
    log_step(log_dir, attempt, step_name, command, completed)
    return completed


def summarize_result(result: dict[str, object]) -> str:
    return (
        "Processor Result\n"
        f"- Task: {result['task_id']}\n"
        f"- Final Verdict: {result['final_verdict']}\n"
        f"- Worker Attempts: {result['worker_attempts']}\n"
        f"- Last Evaluation: {result['evaluation_report']}\n\n"
        "Next Action\n"
        f"- {result['next_action']}\n"
    )


def main() -> int:
    args = parse_args()
    workspace_root = Path(args.workspace_root).expanduser().resolve() if args.workspace_root else Path.cwd().resolve()

    try:
        tasks_root = normalize_tasks_root(args.root)
        task_dir = find_task_dir(tasks_root, args.task)
    except (FileNotFoundError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    tasksmith_root = infer_tasksmith_root(tasks_root)
    context_result = build_processor_context(task_dir, tasks_root, workspace_root)
    task_id = str(context_result["task_id"])
    log_dir = ensure_log_dir(tasksmith_root, task_id)
    runner_bin = args.runner_bin or args.runner

    history: list[dict[str, object]] = []
    previous_unmet_sig: str | None = None
    previous_after_snapshot: tuple[str, str] | None = None
    final_verdict = "차단됨"
    next_action = "Review the latest processor logs."

    for attempt in range(1, args.max_attempts + 1):
        before_task = task_snapshot(task_dir)
        before_workspace = workspace_snapshot(workspace_root)
        context = {
            "task_id": task_id,
            "task_dir": str(task_dir),
            "tasks_root": str(tasks_root),
            "tasksmith_root": str(tasksmith_root),
            "workspace_root": str(workspace_root),
            "evaluation_report": str(task_dir / "평가결과.md"),
        }

        worker_command = build_command(
            args.worker_command,
            args.runner,
            runner_bin,
            workspace_root,
            build_worker_prompt(context),
            context,
        )
        worker_run = run_step(log_dir, attempt, "worker", worker_command, workspace_root)
        if worker_run.returncode != 0:
            final_verdict = "차단됨"
            next_action = f"Worker runner failed with exit code {worker_run.returncode}. See {log_dir}."
            history.append({"attempt": attempt, "verdict": final_verdict, "changed": False})
            break

        evaluator_command = build_command(
            args.evaluator_command,
            args.runner,
            runner_bin,
            workspace_root,
            build_evaluator_prompt(context),
            context,
        )
        evaluator_run = run_step(log_dir, attempt, "evaluator", evaluator_command, workspace_root)
        if evaluator_run.returncode != 0:
            final_verdict = "차단됨"
            next_action = f"Evaluator runner failed with exit code {evaluator_run.returncode}. See {log_dir}."
            history.append({"attempt": attempt, "verdict": final_verdict, "changed": False})
            break

        report = parse_report(task_dir / "평가결과.md")
        verdict = str(report["verdict"])
        unmet_items = [str(item) for item in report["unmet_items"]]
        unmet_sig = unmet_signature(unmet_items)
        after_task = task_snapshot(task_dir)
        after_workspace = workspace_snapshot(workspace_root)
        changed = before_task != after_task or before_workspace != after_workspace

        history.append(
            {
                "attempt": attempt,
                "worker_exit_code": worker_run.returncode,
                "evaluator_exit_code": evaluator_run.returncode,
                "verdict": verdict,
                "unmet_items": unmet_items,
                "changed": changed,
            }
        )

        if verdict == "통과":
            final_verdict = verdict
            next_action = "No further processor action required."
            break

        if verdict == "차단됨":
            final_verdict = verdict
            next_action = str(report["next_action"]).strip() or "Resolve the reported blocker before retrying."
            break

        repeated_reason = previous_unmet_sig == unmet_sig
        repeated_snapshot = previous_after_snapshot == (after_task, after_workspace)
        if verdict == "수정필요" and repeated_reason and repeated_snapshot:
            final_verdict = "차단됨"
            next_action = "Processor loop stalled because the same unmet item repeated without material change."
            break

        previous_unmet_sig = unmet_sig
        previous_after_snapshot = (after_task, after_workspace)
        final_verdict = verdict
        next_action = str(report["next_action"]).strip() or "Run another worker attempt with the latest evaluation feedback."
    else:
        final_verdict = "차단됨"
        next_action = f"Stopped after reaching the max attempt limit ({args.max_attempts})."

    result = {
        "task_id": task_id,
        "task_dir": str(task_dir),
        "final_verdict": final_verdict,
        "worker_attempts": len(history),
        "evaluation_report": str(task_dir / "평가결과.md"),
        "next_action": next_action,
        "history": history,
        "log_dir": str(log_dir),
    }
    if args.json:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(summarize_result(result))
    return 0 if final_verdict == "통과" else 1


if __name__ == "__main__":
    raise SystemExit(main())
