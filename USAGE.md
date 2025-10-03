# Usage

Homedoc Spektor ships with both non-interactive commands and an interactive
shell. Install the package (`pip install -e .`) or invoke via `python
spektor-cli.py` from the repository root.

## Interactive shell

Running `spektor` with no arguments launches the REPL. The startup flow prompts
for the Ollama server URL and model. Defaults are:

- server: `http://localhost:11434`
- model: `gemma3:12b`

Available model shortcuts:

1. `gemma3:12b` (default)
2. `qwen3:14b` (thinking model)
3. `mistral:7b` (~4 GB)
4. `other` (enter a custom model name)

### REPL commands

```
collect [--debug] [--raw-dir DIR] [--timeout N]
load <path>
save <path>
overview
section <name[,name]>
ask <question>
show [json.path]
quit
```

Toggles are available for LLM thinking controls:

```
:show-thinking on|off
:save-thinking on|off
```

After each action the shell prints the equivalent CLI invocation to help users
transition to scripts and automation.

## CLI commands

### `spektor collect`

```
spektor collect --output system.json [--debug] [--raw-dir DIR] [--timeout N]
```

Collects system facts on Linux hosts. When `--debug` is supplied the collector
stores raw command output inside an `artifacts/` directory (or the provided
`--raw-dir`). The resulting JSON always includes the schema version and schema
validation issues when present.

### `spektor report`

```
spektor report --input system.json [--overview] [--section NAME ...] \
  [--json-only] [--model MODEL] [--server URL] [--system-prompt PROMPT] \
  [--show-thinking] [--save-thinking] [--debug]
```

Reads a saved JSON document and uses the Ollama model to produce human-friendly
summaries. `--json-only` skips the LLM call and prints the document. When
`--system-prompt` is provided the value is treated as a file path if it exists,
otherwise it is interpreted as inline prompt text.

### `spektor query`

```
spektor query --input system.json "Do we have an NVIDIA GPU?" \
  [--json-only] [--model MODEL] [--server URL] [--system-prompt PROMPT] \
  [--show-thinking] [--save-thinking] [--debug]
```

Answers ad-hoc questions strictly from the JSON document. If the requested data
is missing the response lists commands to run in order to collect it.

### `spektor interactive`

```
spektor interactive [--input system.json] [--model MODEL] [--server URL]
```

Starts the REPL with optional defaults. If `--input` is provided the JSON file is
loaded automatically after startup.

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
