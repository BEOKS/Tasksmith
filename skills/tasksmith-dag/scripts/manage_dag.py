#!/usr/bin/env python3
"""Manage the authoritative Tasksmith DAG JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_DAG = {"version": 1, "nodes": {}}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"DAG file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("DAG root must be a JSON object")
    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        raise SystemExit("DAG file must contain an object field named 'nodes'")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def require_node(data: dict[str, Any], node_id: str) -> dict[str, Any]:
    nodes = data["nodes"]
    if node_id not in nodes:
        raise SystemExit(f"Unknown node id: {node_id}")
    node = nodes[node_id]
    if not isinstance(node, dict):
        raise SystemExit(f"Node {node_id} must be a JSON object")
    return node


def load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Payload file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in payload file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Payload in {path} must be a JSON object")
    return payload


def normalize_depends_on(node: dict[str, Any]) -> None:
    depends_on = node.get("depends_on", [])
    if depends_on is None:
        depends_on = []
    if not isinstance(depends_on, list) or not all(isinstance(item, str) for item in depends_on):
        raise SystemExit("Field 'depends_on' must be a list of node ids")
    deduped = []
    seen = set()
    for item in depends_on:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    node["depends_on"] = deduped


def cmd_init(args: argparse.Namespace) -> int:
    if args.dag_file.exists() and not args.force:
        raise SystemExit(f"DAG file already exists: {args.dag_file}")
    write_json(args.dag_file, DEFAULT_DAG.copy())
    print(args.dag_file)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    data = load_json(args.dag_file)
    json.dump(data, sys.stdout, indent=2, ensure_ascii=True)
    sys.stdout.write("\n")
    return 0


def cmd_next_id(args: argparse.Namespace) -> int:
    data = load_json(args.dag_file)
    max_num = 0
    for node_id in data["nodes"]:
        if isinstance(node_id, str) and node_id.startswith("N") and node_id[1:].isdigit():
            max_num = max(max_num, int(node_id[1:]))
    print(f"N{max_num + 1}")
    return 0


def cmd_add_node(args: argparse.Namespace) -> int:
    data = load_json(args.dag_file)
    payload = load_payload(args.node_file)
    node_id = payload.get("id")
    if not isinstance(node_id, str) or not node_id:
        raise SystemExit("New node payload must include a non-empty string field 'id'")
    if node_id in data["nodes"]:
        raise SystemExit(f"Node already exists: {node_id}")
    normalize_depends_on(payload)
    for dep in payload["depends_on"]:
        if dep not in data["nodes"]:
            raise SystemExit(f"Dependency {dep} does not exist")
    data["nodes"][node_id] = payload
    write_json(args.dag_file, data)
    print(node_id)
    return 0


def cmd_update_node(args: argparse.Namespace) -> int:
    data = load_json(args.dag_file)
    node = require_node(data, args.node_id)
    patch = load_payload(args.patch_file)
    if "id" in patch and patch["id"] != args.node_id:
        raise SystemExit("Node id cannot be changed")
    node.update(patch)
    node["id"] = args.node_id
    normalize_depends_on(node)
    for dep in node["depends_on"]:
        if dep not in data["nodes"]:
            raise SystemExit(f"Dependency {dep} does not exist")
        if dep == args.node_id:
            raise SystemExit("A node cannot depend on itself")
    write_json(args.dag_file, data)
    print(args.node_id)
    return 0


def cmd_delete_node(args: argparse.Namespace) -> int:
    data = load_json(args.dag_file)
    require_node(data, args.node_id)
    dependents = [
        other_id
        for other_id, other in data["nodes"].items()
        if other_id != args.node_id and args.node_id in other.get("depends_on", [])
    ]
    if dependents and not args.force:
        raise SystemExit(
            f"Cannot delete {args.node_id}; dependent nodes exist: {', '.join(sorted(dependents))}"
        )
    for dep_id in dependents:
        other = data["nodes"][dep_id]
        other["depends_on"] = [dep for dep in other.get("depends_on", []) if dep != args.node_id]
    del data["nodes"][args.node_id]
    write_json(args.dag_file, data)
    print(args.node_id)
    return 0


def cmd_add_dependency(args: argparse.Namespace) -> int:
    data = load_json(args.dag_file)
    node = require_node(data, args.node_id)
    require_node(data, args.depends_on)
    if args.node_id == args.depends_on:
        raise SystemExit("A node cannot depend on itself")
    depends_on = node.get("depends_on", [])
    if args.depends_on not in depends_on:
        depends_on.append(args.depends_on)
    node["depends_on"] = depends_on
    normalize_depends_on(node)
    write_json(args.dag_file, data)
    print(args.node_id)
    return 0


def cmd_remove_dependency(args: argparse.Namespace) -> int:
    data = load_json(args.dag_file)
    node = require_node(data, args.node_id)
    depends_on = node.get("depends_on", [])
    node["depends_on"] = [item for item in depends_on if item != args.depends_on]
    write_json(args.dag_file, data)
    print(args.node_id)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage a Tasksmith DAG JSON file.")
    parser.add_argument("--dag-file", required=True, type=Path, help="Path to the authoritative DAG JSON file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a new DAG file")
    init_parser.add_argument("--force", action="store_true", help="Overwrite the file if it already exists")
    init_parser.set_defaults(func=cmd_init)

    show_parser = subparsers.add_parser("show", help="Print the DAG JSON")
    show_parser.set_defaults(func=cmd_show)

    next_id_parser = subparsers.add_parser("next-id", help="Print the next node id like N12")
    next_id_parser.set_defaults(func=cmd_next_id)

    add_node_parser = subparsers.add_parser("add-node", help="Add a new node from a JSON payload file")
    add_node_parser.add_argument("--node-file", required=True, type=Path, help="JSON file containing the full node object")
    add_node_parser.set_defaults(func=cmd_add_node)

    update_node_parser = subparsers.add_parser("update-node", help="Merge a JSON patch into a node")
    update_node_parser.add_argument("--node-id", required=True, help="Existing node id")
    update_node_parser.add_argument("--patch-file", required=True, type=Path, help="JSON file containing fields to merge")
    update_node_parser.set_defaults(func=cmd_update_node)

    delete_node_parser = subparsers.add_parser("delete-node", help="Delete a node")
    delete_node_parser.add_argument("--node-id", required=True, help="Existing node id")
    delete_node_parser.add_argument("--force", action="store_true", help="Also remove this dependency from dependent nodes")
    delete_node_parser.set_defaults(func=cmd_delete_node)

    add_dep_parser = subparsers.add_parser("add-dependency", help="Add a dependency edge")
    add_dep_parser.add_argument("--node-id", required=True, help="Target node id")
    add_dep_parser.add_argument("--depends-on", required=True, help="Prerequisite node id")
    add_dep_parser.set_defaults(func=cmd_add_dependency)

    remove_dep_parser = subparsers.add_parser("remove-dependency", help="Remove a dependency edge")
    remove_dep_parser.add_argument("--node-id", required=True, help="Target node id")
    remove_dep_parser.add_argument("--depends-on", required=True, help="Prerequisite node id")
    remove_dep_parser.set_defaults(func=cmd_remove_dependency)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
