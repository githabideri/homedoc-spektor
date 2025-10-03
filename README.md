# HomeDoc Spektor

HomeDoc Spektor captures Linux system inventory data and generates reports with
local Ollama models. The tool gathers CPU, memory, storage, firmware, and
software facts as structured JSON then asks an LLM for summaries and section
deep dives.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Collect data into out/system.json
spektor --collect --output out/system.json

# Generate an overview report using the default model
spektor --report --input out/system.json --overview
```

See [USAGE.md](USAGE.md) for detailed CLI instructions.

## GUI helper

A Tkinter-based helper is available for people who prefer a visual interface.
It walks through the same “collect then summarise” workflow as the CLI and
shows the equivalent command as you toggle settings, making it easy to
copy/paste the flags you need.

```bash
python spektor_gui.py
```

The GUI can also execute the assembled command directly and will display the
output in the window.
