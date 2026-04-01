#!/usr/bin/env python3
"""Execute one Tasksmith DAG node through the isolated Tasksmith exec wrapper."""

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
        description="Execute one Tasksmith DAG node in a fresh isolated agent session."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--dag-file", type=Path, help="Path to the authoritative DAG JSON file.")
    source_group.add_argument("--node-file", type=Path, help="Path to a standalone node JSON file.")
    parser.add_argument("--node-id", help="Node id to execute when using --dag-file.")
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="Workspace root used for path resolution.")
    parser.add_argument(
        "--results-dir",
        type=Path,
        help="Directory for worker run artifacts. Defaults to <cwd>/.tasksmith/worker-runs.",
    )
    parser.add_argument(
        "--provider",
        default="auto",
        help="Provider passed through to tasksmith-exec. Defaults to auto.",
    )
    parser.add_argument("--model", help="Optional model name passed through to tasksmith-exec.")
    parser.add_argument(
        "--evaluation-provider",
        default="auto",
        help="Provider passed through to tasksmith-evaluator. Defaults to auto.",
    )
    parser.add_argument("--evaluation-model", help="Optional model name passed through to tasksmith-evaluator.")
    parser.add_argument(
        "--evaluation-results-dir",
        type=Path,
        help="Directory for evaluator artifacts. Defaults to <cwd>/.tasksmith/evaluator-runs.",
    )
    parser.add_argument(
        "--skip-evaluation",
        action="store_true",
        help="Skip the evaluator and base final status only on execution and output artifacts.",
    )
    parser.add_argument(
        "--schema-file",
        type=Path,
        help="Optional JSON schema passed through to tasksmith-exec.",
    )
    parser.add_argument(
        "--revision-file",
        type=Path,
        help="Optional evaluator JSON from a previous attempt to guide a revision attempt.",
    )
    parser.add_argument(
        "--attempt",
        type=int,
        help="Override the attempt number. Defaults to the next available attempt directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare artifacts and print the resolved isolated command without executing it.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the normalized result JSON to stdout.",
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

    for field in ("inputs", "depends_on", "constraints", "success_criteria", "output_contract"):
        if not isinstance(node[field], list):
            raise SystemExit(f"Node field '{field}' must be a list.")

    node_id = node["id"]
    if not isinstance(node_id, str) or not node_id.strip():
        raise SystemExit("Node field 'id' must be a non-empty string.")
    goal = node["goal"]
    if not isinstance(goal, str) or not goal.strip():
        raise SystemExit("Node field 'goal' must be a non-empty string.")
    return node


def is_dependency_reference(value: str) -> bool:
    return bool(re.match(r"^N\d+:[A-Za-z0-9_.-]+$", value))


def looks_like_path(value: str) -> bool:
    return "/" in value or value.startswith(".") or value.startswith("~") or bool(re.search(r"\.[A-Za-z0-9]+$", value))


def resolve_input_artifacts(node: dict[str, Any], cwd: Path) -> tuple[list[str], list[str], list[str]]:
    required_inputs: list[str] = []
    missing_inputs: list[str] = []
    warnings: list[str] = []

    for raw in node["inputs"]:
        if not isinstance(raw, str):
            warnings.append(f"Ignored non-string input entry: {raw!r}")
            continue
        if is_dependency_reference(raw):
            warnings.append(f"Dependency reference left unresolved for worker prompt: {raw}")
            required_inputs.append(raw)
            continue
        if looks_like_path(raw):
            resolved = Path(raw).expanduser()
            if not resolved.is_absolute():
                resolved = (cwd / resolved).resolve()
            required_inputs.append(str(resolved))
            if not resolved.exists():
                missing_inputs.append(str(resolved))
            continue
        required_inputs.append(raw)
        warnings.append(f"Input kept as literal context because it is not a clear file path: {raw}")

    return required_inputs, missing_inputs, warnings


def load_revision_payload(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = load_json(path.resolve())
    verdict = payload.get("verdict")
    if verdict != "needs_revision":
        raise SystemExit("--revision-file must point to an evaluator payload with verdict 'needs_revision'.")
    return payload


def resolve_execution_cwd(node: dict[str, Any], cwd: Path) -> Path:
    raw = node.get("working_directory")
    if raw is None:
        return cwd
    if not isinstance(raw, str) or not raw.strip():
        raise SystemExit("Node field 'working_directory' must be a non-empty string when present.")

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (cwd / path).resolve()
    else:
        path = path.resolve()

    if not path.exists():
        raise SystemExit(f"Node working_directory does not exist: {path}")
    if not path.is_dir():
        raise SystemExit(f"Node working_directory must be a directory: {path}")
    return path


def build_brief(
    node: dict[str, Any],
    required_inputs: list[str],
    revision_payload: dict[str, Any] | None = None,
) -> str:
    lines = [
        f"Node ID: {node['id']}",
        f"Goal: {node['goal']}",
        "Inputs:",
    ]
    if required_inputs:
        lines.extend(f"- {item}" for item in required_inputs)
    else:
        lines.append("- None")

    lines.append("Constraints:")
    if node["constraints"]:
        lines.extend(f"- {item}" for item in node["constraints"])
    else:
        lines.append("- None")

    allowed_tools = node.get("allowed_tools", [])
    if isinstance(allowed_tools, list):
        lines.append("Allowed Tools:")
        if allowed_tools:
            lines.extend(f"- {item}" for item in allowed_tools)
        else:
            lines.append("- Use only the tools implied by the node inputs and workspace.")

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

    if revision_payload is not None:
        lines.extend(
            [
                "Revision Context:",
                "- This is a revision attempt after an isolated evaluator requested changes.",
                f"- Prior evaluation summary: {revision_payload.get('summary', 'No summary provided.')}",
                "- Deficiencies:",
            ]
        )
        deficiencies = revision_payload.get("deficiencies", [])
        if isinstance(deficiencies, list) and deficiencies:
            lines.extend(f"- {item}" for item in deficiencies)
        else:
            lines.append("- None listed.")

        lines.append("Improvement Actions:")
        actions = revision_payload.get("improvement_actions", [])
        if isinstance(actions, list) and actions:
            lines.extend(f"- {item}" for item in actions)
        else:
            lines.append("- Address the evaluator feedback and satisfy the node contract.")

        lines.extend(
            [
                "Revision Requirements:",
                "- Inspect and update any existing node outputs as needed instead of starting from stale assumptions.",
                "- Satisfy the original node contract first; use the evaluator feedback as repair guidance.",
                "- Return only when the revised outputs are ready for another isolated evaluation pass.",
            ]
        )

    return "\n".join(lines) + "\n"


def next_attempt(node_dir: Path) -> int:
    attempts = []
    for child in node_dir.iterdir() if node_dir.exists() else []:
        match = re.fullmatch(r"attempt-(\d{3})", child.name)
        if match:
            attempts.append(int(match.group(1)))
    return max(attempts, default=0) + 1


def parse_output_paths(node: dict[str, Any], cwd: Path) -> list[str]:
    output_paths: list[str] = []
    for item in node["output_contract"]:
        if not isinstance(item, str):
            continue
        candidates = re.findall(r"`([^`]+)`", item)
        if not candidates:
            save_match = re.search(r"\b(?:Save|Write|Create)\s+([A-Za-z0-9_./-]+)", item)
            if save_match:
                candidates = [save_match.group(1)]
        for candidate in candidates:
            path = Path(candidate).expanduser()
            if not path.is_absolute():
                path = (cwd / path).resolve()
            output_paths.append(str(path))
    deduped: list[str] = []
    seen = set()
    for path in output_paths:
        if path not in seen:
            deduped.append(path)
            seen.add(path)
    return deduped


def summarize(stdout: str, stderr: str, fallback: str) -> str:
    for source in (stdout, stderr):
        for line in source.splitlines():
            cleaned = line.strip()
            if cleaned:
                return cleaned[:240]
    return fallback


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def normalize_evaluation_payload(payload: dict[str, Any], execution_path: Path) -> dict[str, Any]:
    return {
        "node_id": payload.get("node_id"),
        "verdict": payload.get("verdict"),
        "summary": payload.get("summary"),
        "satisfied_criteria": payload.get("satisfied_criteria", []),
        "deficiencies": payload.get("deficiencies", []),
        "improvement_actions": payload.get("improvement_actions", []),
        "evidence": payload.get("evidence", []),
        "confidence": payload.get("confidence"),
        "provider": payload.get("provider"),
        "attempt": payload.get("attempt"),
        "status": payload.get("status"),
        "raw_execution_ref": str(execution_path),
    }


def run_evaluator(
    args: argparse.Namespace,
    node: dict[str, Any],
    cwd: Path,
    result_path: Path,
    execution_path: Path,
    attempt: int,
) -> dict[str, Any]:
    evaluator_script = Path(__file__).resolve().parents[2] / "tasksmith-evaluator" / "scripts" / "run_evaluator.py"
    if not evaluator_script.exists():
        raise SystemExit(f"tasksmith-evaluator runner not found: {evaluator_script}")

    temp_node_path = write_temp_node(node)
    try:
        command = [
            sys.executable,
            str(evaluator_script),
            "--node-file",
            str(temp_node_path),
            "--worker-result",
            str(result_path),
            "--worker-execution",
            str(execution_path),
            "--cwd",
            str(cwd),
            "--results-dir",
            str((args.evaluation_results_dir or (cwd / ".tasksmith" / "evaluator-runs")).resolve()),
            "--provider",
            args.evaluation_provider,
            "--attempt",
            str(attempt),
            "--json",
        ]
        if args.evaluation_model:
            command.extend(["--model", args.evaluation_model])
        if args.dry_run:
            command.append("--dry-run")

        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        temp_node_path.unlink(missing_ok=True)

    if completed.stdout.strip():
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON from tasksmith-evaluator: {exc}") from exc
        if not isinstance(payload, dict):
            raise SystemExit("tasksmith-evaluator returned a non-object JSON payload.")
        return normalize_evaluation_payload(payload, Path(payload.get("raw_execution_ref", execution_path)))

    if completed.returncode != 0:
        return {
            "node_id": node["id"],
            "verdict": "needs_revision",
            "summary": "Evaluator failed before producing a judgment.",
            "satisfied_criteria": [],
            "deficiencies": [completed.stderr.strip() or "Evaluator exited non-zero without JSON output."],
            "improvement_actions": ["Inspect evaluator stderr and retry the evaluation."],
            "evidence": [],
            "confidence": 0.0,
            "provider": "unknown",
            "attempt": attempt,
            "status": "failed",
            "raw_execution_ref": str(execution_path),
        }
    raise SystemExit("tasksmith-evaluator produced no JSON output.")


def write_temp_node(node: dict[str, Any]) -> Path:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        path = Path(handle.name)
        json.dump(node, handle, ensure_ascii=True, indent=2)
    return path


def emit_result(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return
    print(f"{result['node_id']} {result['status']} attempt={result['attempt']}")
    if result["failure_reason"]:
        print(result["failure_reason"])


def main() -> int:
    args = parse_args()
    cwd = args.cwd.resolve()
    node = load_node(args)
    revision_payload = load_revision_payload(args.revision_file)
    execution_cwd = resolve_execution_cwd(node, cwd)

    results_dir = (args.results_dir or (cwd / ".tasksmith" / "worker-runs")).resolve()
    node_dir = results_dir / node["id"]
    attempt = args.attempt if args.attempt is not None else next_attempt(node_dir)
    if attempt < 1:
        raise SystemExit("--attempt must be >= 1")
    attempt_dir = node_dir / f"attempt-{attempt:03d}"
    attempt_dir.mkdir(parents=True, exist_ok=False)

    brief_path = attempt_dir / "brief.txt"
    stdout_path = attempt_dir / "stdout.txt"
    stderr_path = attempt_dir / "stderr.txt"
    execution_path = attempt_dir / "execution.json"
    result_path = attempt_dir / "result.json"

    required_inputs, missing_inputs, warnings = resolve_input_artifacts(node, cwd)
    brief = build_brief(node, required_inputs, revision_payload)
    brief_path.write_text(brief, encoding="utf-8")

    if missing_inputs:
        result = {
            "node_id": node["id"],
            "status": "blocked",
            "provider": "unknown",
            "attempt": attempt,
            "output_paths": [],
            "result_summary": "Blocked before execution because required local inputs were missing.",
            "warnings": warnings,
            "failure_reason": f"Missing required local inputs: {', '.join(missing_inputs)}",
            "raw_execution_ref": str(execution_path),
            "evaluation_verdict": None,
            "evaluation_summary": None,
            "evaluation_ref": None,
            "revision_source_ref": None if args.revision_file is None else str(args.revision_file.resolve()),
        }
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        write_json(execution_path, {"executed": False, "reason": result["failure_reason"]})
        write_json(result_path, result)
        emit_result(result, args.json)
        return 2

    exec_script = (Path(__file__).resolve().parents[2] / "tasksmith-exec" / "scripts" / "run_isolated_agent.py")
    if not exec_script.exists():
        raise SystemExit(f"tasksmith-exec runner not found: {exec_script}")

    command = [
        sys.executable,
        str(exec_script),
        "--provider",
        args.provider,
        "--cwd",
        str(execution_cwd),
        "--prompt-file",
        str(brief_path),
        "--capture-output",
        str(stdout_path),
        "--capture-error",
        str(stderr_path),
        "--json",
    ]
    if args.model:
        command.extend(["--model", args.model])
    if args.schema_file:
        command.extend(["--schema-file", str(args.schema_file.resolve())])
    if args.dry_run:
        command.append("--dry-run")

    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )

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

    inferred_outputs = parse_output_paths(node, cwd)
    existing_outputs = [path for path in inferred_outputs if Path(path).exists()]
    missing_outputs = [path for path in inferred_outputs if not Path(path).exists()]

    evaluation_payload: dict[str, Any] | None = None
    evaluation_ref: str | None = None

    if args.dry_run:
        status = "success" if completed.returncode == 0 else "failed"
        failure_reason = None if completed.returncode == 0 else "Dry-run command generation failed."
        summary = "Prepared isolated execution command without running the provider."
    elif completed.returncode != 0:
        status = "failed"
        failure_reason = summarize(
            execution.get("stderr", ""),
            completed.stderr,
            "Isolated worker execution exited non-zero.",
        )
        summary = "Provider execution failed."
    elif missing_outputs:
        status = "failed"
        failure_reason = f"Output contract not satisfied; missing expected artifacts: {', '.join(missing_outputs)}"
        summary = "Provider returned successfully but expected output artifacts were not found."
    else:
        status = "success"
        failure_reason = None
        summary = summarize(
            execution.get("stdout", ""),
            execution.get("stderr", ""),
            "Node executed successfully.",
        )

    provisional_result = {
        "node_id": node["id"],
        "status": status,
        "provider": execution.get("provider", "unknown"),
        "attempt": attempt,
        "output_paths": existing_outputs,
        "result_summary": summary,
        "warnings": warnings,
        "failure_reason": failure_reason,
        "raw_execution_ref": str(execution_path),
        "evaluation_verdict": None,
        "evaluation_summary": None,
        "evaluation_ref": None,
        "revision_source_ref": None if args.revision_file is None else str(args.revision_file.resolve()),
    }
    write_json(result_path, provisional_result)

    if status == "success" and not args.skip_evaluation:
        evaluation_payload = run_evaluator(args, node, cwd, result_path, execution_path, attempt)
        evaluation_ref = str(
            (args.evaluation_results_dir or (cwd / ".tasksmith" / "evaluator-runs")).resolve()
            / node["id"]
            / f"attempt-{attempt:03d}"
            / "evaluation.json"
        )
        verdict = evaluation_payload.get("verdict")
        evaluation_summary = evaluation_payload.get("summary")
        if verdict == "pass":
            summary = evaluation_summary or summary
            status = "success"
            failure_reason = None
        elif verdict == "needs_revision":
            status = "needs_revision"
            failure_reason = evaluation_summary or "Evaluator requested revisions."
            summary = "Execution completed, but evaluator requested revisions."
        else:
            status = "failed"
            failure_reason = "Evaluator returned an unknown verdict."
            summary = "Execution completed, but evaluation failed."
    elif status == "success" and args.skip_evaluation:
        warnings = warnings + ["Evaluation was skipped; success reflects execution and output presence only."]

    result = {
        "node_id": node["id"],
        "status": status,
        "provider": execution.get("provider", "unknown"),
        "attempt": attempt,
        "output_paths": existing_outputs,
        "result_summary": summary,
        "warnings": warnings,
        "failure_reason": failure_reason,
        "raw_execution_ref": str(execution_path),
        "evaluation_verdict": None if evaluation_payload is None else evaluation_payload.get("verdict"),
        "evaluation_summary": None if evaluation_payload is None else evaluation_payload.get("summary"),
        "evaluation_ref": evaluation_ref,
        "revision_source_ref": None if args.revision_file is None else str(args.revision_file.resolve()),
    }
    write_json(result_path, result)
    emit_result(result, args.json)
    return 0 if status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
