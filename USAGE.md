# Usage

Homedoc Spektor provides a straightforward two-step workflow driven by the
command-line interface. Install the package (`pip install -e .`) or invoke the
CLI directly with `python spektor-cli.py` from the repository root.

## Workflow overview

1. **Collect** system information and write it to a JSON document.
2. **Generate summaries** from that JSON using a local Ollama model.

Every run must choose exactly one of the high-level actions: `--collect` for
step 1 or `--report` for step 2. Running `spektor` with no flags now prints the
help text instead of launching an interactive shell.

## Step 1 – Collect system information

```
spektor --collect --output out/system.json [--debug] [--raw-dir DIR] [--timeout N]
```

Collects system facts on Linux hosts and saves them as JSON. Useful options:

- `--output` — path to the resulting JSON file. If omitted, the document is
  printed to stdout.
- `--raw-dir` — capture raw command output for later inspection. Defaults to the
  value configured in the GUI (`./out/raw`).
- `--timeout` — per-command timeout in seconds (default: `5`).
- `--debug` — enable verbose capture for collectors, mirroring the CLI output in
  the debug artifacts directory.

## Step 2 – Generate LLM summaries

```
spektor --report --input out/system.json [--overview] [--section NAME ...] \
  [--json-only] [--model MODEL] [--server URL] [--system-prompt PROMPT] \
  [--show-thinking] [--save-thinking] [--debug]
```

Reads the saved JSON document and asks an Ollama model to produce
human-friendly summaries. `--input` is required. Helpful modifiers:

- `--overview` — request a high-level overview. If no other summarisation
  options are supplied the overview is generated automatically.
- `--section` — analyse specific sections. Repeat the flag to include multiple
  section names.
- `--json-only` — skip the LLM call and print the raw JSON document.
- `--model` / `--server` — choose the Ollama model and base URL.
- `--system-prompt` — override the system prompt. If the argument is a file path
  the contents are used; otherwise the string is passed directly to the model.
- `--show-thinking` — display `<thinking>` blocks returned by the model.
- `--save-thinking` — store raw LLM responses alongside other debug artifacts.
- `--debug` — capture detailed Ollama request/response metadata.

## Environment variables

- `SPEKTOR_EXTRAS` — comma-separated list controlling additional collection
  steps. Recognised values: `docker`, `systemd`, `kvm`.
- `SPEKTOR_DEBUG_LLM` — when set to `1`, enables capture of Ollama JSONL streams
  and metadata even without `--debug`.
- `SPEKTOR_THINKING` — when set to `show` includes `<thinking>` blocks in
  console output. When set to `save` always stores raw responses (with thinking)
  under `debug/`.

## Debug artifacts

- Collector debug artifacts live under `artifacts/` (or the directory supplied
  via `--raw-dir`). Each command logs its arguments, return code, stdout, and
  stderr as JSON for reproducibility.
- LLM debug artifacts live under `debug/`. Streamed responses are stored as
  `ollama_<timestamp>_<session>.jsonl` with matching metadata in
  `ollama_meta.json`. When thinking output capture is enabled raw responses are
  saved with the pattern `YYYYmmdd_HHMMSS_model_task_host_pid.raw.txt`.
