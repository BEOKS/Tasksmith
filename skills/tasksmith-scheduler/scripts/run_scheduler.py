#!/usr/bin/env python3
"""Schedule and dispatch ready Tasksmith DAG nodes through tasksmith-loop."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUNNABLE_STATUSES = {"pending"}
SUCCESS_STATUSES = {"success"}
TERMINAL_FAILURE_STATUSES = {"failed", "blocked", "skipped"}
NON_TERMINAL_STATUSES = {"pending", "running", "needs_revision"}
ALL_TERMINAL_STATUSES = SUCCESS_STATUSES | TERMINAL_FAILURE_STATUSES


@dataclass
class DispatchResult:
    node_id: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    loop_summary: dict[str, Any] | None
    loop_summary_ref: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Schedule and dispatch ready Tasksmith DAG nodes through tasksmith-loop."
    )
    parser.add_argument("--dag-file", type=Path, required=True, help="Path to the authoritative DAG JSON file.")
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Workspace root used for path resolution.")
    parser.add_argument(
        "--results-dir",
        type=Path,
        help="Directory for scheduler artifacts. Defaults to <cwd>/tasksmith/scheduler-runs.",
    )
    parser.add_argument(
        "--loop-results-dir",
        type=Path,
        help="Directory for loop artifacts. Defaults to <cwd>/tasksmith/loop-runs.",
    )
    parser.add_argument(
        "--worker-results-dir",
        type=Path,
        help="Directory for worker artifacts. Defaults to <cwd>/tasksmith/worker-runs.",
    )
    parser.add_argument(
        "--evaluation-results-dir",
        type=Path,
        help="Directory for evaluator artifacts. Defaults to <cwd>/tasksmith/evaluator-runs.",
    )
    parser.add_argument("--provider", default="auto", help="Provider passed through to tasksmith-loop.")
    parser.add_argument("--model", help="Optional model name passed through to tasksmith-loop.")
    parser.add_argument(
        "--evaluation-provider",
        default="auto",
        help="Provider passed through to tasksmith-evaluator via tasksmith-loop.",
    )
    parser.add_argument("--evaluation-model", help="Optional model name for tasksmith-evaluator.")
    parser.add_argument(
        "--schema-file",
        type=Path,
        help="Optional JSON schema passed through to tasksmith-loop and then tasksmith-worker.",
    )
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=2,
        help="Maximum number of ready nodes to dispatch per wave. Defaults to 2.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume scheduling without resetting node statuses. Running nodes are treated as pending.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare only the first wave and print the resolved dispatch plan without executing loops.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the scheduler summary JSON to stdout.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"JSON root in {path} must be an object")
    return data


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def dag_nodes(dag: dict[str, Any]) -> dict[str, dict[str, Any]]:
    nodes = dag.get("nodes")
    if not isinstance(nodes, dict):
        raise SystemExit("DAG JSON must contain an object field named 'nodes'.")
    normalized: dict[str, dict[str, Any]] = {}
    for node_id, node in nodes.items():
        if not isinstance(node_id, str) or not node_id:
            raise SystemExit(f"Invalid DAG node id: {node_id!r}")
        if not isinstance(node, dict):
            raise SystemExit(f"Node {node_id} must be a JSON object.")
        normalized[node_id] = node
    return normalized


def effective_status(node: dict[str, Any]) -> str:
    status = node.get("status")
    if not isinstance(status, str) or not status.strip():
        return "pending"
    return status


def validate_dependencies(nodes: dict[str, dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    for node_id, node in nodes.items():
        depends_on = node.get("depends_on", [])
        if not isinstance(depends_on, list):
            problems.append(f"{node_id} has a non-list depends_on field.")
            continue
        for dep in depends_on:
            if not isinstance(dep, str):
                problems.append(f"{node_id} has a non-string dependency reference: {dep!r}")
                continue
            if dep not in nodes:
                problems.append(f"{node_id} depends on missing node {dep}.")
            elif dep == node_id:
                problems.append(f"{node_id} cannot depend on itself.")
    return problems


def next_run_number(base_dir: Path) -> int:
    runs = []
    for child in base_dir.iterdir() if base_dir.exists() else []:
        match = re.fullmatch(r"run-(\d{3})", child.name)
        if match:
            runs.append(int(match.group(1)))
    return max(runs, default=0) + 1


def patch_node(dag_file: Path, node_id: str, patch: dict[str, Any]) -> None:
    manager = Path(__file__).resolve().parents[2] / "tasksmith-dag" / "scripts" / "manage_dag.py"
    if not manager.exists():
        raise SystemExit(f"tasksmith-dag manager not found: {manager}")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        patch_path = Path(handle.name)
        json.dump(patch, handle, ensure_ascii=True, indent=2)

    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(manager),
                "--dag-file",
                str(dag_file),
                "update-node",
                "--node-id",
                node_id,
                "--patch-file",
                str(patch_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        patch_path.unlink(missing_ok=True)

    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip()
        raise SystemExit(f"Failed to update node {node_id} through manage_dag.py: {stderr}")


def ready_nodes(nodes: dict[str, dict[str, Any]]) -> list[str]:
    ready: list[str] = []
    for node_id in sorted(nodes):
        node = nodes[node_id]
        status = effective_status(node)
        if status == "running":
            continue
        if status not in RUNNABLE_STATUSES:
            continue
        depends_on = node.get("depends_on", [])
        if not isinstance(depends_on, list):
            continue
        if all(effective_status(nodes[dep]) in SUCCESS_STATUSES for dep in depends_on):
            ready.append(node_id)
    return ready


def unresolved_nodes(nodes: dict[str, dict[str, Any]]) -> list[str]:
    return [node_id for node_id in sorted(nodes) if effective_status(nodes[node_id]) not in ALL_TERMINAL_STATUSES]


def blocked_by_failures(nodes: dict[str, dict[str, Any]], node_id: str) -> bool:
    depends_on = nodes[node_id].get("depends_on", [])
    return any(effective_status(nodes[dep]) in TERMINAL_FAILURE_STATUSES for dep in depends_on)


def build_loop_command(args: argparse.Namespace, node_id: str, cwd: Path) -> list[str]:
    loop_script = Path(__file__).resolve().parents[2] / "tasksmith-loop" / "scripts" / "run_loop.py"
    if not loop_script.exists():
        raise SystemExit(f"tasksmith-loop runner not found: {loop_script}")

    command = [
        sys.executable,
        str(loop_script),
        "--dag-file",
        str(args.dag_file.resolve()),
        "--node-id",
        node_id,
        "--cwd",
        str(cwd),
        "--results-dir",
        str((args.loop_results_dir or (cwd / "tasksmith" / "loop-runs")).resolve()),
        "--worker-results-dir",
        str((args.worker_results_dir or (cwd / "tasksmith" / "worker-runs")).resolve()),
        "--evaluation-results-dir",
        str((args.evaluation_results_dir or (cwd / "tasksmith" / "evaluator-runs")).resolve()),
        "--provider",
        args.provider,
        "--evaluation-provider",
        args.evaluation_provider,
        "--json",
    ]
    if args.model:
        command.extend(["--model", args.model])
    if args.evaluation_model:
        command.extend(["--evaluation-model", args.evaluation_model])
    if args.schema_file:
        command.extend(["--schema-file", str(args.schema_file.resolve())])
    if args.dry_run:
        command.append("--dry-run")
    return command


def dispatch_wave(args: argparse.Namespace, node_ids: list[str], cwd: Path) -> list[DispatchResult]:
    procs: list[tuple[str, list[str], subprocess.Popen[str]]] = []
    for node_id in node_ids:
        command = build_loop_command(args, node_id, cwd)
        proc = subprocess.Popen(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        procs.append((node_id, command, proc))

    results: list[DispatchResult] = []
    for node_id, command, proc in procs:
        stdout, stderr = proc.communicate()
        summary = None
        summary_ref = None
        if stdout.strip():
            try:
                parsed = json.loads(stdout)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                summary = parsed
                raw_ref = parsed.get("summary_ref")
                if isinstance(raw_ref, str) and raw_ref.strip():
                    summary_ref = raw_ref
        results.append(
            DispatchResult(
                node_id=node_id,
                command=command,
                returncode=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                loop_summary=summary,
                loop_summary_ref=summary_ref,
            )
        )
    return results


def scheduler_stop_state(nodes: dict[str, dict[str, Any]]) -> tuple[str, str]:
    unresolved = unresolved_nodes(nodes)
    if not unresolved:
        failed = [node_id for node_id in sorted(nodes) if effective_status(nodes[node_id]) in TERMINAL_FAILURE_STATUSES]
        if failed:
            return (
                "blocked",
                f"All nodes are terminal, but some ended non-successfully: {', '.join(failed)}.",
            )
        return ("success", "All DAG nodes completed successfully.")

    blocked = [node_id for node_id in unresolved if blocked_by_failures(nodes, node_id)]
    if len(blocked) == len(unresolved):
        return (
            "blocked",
            "No ready nodes remain because all unresolved nodes depend on terminal upstream failures.",
        )
    return (
        "deadlock",
        "No ready nodes remain while unresolved nodes still exist. Check dependency cycles, invalid statuses, or incomplete failure propagation.",
    )


def normalize_running_nodes_for_resume(dag_file: Path, nodes: dict[str, dict[str, Any]]) -> None:
    for node_id, node in nodes.items():
        if effective_status(node) == "running":
            patch_node(dag_file, node_id, {"status": "pending"})


def emit_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return
    print(f"{result['run_status']} waves={len(result['waves'])}")
    print(result["stop_reason"])


def main() -> int:
    args = parse_args()
    if args.max_parallel < 1:
        raise SystemExit("--max-parallel must be >= 1")

    cwd = args.cwd.resolve()
    dag_file = args.dag_file.resolve()
    if not dag_file.exists():
        raise SystemExit(f"DAG file not found: {dag_file}")

    results_dir = (args.results_dir or (cwd / "tasksmith" / "scheduler-runs")).resolve()
    run_number = next_run_number(results_dir)
    run_dir = results_dir / f"run-{run_number:03d}"
    run_dir.mkdir(parents=True, exist_ok=False)
    summary_path = run_dir / "summary.json"

    initial_dag = load_json(dag_file)
    nodes = dag_nodes(initial_dag)
    problems = validate_dependencies(nodes)
    if problems:
        summary = {
            "dag_file": str(dag_file),
            "run_number": run_number,
            "run_status": "failed",
            "stop_reason": "DAG validation failed before scheduling.",
            "max_parallel": args.max_parallel,
            "problems": problems,
            "waves": [],
            "summary_ref": str(summary_path),
        }
        write_json(summary_path, summary)
        emit_result(summary, args.json)
        return 1

    if args.resume:
        normalize_running_nodes_for_resume(dag_file, nodes)
        nodes = dag_nodes(load_json(dag_file))

    waves: list[dict[str, Any]] = []

    while True:
        current_nodes = dag_nodes(load_json(dag_file))
        ready = ready_nodes(current_nodes)
        if not ready:
            run_status, stop_reason = scheduler_stop_state(current_nodes)
            summary = {
                "dag_file": str(dag_file),
                "run_number": run_number,
                "run_status": run_status,
                "stop_reason": stop_reason,
                "max_parallel": args.max_parallel,
                "waves": waves,
                "summary_ref": str(summary_path),
            }
            write_json(summary_path, summary)
            emit_result(summary, args.json)
            return 0 if run_status == "success" else 1

        wave_nodes = ready[: args.max_parallel]
        wave_number = len(waves) + 1
        wave_record: dict[str, Any] = {
            "wave": wave_number,
            "ready_nodes": ready,
            "dispatched_nodes": wave_nodes,
            "results": [],
        }

        if args.dry_run:
            for node_id in wave_nodes:
                wave_record["results"].append(
                    {
                        "node_id": node_id,
                        "planned_command": build_loop_command(args, node_id, cwd),
                        "planned_status_update": {
                            "status": "running",
                            "last_scheduler_run": run_number,
                            "last_scheduler_wave": wave_number,
                        },
                    }
                )
            waves.append(wave_record)
            summary = {
                "dag_file": str(dag_file),
                "run_number": run_number,
                "run_status": "dry_run",
                "stop_reason": "Prepared the first scheduler wave without executing tasksmith-loop.",
                "max_parallel": args.max_parallel,
                "waves": waves,
                "summary_ref": str(summary_path),
            }
            write_json(summary_path, summary)
            emit_result(summary, args.json)
            return 0

        for node_id in wave_nodes:
            patch_node(
                dag_file,
                node_id,
                {
                    "status": "running",
                    "last_scheduler_run": run_number,
                    "last_scheduler_wave": wave_number,
                },
            )

        dispatch_results = dispatch_wave(args, wave_nodes, cwd)

        for result in dispatch_results:
            final_status = "failed"
            stop_reason = "Loop finished without a parsable summary."
            if result.loop_summary is not None:
                raw_status = result.loop_summary.get("final_status")
                if isinstance(raw_status, str) and raw_status.strip():
                    final_status = raw_status
                raw_reason = result.loop_summary.get("stop_reason")
                if isinstance(raw_reason, str) and raw_reason.strip():
                    stop_reason = raw_reason
            elif result.returncode == 0:
                final_status = "success"
                stop_reason = "Loop process exited successfully without a JSON summary."

            patch_node(
                dag_file,
                result.node_id,
                {
                    "status": final_status,
                    "last_scheduler_run": run_number,
                    "last_scheduler_wave": wave_number,
                    "last_loop_summary_ref": result.loop_summary_ref,
                    "last_loop_stop_reason": stop_reason,
                },
            )

            wave_record["results"].append(
                {
                    "node_id": result.node_id,
                    "command": result.command,
                    "returncode": result.returncode,
                    "final_status": final_status,
                    "stop_reason": stop_reason,
                    "loop_summary_ref": result.loop_summary_ref,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
            )

        waves.append(wave_record)


if __name__ == "__main__":
    raise SystemExit(main())
