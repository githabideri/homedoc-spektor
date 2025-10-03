# HomeDoc Spektor

HomeDoc Spektor captures Linux system inventory data and generates reports with
local Ollama models. The tool gathers CPU, memory, storage, firmware, and
software facts as structured JSON then asks an LLM for summaries, section deep
dives, or answers to ad-hoc questions.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Collect data into system.json
spektor --collect --output system.json

# Generate an overview report using the default model
spektor --report --input system.json --overview

# Ask an ad-hoc question about the collected data
spektor --question "Do we have an NVIDIA GPU?" --input system.json

# Launch the interactive REPL (default command)
spektor --interactive

# The CLI also falls back to the REPL when no flags are supplied
spektor
```

See [USAGE.md](USAGE.md) for detailed CLI and REPL instructions.
