#!/usr/bin/env python3
"""Aggregate Tasksmith benchmark trial data into JSON and Markdown summaries."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate a Tasksmith benchmark manifest into summary artifacts."
    )
    parser.add_argument("--manifest", type=Path, required=True, help="Path to benchmark manifest.json.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for summary artifacts. Defaults to <manifest-dir>/results.",
    )
    parser.add_argument("--json", action="store_true", help="Print the JSON summary to stdout.")
    parser.add_argument("--markdown", action="store_true", help="Print the Markdown summary to stdout.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print the resolved output paths without writing files.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("Manifest root must be a JSON object.")
    return payload


def require_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"Manifest field '{field}' must be a non-empty string.")
    return value


def require_list(payload: dict[str, Any], field: str) -> list[Any]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise SystemExit(f"Manifest field '{field}' must be a list.")
    return value


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def safe_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return mean(values)


def summarize_trials(manifest: dict[str, Any]) -> dict[str, Any]:
    experiment_id = require_string(manifest, "experiment_id")
    title = require_string(manifest, "title")
    benchmark_question = require_string(manifest, "benchmark_question")
    variants = require_list(manifest, "variants")
    trials = require_list(manifest, "trials")
    metrics_declared = manifest.get("metrics", [])
    if metrics_declared is not None and not isinstance(metrics_declared, list):
        raise SystemExit("Manifest field 'metrics' must be a list when provided.")

    variant_defs: dict[str, dict[str, Any]] = {}
    for raw_variant in variants:
        if not isinstance(raw_variant, dict):
            raise SystemExit("Each variant entry must be a JSON object.")
        variant_id = require_string(raw_variant, "id")
        require_string(raw_variant, "label")
        if variant_id in variant_defs:
            raise SystemExit(f"Duplicate variant id in manifest: {variant_id}")
        variant_defs[variant_id] = raw_variant

    trial_records: list[dict[str, Any]] = []
    per_variant_trials: dict[str, list[dict[str, Any]]] = defaultdict(list)
    per_task_status: dict[str, dict[str, str]] = defaultdict(dict)

    for raw_trial in trials:
        if not isinstance(raw_trial, dict):
            raise SystemExit("Each trial entry must be a JSON object.")
        variant_id = require_string(raw_trial, "variant_id")
        if variant_id not in variant_defs:
            raise SystemExit(f"Trial references unknown variant id: {variant_id}")
        task_id = require_string(raw_trial, "task_id")
        run_id = require_string(raw_trial, "run_id")
        status = require_string(raw_trial, "status")
        metrics = raw_trial.get("metrics", {})
        if metrics is None:
            metrics = {}
        if not isinstance(metrics, dict):
            raise SystemExit("Trial field 'metrics' must be an object when provided.")

        normalized_metrics = {
            key: value for key, value in metrics.items() if is_number(value) or value is None
        }
        trial = {
            "variant_id": variant_id,
            "task_id": task_id,
            "run_id": run_id,
            "status": status,
            "metrics": normalized_metrics,
            "artifacts": raw_trial.get("artifacts", {}),
            "notes": raw_trial.get("notes", {}),
        }
        trial_records.append(trial)
        per_variant_trials[variant_id].append(trial)
        per_task_status[task_id][variant_id] = status

    metric_names: set[str] = set()
    for trial in trial_records:
        metric_names.update(trial["metrics"].keys())
    if isinstance(metrics_declared, list):
        for item in metrics_declared:
            if isinstance(item, str) and item.strip():
                metric_names.add(item)

    variant_summaries: list[dict[str, Any]] = []
    for variant_id in sorted(variant_defs):
        variant = variant_defs[variant_id]
        variant_trials = per_variant_trials.get(variant_id, [])
        metric_summary: dict[str, Any] = {}
        for metric_name in sorted(metric_names):
            values = [
                float(trial["metrics"][metric_name])
                for trial in variant_trials
                if metric_name in trial["metrics"] and trial["metrics"][metric_name] is not None
            ]
            metric_summary[metric_name] = {
                "count": len(values),
                "mean": safe_mean(values),
                "sum": sum(values) if values else None,
            }

        statuses = defaultdict(int)
        for trial in variant_trials:
            statuses[trial["status"]] += 1

        variant_summaries.append(
            {
                "variant_id": variant_id,
                "label": variant["label"],
                "family": variant.get("family"),
                "session_mode": variant.get("session_mode"),
                "trial_count": len(variant_trials),
                "status_counts": dict(sorted(statuses.items())),
                "metrics": metric_summary,
            }
        )

    pairwise_comparisons: list[dict[str, Any]] = []
    variant_ids = sorted(variant_defs)
    for index, left_id in enumerate(variant_ids):
        for right_id in variant_ids[index + 1 :]:
            left_summary = next(item for item in variant_summaries if item["variant_id"] == left_id)
            right_summary = next(item for item in variant_summaries if item["variant_id"] == right_id)
            metric_deltas: dict[str, Any] = {}
            for metric_name in sorted(metric_names):
                left_mean = left_summary["metrics"][metric_name]["mean"]
                right_mean = right_summary["metrics"][metric_name]["mean"]
                if left_mean is None or right_mean is None:
                    delta = None
                else:
                    delta = right_mean - left_mean
                metric_deltas[metric_name] = {
                    "left_mean": left_mean,
                    "right_mean": right_mean,
                    "delta_right_minus_left": delta,
                }
            pairwise_comparisons.append(
                {
                    "left_variant_id": left_id,
                    "right_variant_id": right_id,
                    "metric_deltas": metric_deltas,
                }
            )

    coverage_summary = {
        "task_count": len(per_task_status),
        "task_ids": sorted(per_task_status),
        "variant_count": len(variant_defs),
        "trial_count": len(trial_records),
    }

    return {
        "experiment_id": experiment_id,
        "title": title,
        "benchmark_question": benchmark_question,
        "coverage": coverage_summary,
        "variant_summaries": variant_summaries,
        "pairwise_comparisons": pairwise_comparisons,
        "declared_metrics": sorted(metric_names),
        "task_set": manifest.get("task_set"),
    }


def format_value(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# {summary['title']}",
        "",
        f"Experiment ID: `{summary['experiment_id']}`",
        "",
        "## Benchmark Question",
        "",
        summary["benchmark_question"],
        "",
        "## Coverage",
        "",
        f"- Tasks: {summary['coverage']['task_count']}",
        f"- Variants: {summary['coverage']['variant_count']}",
        f"- Trials: {summary['coverage']['trial_count']}",
        "",
        "## Variant Summaries",
        "",
    ]

    for variant in summary["variant_summaries"]:
        lines.extend(
            [
                f"### {variant['label']} (`{variant['variant_id']}`)",
                "",
                f"- Trial count: {variant['trial_count']}",
                f"- Session mode: {variant.get('session_mode') or 'n/a'}",
                f"- Status counts: {json.dumps(variant['status_counts'], ensure_ascii=True)}",
                "- Metrics:",
            ]
        )
        for metric_name, metric_summary in sorted(variant["metrics"].items()):
            lines.append(
                f"  - {metric_name}: mean={format_value(metric_summary['mean'])}, "
                f"sum={format_value(metric_summary['sum'])}, count={metric_summary['count']}"
            )
        lines.append("")

    lines.extend(["## Pairwise Comparisons", ""])
    for comparison in summary["pairwise_comparisons"]:
        lines.append(
            f"### `{comparison['left_variant_id']}` vs `{comparison['right_variant_id']}`"
        )
        lines.append("")
        for metric_name, metric_delta in sorted(comparison["metric_deltas"].items()):
            lines.append(
                f"- {metric_name}: left={format_value(metric_delta['left_mean'])}, "
                f"right={format_value(metric_delta['right_mean'])}, "
                f"delta(right-left)={format_value(metric_delta['delta_right_minus_left'])}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    output_dir = (args.output_dir or (manifest_path.parent / "results")).resolve()
    summary_json_path = output_dir / "summary.json"
    summary_md_path = output_dir / "summary.md"

    summary = summarize_trials(load_json(manifest_path))

    if args.dry_run:
        payload = {
            "manifest": str(manifest_path),
            "output_dir": str(output_dir),
            "summary_json": str(summary_json_path),
            "summary_md": str(summary_md_path),
            "variant_count": summary["coverage"]["variant_count"],
            "trial_count": summary["coverage"]["trial_count"],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_json_text = json.dumps(summary, indent=2, ensure_ascii=True) + "\n"
    summary_md_text = render_markdown(summary)
    write_text(summary_json_path, summary_json_text)
    write_text(summary_md_path, summary_md_text)

    if args.json:
        print(summary_json_text, end="")
    if args.markdown:
        print(summary_md_text, end="")
    if not args.json and not args.markdown:
        print(summary_json_path)
        print(summary_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
