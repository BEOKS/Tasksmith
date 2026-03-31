#!/usr/bin/env python3
"""Orchestrate repeated Tasksmith worker/evaluator attempts for one node."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = (
    "id",
    "goal",
    "inputs",
    "depends_on",
    "constraints",
    "success_criteria",
    "output_contract",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Tasksmith worker/evaluator loop for one node."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--dag-file", type=Path, help="Path to the authoritative DAG JSON file.")
    source_group.add_argument("--node-file", type=Path, help="Path to a standalone node JSON file.")
    parser.add_argument("--node-id", help="Node id to execute when using --dag-file.")
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Workspace root used for path resolution.")
    parser.add_argument(
        "--results-dir",
        type=Path,
        help="Directory for loop run artifacts. Defaults to <cwd>/tasksmith/loop-runs.",
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
    parser.add_argument("--provider", default="auto", help="Provider passed through to tasksmith-worker.")
    parser.add_argument("--model", help="Optional model name passed through to tasksmith-worker.")
    parser.add_argument(
        "--evaluation-provider",
        default="auto",
        help="Provider passed through to tasksmith-evaluator via tasksmith-worker.",
    )
    parser.add_argument("--evaluation-model", help="Optional model name for tasksmith-evaluator.")
    parser.add_argument(
        "--schema-file",
        type=Path,
        help="Optional JSON schema passed through to tasksmith-worker and then tasksmith-exec.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum number of worker attempts. Defaults to 3.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare the first worker attempt without executing provider calls.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the loop summary JSON to stdout.",
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


def load_node(args: argparse.Namespace) -> dict[str, Any]:
    if args.node_file:
        node = load_json(args.node_file.resolve())
    else:
        if not args.node_id:
            raise SystemExit("--node-id is required when using --dag-file.")
        dag = load_json(args.dag_file.resolve())
        nodes = dag.get("nodes")
        if not isinstance(nodes, dict):
            raise SystemExit("DAG JSON must contain an object field named 'nodes'.")
        try:
            node = nodes[args.node_id]
        except KeyError as exc:
            raise SystemExit(f"Node not found in DAG: {args.node_id}") from exc
        if not isinstance(node, dict):
            raise SystemExit(f"Node {args.node_id} must be a JSON object.")

    missing = [field for field in REQUIRED_FIELDS if field not in node]
    if missing:
        raise SystemExit(f"Node is missing required field(s): {', '.join(missing)}")
    return node


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def next_run(node_dir: Path) -> int:
    runs = []
    for child in node_dir.iterdir() if node_dir.exists() else []:
        match = re.fullmatch(r"run-(\d{3})", child.name)
        if match:
            runs.append(int(match.group(1)))
    return max(runs, default=0) + 1


def worker_result_path(base_dir: Path, node_id: str, attempt: int) -> Path:
    return base_dir / node_id / f"attempt-{attempt:03d}" / "result.json"


def run_worker_attempt(
    args: argparse.Namespace,
    node: dict[str, Any],
    cwd: Path,
    attempt: int,
    revision_file: Path | None,
) -> tuple[dict[str, Any], Path]:
    worker_script = Path(__file__).resolve().parents[2] / "tasksmith-worker" / "scripts" / "run_worker.py"
    if not worker_script.exists():
        raise SystemExit(f"tasksmith-worker runner not found: {worker_script}")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        temp_node_path = Path(handle.name)
        json.dump(node, handle, ensure_ascii=True, indent=2)

    command = [
        sys.executable,
        str(worker_script),
        "--node-file",
        str(temp_node_path),
        "--cwd",
        str(cwd),
        "--results-dir",
        str((args.worker_results_dir or (cwd / "tasksmith" / "worker-runs")).resolve()),
        "--evaluation-results-dir",
        str((args.evaluation_results_dir or (cwd / "tasksmith" / "evaluator-runs")).resolve()),
        "--provider",
        args.provider,
        "--evaluation-provider",
        args.evaluation_provider,
        "--attempt",
        str(attempt),
        "--json",
    ]
    if args.model:
        command.extend(["--model", args.model])
    if args.evaluation_model:
        command.extend(["--evaluation-model", args.evaluation_model])
    if args.schema_file:
        command.extend(["--schema-file", str(args.schema_file.resolve())])
    if revision_file is not None:
        command.extend(["--revision-file", str(revision_file.resolve())])
    if args.dry_run:
        command.append("--dry-run")

    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        temp_node_path.unlink(missing_ok=True)

    if not completed.stdout.strip():
        raise SystemExit("tasksmith-worker produced no JSON output.")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON from tasksmith-worker: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("tasksmith-worker returned a non-object JSON payload.")
    return payload, worker_result_path(
        (args.worker_results_dir or (cwd / "tasksmith" / "worker-runs")).resolve(),
        node["id"],
        attempt,
    )


def emit_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return
    print(f"{result['node_id']} {result['final_status']} attempts={len(result['attempts'])}")
    print(result["stop_reason"])


def main() -> int:
    args = parse_args()
    if args.max_attempts < 1:
        raise SystemExit("--max-attempts must be >= 1")

    cwd = args.cwd.resolve()
    node = load_node(args)
    results_dir = (args.results_dir or (cwd / "tasksmith" / "loop-runs")).resolve()
    node_dir = results_dir / node["id"]
    run_number = next_run(node_dir)
    run_dir = node_dir / f"run-{run_number:03d}"
    run_dir.mkdir(parents=True, exist_ok=False)
    summary_path = run_dir / "summary.json"

    attempts: list[dict[str, Any]] = []
    revision_file: Path | None = None
    final_status = "failed"
    stop_reason = "Loop ended unexpectedly."

    for attempt in range(1, args.max_attempts + 1):
        worker_result, worker_result_ref = run_worker_attempt(args, node, cwd, attempt, revision_file)
        attempt_record = {
            "attempt": attempt,
            "worker_status": worker_result.get("status"),
            "evaluation_verdict": worker_result.get("evaluation_verdict"),
            "result_summary": worker_result.get("result_summary"),
            "failure_reason": worker_result.get("failure_reason"),
            "worker_result_ref": str(worker_result_ref),
            "evaluation_ref": worker_result.get("evaluation_ref"),
            "revision_source_ref": worker_result.get("revision_source_ref"),
        }
        attempts.append(attempt_record)

        status = worker_result.get("status")
        if args.dry_run:
            final_status = status or "success"
            stop_reason = "Dry run completed after preparing the first isolated worker attempt."
            break
        if status == "success":
            final_status = "success"
            stop_reason = "Evaluator passed the node."
            break
        if status != "needs_revision":
            final_status = status or "failed"
            stop_reason = f"Loop stopped after worker returned terminal status '{final_status}'."
            break

        evaluation_ref = worker_result.get("evaluation_ref")
        if not isinstance(evaluation_ref, str) or not evaluation_ref.strip():
            final_status = "failed"
            stop_reason = "Worker requested revision but did not provide an evaluator artifact for the next attempt."
            break

        revision_file = Path(evaluation_ref)
        if not revision_file.is_absolute():
            revision_file = (cwd / revision_file).resolve()
        if not revision_file.exists():
            final_status = "failed"
            stop_reason = f"Expected evaluator artifact for revision attempt was not found: {revision_file}"
            break

        final_status = "needs_revision"
        stop_reason = "Evaluator requested another revision attempt."

    if attempts and attempts[-1]["worker_status"] == "needs_revision" and len(attempts) == args.max_attempts:
        stop_reason = "Reached max attempts while the evaluator still required revisions."

    summary = {
        "node_id": node["id"],
        "final_status": final_status,
        "stop_reason": stop_reason,
        "max_attempts": args.max_attempts,
        "run_number": run_number,
        "summary_ref": str(summary_path),
        "attempts": attempts,
    }
    write_json(summary_path, summary)
    emit_result(summary, args.json)
    return 0 if final_status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
