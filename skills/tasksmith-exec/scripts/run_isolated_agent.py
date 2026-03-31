#!/usr/bin/env python3
"""Run one isolated agent session through Codex or Claude Code."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a fresh non-persistent agent session via Codex or Claude Code."
    )
    parser.add_argument(
        "--provider",
        choices=("auto", "codex", "claude"),
        default=os.environ.get("TASKSMITH_EXEC_PROVIDER", "auto"),
        help="Agent CLI to use. Defaults to TASKSMITH_EXEC_PROVIDER or auto.",
    )
    parser.add_argument("--cwd", default=os.getcwd(), help="Working directory for the agent.")
    parser.add_argument("--model", help="Optional model name passed through to the provider.")
    parser.add_argument(
        "--prompt",
        help="Inline prompt. Mutually exclusive with --prompt-file. Defaults to stdin when omitted.",
    )
    parser.add_argument("--prompt-file", help="Read the prompt from a file.")
    parser.add_argument(
        "--schema-file",
        help="Optional JSON schema file. Uses provider-specific schema flags when supported.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a wrapper JSON object with provider, command, exit_code, stdout, and stderr.",
    )
    parser.add_argument(
        "--capture-output",
        help="Write stdout to a file after execution.",
    )
    parser.add_argument(
        "--capture-error",
        help="Write stderr to a file after execution.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved command without executing it.",
    )
    return parser.parse_args()


def load_prompt(args: argparse.Namespace) -> str:
    if args.prompt and args.prompt_file:
        raise SystemExit("Use only one of --prompt or --prompt-file.")
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    if args.prompt is not None:
        return args.prompt
    return sys.stdin.read()


def resolve_provider(provider: str) -> str:
    if provider != "auto":
        if shutil.which(provider) is None:
            raise SystemExit(f"Requested provider '{provider}' is not installed or not on PATH.")
        return provider
    for candidate in ("codex", "claude"):
        if shutil.which(candidate):
            return candidate
    raise SystemExit("No supported provider found on PATH. Install codex or claude.")


def build_command(
    provider: str, cwd: str, prompt: str, model: str | None, schema_file: str | None
) -> list[str]:
    if provider == "codex":
        command = ["codex", "exec", "--ephemeral", "-C", cwd]
        if model:
            command.extend(["--model", model])
        if schema_file:
            command.extend(["--output-schema", schema_file])
        command.append(prompt)
        return command
    command = ["claude", "-p", "--no-session-persistence"]
    if model:
        command.extend(["--model", model])
    if schema_file:
        command.extend(["--json-schema", Path(schema_file).read_text(encoding="utf-8")])
        command.extend(["--output-format", "json"])
    command.append(prompt)
    return command


def write_capture(path: str | None, content: str) -> None:
    if not path:
        return
    Path(path).write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    prompt = load_prompt(args)
    if not prompt.strip():
        raise SystemExit("Prompt is empty.")

    provider = resolve_provider(args.provider)
    command = build_command(provider, args.cwd, prompt, args.model, args.schema_file)

    if args.dry_run:
        payload = {"provider": provider, "command": command, "cwd": args.cwd}
        if args.json:
            print(json.dumps(payload, ensure_ascii=True, indent=2))
        else:
            print(subprocess.list2cmdline(command))
        return 0

    completed = subprocess.run(
        command,
        cwd=args.cwd,
        text=True,
        capture_output=True,
        check=False,
    )

    write_capture(args.capture_output, completed.stdout)
    write_capture(args.capture_error, completed.stderr)

    if args.json:
        print(
            json.dumps(
                {
                    "provider": provider,
                    "command": command,
                    "cwd": args.cwd,
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                },
                ensure_ascii=True,
            )
        )
    else:
        sys.stdout.write(completed.stdout)
        if completed.stderr:
            sys.stderr.write(completed.stderr)

    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
