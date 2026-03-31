# Local CLI Notes

This file records the relevant single-agent fresh-session behavior discovered from local help output.

## Codex

Observed commands:

- `codex exec [PROMPT]`
- `codex exec --ephemeral`
- `codex exec --output-schema <file>`
- `codex exec --json`
- `codex exec -C <dir>`

Useful properties:

- `exec` is the non-interactive command intended for one-shot execution.
- `--ephemeral` prevents session persistence, which is the cleanest fit for isolated node runs.
- `--output-schema` can constrain the final response shape.
- `--json` emits JSONL events suitable for harness logging.

Recommended isolated pattern:

```bash
codex exec --ephemeral -C /abs/path "task prompt"
```

## Claude Code

Observed commands:

- `claude -p [prompt]`
- `claude --no-session-persistence`
- `claude --json-schema <schema>`
- `claude --output-format json`
- `claude --permission-mode <mode>`

Useful properties:

- `-p` runs non-interactively and prints the response.
- `--no-session-persistence` prevents saving and reusing the session.
- `--json-schema` can constrain the final response shape.
- `--output-format json` is useful when the harness wants a single JSON result object.

Recommended isolated pattern:

```bash
claude -p --no-session-persistence "task prompt"
```

## Isolation Rule

For Tasksmith DAG execution, do not use interactive resume or continue flows.
Always start a new session and pass only the node-local brief plus required inputs.
