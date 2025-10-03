"""Interactive REPL for Spektor."""

from __future__ import annotations

import argparse
import json
import shlex
from typing import Any, Dict, List, Optional

from .llm import OllamaClient
from .reporting import answer_query, overview, per_section
from .sysprobe import collect as collect_probe
from .util import safe_json_dump

DEFAULT_SERVER = "http://localhost:11434"
DEFAULT_MODEL = "gemma3:12b"
MODEL_CHOICES = [
    ("gemma3:12b", "default"),
    ("qwen3:14b", "thinking model"),
    ("mistral:7b", "~4 GB"),
    ("other", "custom"),
]


class InteractiveShell:
    def __init__(
        self,
        *,
        initial_document: Optional[Dict[str, Any]] = None,
        default_model: str = DEFAULT_MODEL,
        default_server: str = DEFAULT_SERVER,
    ) -> None:
        self.server = default_server
        self.model = default_model
        self.client: Optional[OllamaClient] = None
        self.document: Optional[Dict[str, Any]] = initial_document
        self.show_thinking = False
        self.save_thinking = False

    def start(self) -> None:
        print("Spektor interactive shell. Type 'help' for commands.")
        self._configure_llm()
        self.loop()

    def _configure_llm(self) -> None:
        server = input(f"Ollama server [{DEFAULT_SERVER}]: ").strip()
        if server:
            self.server = server
        print("Available models:")
        for idx, (model, desc) in enumerate(MODEL_CHOICES, 1):
            print(f"  {idx}. {model} ({desc})")
        selection = input(f"Select model [1]: ").strip() or "1"
        try:
            choice_idx = int(selection) - 1
            model_choice = MODEL_CHOICES[choice_idx][0]
        except (ValueError, IndexError):
            model_choice = DEFAULT_MODEL
        if model_choice == "other":
            custom = input("Enter model name: ").strip()
            if custom:
                self.model = custom
        else:
            self.model = model_choice
        self.client = OllamaClient(base_url=self.server, model=self.model)
        print(f"Using {self.model} at {self.server}")

    def loop(self) -> None:
        while True:
            try:
                raw = input("spektor> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not raw:
                continue
            if raw in {"quit", "exit"}:
                break
            if raw == "help":
                self._print_help()
                continue
            if raw.startswith(":"):
                self._handle_toggle(raw)
                continue
            self._dispatch(raw)

    def _print_help(self) -> None:
        print("Available commands:")
        print("  collect [--debug] [--raw-dir DIR] [--timeout N]")
        print("  load <path>")
        print("  save <path>")
        print("  overview")
        print("  section <name[,name]>\n  ask <question>")
        print("  show [json.path]")
        print("  quit")
        print("  :show-thinking on|off  :save-thinking on|off")

    def _handle_toggle(self, raw: str) -> None:
        parts = raw.split()
        if parts[0] == ":show-thinking" and len(parts) > 1:
            self.show_thinking = parts[1].lower() == "on"
            print(f"Show thinking: {self.show_thinking}")
        elif parts[0] == ":save-thinking" and len(parts) > 1:
            self.save_thinking = parts[1].lower() == "on"
            print(f"Save thinking: {self.save_thinking}")
        else:
            print("Unknown toggle")

    def _ensure_doc(self) -> bool:
        if self.document is None:
            print("No document loaded. Run 'collect' or 'load <path>'.")
            return False
        return True

    def _dispatch(self, raw: str) -> None:
        parts = shlex.split(raw)
        if not parts:
            return
        cmd, *args = parts
        if cmd == "collect":
            self._cmd_collect(args)
        elif cmd == "load":
            self._cmd_load(args)
        elif cmd == "save":
            self._cmd_save(args)
        elif cmd == "overview":
            self._cmd_overview()
        elif cmd == "section":
            self._cmd_section(args)
        elif cmd == "ask":
            self._cmd_ask(args)
        elif cmd == "show":
            self._cmd_show(args)
        else:
            print(f"Unknown command: {cmd}")

    def _cmd_collect(self, args: List[str]) -> None:
        parser = argparse.ArgumentParser(prog="collect", add_help=False)
        parser.add_argument("--debug", action="store_true")
        parser.add_argument("--raw-dir")
        parser.add_argument("--timeout", type=int, default=5)
        try:
            ns = parser.parse_args(args)
        except SystemExit:
            return
        self.document = collect_probe(debug=ns.debug, raw_dir=ns.raw_dir, timeout=ns.timeout)
        print("Collection complete.")
        self._print_equivalent(
            "collect",
            [
                f"--output <file>",
                "--debug" if ns.debug else None,
                f"--raw-dir {ns.raw_dir}" if ns.raw_dir else None,
                f"--timeout {ns.timeout}" if ns.timeout else None,
            ],
        )

    def _cmd_load(self, args: List[str]) -> None:
        if not args:
            print("Usage: load <path>")
            return
        path = args[0]
        try:
            with open(path, "r", encoding="utf-8") as fh:
                self.document = json.load(fh)
        except OSError as exc:
            print(f"Failed to load {path}: {exc}")
            return
        print(f"Loaded {path}")
        self._print_equivalent("collect", [f"--output {path}"])

    def _cmd_save(self, args: List[str]) -> None:
        if not self._ensure_doc():
            return
        if not args:
            print("Usage: save <path>")
            return
        path = args[0]
        safe_json_dump(self.document, path)
        print(f"Saved {path}")
        self._print_equivalent("collect", [f"--output {path}"])

    def _cmd_overview(self) -> None:
        if not self._ensure_doc() or self.client is None:
            return
        response = overview(
            self.document,
            self.client,
            show_thinking=self.show_thinking,
            save_thinking=self.save_thinking,
        )
        print(response.text)
        self._print_equivalent("report", ["--input <file>", "--overview"])

    def _cmd_section(self, args: List[str]) -> None:
        if not self._ensure_doc() or self.client is None:
            return
        if not args:
            print("Usage: section <name[,name]>")
            return
        sections = [part.strip() for part in args[0].split(",") if part.strip()]
        response = per_section(
            self.document,
            sections,
            self.client,
            show_thinking=self.show_thinking,
            save_thinking=self.save_thinking,
        )
        print(response.text)
        args = ["--input <file>"]
        for section in sections:
            args.append(f"--section {section}")
        self._print_equivalent("report", args)

    def _cmd_ask(self, args: List[str]) -> None:
        if not self._ensure_doc() or self.client is None:
            return
        if not args:
            print("Usage: ask <question>")
            return
        question = " ".join(args)
        response = answer_query(
            self.document,
            question,
            self.client,
            show_thinking=self.show_thinking,
            save_thinking=self.save_thinking,
        )
        print(response.text)
        self._print_equivalent("query", ["--input <file>", json.dumps(question)])

    def _cmd_show(self, args: List[str]) -> None:
        if not self._ensure_doc():
            return
        if not args:
            print(json.dumps(self.document, indent=2, ensure_ascii=False))
            return
        path = args[0]
        value = self.document
        for part in path.split("."):
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list):
                try:
                    idx = int(part)
                    value = value[idx]
                except (ValueError, IndexError):
                    value = None
                    break
            else:
                value = None
                break
        print(json.dumps(value, indent=2, ensure_ascii=False))

    def _print_equivalent(self, subcommand: str, args: List[Optional[str]]) -> None:
        filtered = [arg for arg in args if arg]
        pieces = ["spektor", subcommand] + filtered
        print("# CLI equivalent: " + " ".join(pieces))


def main(
    *,
    input_path: str | None = None,
    model: str = DEFAULT_MODEL,
    server: str = DEFAULT_SERVER,
) -> None:
    document = None
    if input_path:
        try:
            with open(input_path, "r", encoding="utf-8") as fh:
                document = json.load(fh)
        except OSError as exc:
            print(f"Failed to load {input_path}: {exc}")
    shell = InteractiveShell(initial_document=document, default_model=model, default_server=server)
    shell.start()


if __name__ == "__main__":
    main()
