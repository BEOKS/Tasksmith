#!/usr/bin/env python3
"""Evaluate one Tasksmith DAG node result in a fresh isolated agent session."""

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

EVALUATION_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
    "required": [
        "node_id",
        "verdict",
        "summary",
        "satisfied_criteria",
        "deficiencies",
        "improvement_actions",
        "evidence",
        "confidence",
    ],
    "properties": {
        "node_id": {"type": "string", "minLength": 1},
        "verdict": {"type": "string", "enum": ["pass", "needs_revision"]},
        "summary": {"type": "string", "minLength": 1},
        "satisfied_criteria": {"type": "array", "items": {"type": "string"}},
        "deficiencies": {"type": "array", "items": {"type": "string"}},
        "improvement_actions": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate one Tasksmith DAG node result in a fresh isolated agent session."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--dag-file", type=Path, help="Path to the authoritative DAG JSON file.")
    source_group.add_argument("--node-file", type=Path, help="Path to a standalone node JSON file.")
    parser.add_argument("--node-id", help="Node id to evaluate when using --dag-file.")
    parser.add_argument("--worker-result", type=Path, required=True, help="Path to worker result.json.")
    parser.add_argument("--worker-execution", type=Path, help="Optional path to worker execution.json.")
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Workspace root for resolving paths.")
    parser.add_argument(
        "--results-dir",
        type=Path,
        help="Directory for evaluator artifacts. Defaults to <cwd>/.tasksmith/evaluator-runs.",
    )
    parser.add_argument(
        "--provider",
        default="auto",
        help="Provider passed through to tasksmith-exec. Defaults to auto.",
    )
    parser.add_argument("--model", help="Optional model name passed through to tasksmith-exec.")
    parser.add_argument(
        "--attempt",
        type=int,
        help="Override the attempt number. Defaults to the worker attempt when present, else next available.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare artifacts and print the resolved isolated command without executing it.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the normalized evaluation JSON to stdout.",
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
        node = load_json(args.node_file)
    else:
        if not args.node_id:
            raise SystemExit("--node-id is required when using --dag-file.")
        dag = load_json(args.dag_file)
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


def next_attempt(node_dir: Path) -> int:
    attempts = []
    for child in node_dir.iterdir() if node_dir.exists() else []:
        match = re.fullmatch(r"attempt-(\d{3})", child.name)
        if match:
            attempts.append(int(match.group(1)))
    return max(attempts, default=0) + 1


def normalize_paths(paths: list[Any], cwd: Path) -> list[str]:
    normalized: list[str] = []
    for item in paths:
        if not isinstance(item, str):
            continue
        path = Path(item).expanduser()
        if not path.is_absolute():
            path = (cwd / path).resolve()
        normalized.append(str(path))
    return normalized


def infer_worker_execution_path(result: dict[str, Any], explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    raw_ref = result.get("raw_execution_ref")
    if isinstance(raw_ref, str) and raw_ref.strip():
        return Path(raw_ref)
    raise SystemExit("--worker-execution is required when worker result lacks raw_execution_ref.")


def build_brief(
    node: dict[str, Any],
    worker_result: dict[str, Any],
    worker_execution_path: Path,
    worker_attempt_dir: Path,
    evidence_paths: list[str],
) -> str:
    stdout_path = worker_attempt_dir / "stdout.txt"
    stderr_path = worker_attempt_dir / "stderr.txt"

    lines = [
        "Role: Tasksmith node evaluator",
        f"Node ID: {node['id']}",
        f"Goal: {node['goal']}",
        "Constraints:",
    ]
    if node["constraints"]:
        lines.extend(f"- {item}" for item in node["constraints"])
    else:
        lines.append("- None")

    lines.append("Success Criteria:")
    if node["success_criteria"]:
        lines.extend(f"- {item}" for item in node["success_criteria"])
    else:
        lines.append("- Complete the goal faithfully.")

    lines.append("Output Contract:")
    if node["output_contract"]:
        lines.extend(f"- {item}" for item in node["output_contract"])
    else:
        lines.append("- Return a concise summary of work completed.")

    lines.extend(
        [
            "Worker Evidence:",
            f"- Worker status: {worker_result.get('status', 'unknown')}",
            f"- Worker summary: {worker_result.get('result_summary', '')}",
            "- Output artifacts:",
        ]
    )
    if evidence_paths:
        lines.extend(f"  - {path}" for path in evidence_paths)
    else:
        lines.append("  - None")

    lines.extend(
        [
            "- Supporting files:",
            f"  - {worker_execution_path}",
            f"  - {stdout_path}",
            f"  - {stderr_path}",
            "Evaluation Task:",
            "- Inspect the listed artifacts directly before judging.",
            "- Return `pass` only if the node goal, success criteria, and output contract are truly satisfied.",
            "- Return `needs_revision` if anything important is missing, weak, incorrect, or unverifiable.",
            "- Be strict about substantive completion, not just file existence.",
            "Output Format:",
            "- Return a JSON object with keys node_id, verdict, summary, satisfied_criteria, deficiencies, improvement_actions, evidence, confidence.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def emit_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return
    print(f"{result['node_id']} {result['verdict']}")
    print(result["summary"])


def parse_evaluation_payload(stdout: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Evaluator returned non-JSON output: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Evaluator returned a non-object JSON value.")
    return payload


def main() -> int:
    args = parse_args()
    cwd = args.cwd.resolve()
    node = load_node(args)
    worker_result = load_json(args.worker_result.resolve())
    worker_execution_path = infer_worker_execution_path(worker_result, args.worker_execution)
    if not worker_execution_path.is_absolute():
        worker_execution_path = (cwd / worker_execution_path).resolve()
    worker_attempt_dir = worker_execution_path.parent

    results_dir = (args.results_dir or (cwd / ".tasksmith" / "evaluator-runs")).resolve()
    node_dir = results_dir / node["id"]
    worker_attempt = worker_result.get("attempt")
    attempt = args.attempt if args.attempt is not None else (
        worker_attempt if isinstance(worker_attempt, int) and worker_attempt > 0 else next_attempt(node_dir)
    )
    if attempt < 1:
        raise SystemExit("--attempt must be >= 1")
    attempt_dir = node_dir / f"attempt-{attempt:03d}"
    attempt_dir.mkdir(parents=True, exist_ok=False)

    brief_path = attempt_dir / "brief.txt"
    stdout_path = attempt_dir / "stdout.txt"
    stderr_path = attempt_dir / "stderr.txt"
    execution_path = attempt_dir / "execution.json"
    evaluation_path = attempt_dir / "evaluation.json"

    evidence_paths = normalize_paths(worker_result.get("output_paths", []), cwd)
    brief = build_brief(node, worker_result, worker_execution_path, worker_attempt_dir, evidence_paths)
    brief_path.write_text(brief, encoding="utf-8")

    exec_script = Path(__file__).resolve().parents[2] / "tasksmith-exec" / "scripts" / "run_isolated_agent.py"
    if not exec_script.exists():
        raise SystemExit(f"tasksmith-exec runner not found: {exec_script}")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        schema_path = Path(handle.name)
        json.dump(EVALUATION_SCHEMA, handle, ensure_ascii=True, indent=2)

    try:
        command = [
            sys.executable,
            str(exec_script),
            "--provider",
            args.provider,
            "--cwd",
            str(cwd),
            "--prompt-file",
            str(brief_path),
            "--schema-file",
            str(schema_path),
            "--capture-output",
            str(stdout_path),
            "--capture-error",
            str(stderr_path),
            "--json",
        ]
        if args.model:
            command.extend(["--model", args.model])
        if args.dry_run:
            command.append("--dry-run")

        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        schema_path.unlink(missing_ok=True)

    if completed.stdout.strip():
        try:
            execution = json.loads(completed.stdout)
        except json.JSONDecodeError:
            execution = {
                "provider": "unknown",
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
    else:
        execution = {
            "provider": "unknown",
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    if completed.stderr and not stderr_path.exists():
        stderr_path.write_text(completed.stderr, encoding="utf-8")
    if not stdout_path.exists():
        stdout_path.write_text(execution.get("stdout", ""), encoding="utf-8")
    write_json(execution_path, execution)

    if args.dry_run:
        evaluation = {
            "node_id": node["id"],
            "verdict": "pass" if completed.returncode == 0 else "needs_revision",
            "summary": "Prepared isolated evaluation command without running the provider.",
            "satisfied_criteria": [],
            "deficiencies": [] if completed.returncode == 0 else ["Dry-run command generation failed."],
            "improvement_actions": [],
            "evidence": evidence_paths,
            "confidence": 1.0 if completed.returncode == 0 else 0.0,
            "provider": execution.get("provider", "unknown"),
            "attempt": attempt,
            "status": "dry_run",
            "raw_execution_ref": str(execution_path),
        }
        write_json(evaluation_path, evaluation)
        emit_result(evaluation, args.json)
        return 0 if completed.returncode == 0 else 1

    if completed.returncode != 0:
        evaluation = {
            "node_id": node["id"],
            "verdict": "needs_revision",
            "summary": "Evaluator execution failed before a valid judgment was produced.",
            "satisfied_criteria": [],
            "deficiencies": [execution.get("stderr", "").strip() or "Evaluator run exited non-zero."],
            "improvement_actions": ["Re-run evaluation after inspecting the evaluator stderr and provider output."],
            "evidence": evidence_paths,
            "confidence": 0.0,
            "provider": execution.get("provider", "unknown"),
            "attempt": attempt,
            "status": "failed",
            "raw_execution_ref": str(execution_path),
        }
        write_json(evaluation_path, evaluation)
        emit_result(evaluation, args.json)
        return 1

    evaluation_payload = parse_evaluation_payload(execution.get("stdout", ""))
    evaluation = {
        "node_id": evaluation_payload.get("node_id", node["id"]),
        "verdict": evaluation_payload.get("verdict", "needs_revision"),
        "summary": evaluation_payload.get("summary", "No evaluation summary returned."),
        "satisfied_criteria": evaluation_payload.get("satisfied_criteria", []),
        "deficiencies": evaluation_payload.get("deficiencies", []),
        "improvement_actions": evaluation_payload.get("improvement_actions", []),
        "evidence": evaluation_payload.get("evidence", evidence_paths),
        "confidence": evaluation_payload.get("confidence", 0.0),
        "provider": execution.get("provider", "unknown"),
        "attempt": attempt,
        "status": "success",
        "raw_execution_ref": str(execution_path),
    }
    write_json(evaluation_path, evaluation)
    emit_result(evaluation, args.json)
    return 0 if evaluation["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
