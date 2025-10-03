"""Guided interactive experience for Spektor."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .llm import DEFAULT_BASE_URL, DEFAULT_MODEL as LLM_DEFAULT_MODEL, OllamaClient
from .reporting import answer_query, overview, per_section
from .sysprobe import collect as collect_probe
from .util import safe_json_dump

DEFAULT_SERVER = DEFAULT_BASE_URL
DEFAULT_MODEL = LLM_DEFAULT_MODEL
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
        self.server = self._normalize_server(default_server)
        self.model = default_model
        self.client: Optional[OllamaClient] = None
        self.document: Optional[Dict[str, Any]] = initial_document
        self.document_path: Optional[str] = None
        self.show_thinking = False
        self.save_thinking = False

    def start(self) -> None:
        print("Spektor interactive assistant. Let's get you set up.")
        self._configure_llm(initial=True)
        self._main_loop()

    def _configure_llm(self, *, initial: bool = False) -> None:
        print()
        if initial:
            print("First, let's choose which Ollama server and model to use.")
        server_prompt = f"Ollama server URL [{self.server}]: "
        server = input(server_prompt).strip()
        if server:
            self.server = self._normalize_server(server)
        print("Available models:")
        for idx, (model, desc) in enumerate(MODEL_CHOICES, 1):
            print(f"  {idx}. {model} ({desc})")
        model_prompt = (
            "Select a model by number, or type a custom name "
            f"[{self.model}]: "
        )
        selection = input(model_prompt).strip()
        if selection:
            if selection.isdigit():
                choice_idx = int(selection) - 1
                try:
                    model_choice = MODEL_CHOICES[choice_idx][0]
                except IndexError:
                    model_choice = self.model
            else:
                model_choice = selection
            if model_choice == "other":
                custom = input("Enter model name: ").strip()
                if custom:
                    self.model = custom
            else:
                self.model = model_choice
        self.show_thinking = self._ask_yes_no(
            "Display <thinking> blocks from the model?",
            default=self.show_thinking,
        )
        self.save_thinking = self._ask_yes_no(
            "Save raw model responses to disk?",
            default=self.save_thinking,
        )
        self._refresh_client()
        print(f"Great! We'll use {self.model} at {self.server}.")

    def _main_loop(self) -> None:
        while True:
            print()
            action = self._prompt_action()
            if action == "quit":
                print("Goodbye!")
                break
            if action == "collect":
                self._action_collect()
            elif action == "load":
                self._action_load()
            elif action == "save":
                self._action_save()
            elif action == "overview":
                self._action_overview()
            elif action == "section":
                self._action_section()
            elif action == "ask":
                self._action_ask()
            elif action == "show":
                self._action_show()
            elif action == "configure":
                self._configure_llm()

    def _prompt_action(self) -> str:
        options = [
            ("collect", "Collect system information"),
            ("load", "Load a saved JSON document"),
            ("save", "Save the current document"),
            ("overview", "Generate an overview with the LLM"),
            ("section", "Analyse specific sections"),
            ("ask", "Ask a custom question"),
            ("show", "Inspect raw JSON"),
            ("configure", "Change server/model settings"),
        ]
        for idx, (_, description) in enumerate(options, 1):
            print(f"{idx}. {description}")
        print("0. Quit")
        while True:
            choice = input("What would you like to do? [1]: ").strip() or "1"
            if choice == "0":
                return "quit"
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return options[idx][0]
            print("Please select a valid option.")

    def _ask_yes_no(self, prompt: str, *, default: bool = False) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        while True:
            answer = input(f"{prompt} {suffix} ").strip().lower()
            if not answer:
                return default
            if answer in {"y", "yes"}:
                return True
            if answer in {"n", "no"}:
                return False
            print("Please answer with 'y' or 'n'.")

    def _ask_int(self, prompt: str, *, default: int) -> int:
        while True:
            response = input(prompt).strip()
            if not response:
                return default
            try:
                return int(response)
            except ValueError:
                print("Please enter a number.")

    def _action_collect(self) -> None:
        print("\nLet's collect information from this machine.")
        debug = self._ask_yes_no("Capture debug artifacts?", default=False)
        raw_dir = input("Directory for raw command output (leave blank to skip): ").strip()
        raw_dir = raw_dir or None
        timeout = self._ask_int("Command timeout seconds [5]: ", default=5)
        output = input("Save the results to a file? Enter a path or leave blank: ").strip()
        output = output or None
        self.document = collect_probe(debug=debug, raw_dir=raw_dir, timeout=timeout)
        if output:
            safe_json_dump(self.document, output)
            self.document_path = output
            print(f"Collection complete and saved to {output}.")
        else:
            self.document_path = None
            print("Collection complete. The document is available in memory.")
        self._print_equivalent(
            "collect",
            [
                f"--output {output}" if output else None,
                "--debug" if debug else None,
                f"--raw-dir {raw_dir}" if raw_dir else None,
                f"--timeout {timeout}" if timeout != 5 else None,
            ],
        )

    def _ensure_doc(self) -> bool:
        if self.document is None:
            print("No document available. Collect new data or load an existing file first.")
            return False
        return True

    def _action_load(self) -> None:
        path = input("Path to the JSON document: ").strip()
        if not path:
            print("No path provided.")
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                self.document = json.load(fh)
        except OSError as exc:
            print(f"Failed to load {path}: {exc}")
            return
        self.document_path = path
        print(f"Loaded document from {path}.")
        self._print_equivalent("collect", [f"--output {path}"])

    def _action_save(self) -> None:
        if not self._ensure_doc():
            return
        default = self.document_path or "spektor-report.json"
        prompt = f"Where should we save the JSON? [{default}]: "
        path = input(prompt).strip() or default
        safe_json_dump(self.document, path)
        self.document_path = path
        print(f"Saved document to {path}.")
        self._print_equivalent("collect", [f"--output {path}"])

    def _action_overview(self) -> None:
        if not self._ensure_doc() or self.client is None:
            return
        response = overview(
            self.document,
            self.client,
            show_thinking=self.show_thinking,
            save_thinking=self.save_thinking,
        )
        print(response.text)
        args = self._llm_cli_args()
        args.insert(0, f"--input {self._document_cli_path()}")
        args.append("--overview")
        self._print_equivalent("report", args)

    def _action_section(self) -> None:
        if not self._ensure_doc() or self.client is None:
            return
        available = self._discover_sections()
        if available:
            print("Available sections:")
            for name in available:
                print(f"  - {name}")
        prompt = "Enter section names separated by commas: "
        raw = input(prompt).strip()
        if not raw:
            print("No sections provided.")
            return
        sections = [part.strip() for part in raw.split(",") if part.strip()]
        if not sections:
            print("No valid sections provided.")
            return
        response = per_section(
            self.document,
            sections,
            self.client,
            show_thinking=self.show_thinking,
            save_thinking=self.save_thinking,
        )
        print(response.text)
        args = self._llm_cli_args()
        args.insert(0, f"--input {self._document_cli_path()}")
        for section in sections:
            args.append(f"--section {section}")
        self._print_equivalent("report", args)

    def _action_ask(self) -> None:
        if not self._ensure_doc() or self.client is None:
            return
        question = input("What question would you like to ask? ").strip()
        if not question:
            print("Please provide a question.")
            return
        response = answer_query(
            self.document,
            question,
            self.client,
            show_thinking=self.show_thinking,
            save_thinking=self.save_thinking,
        )
        print(response.text)
        args = self._llm_cli_args()
        args.insert(0, f"--input {self._document_cli_path()}")
        args.append(json.dumps(question))
        self._print_equivalent("query", args)

    def _action_show(self) -> None:
        if not self._ensure_doc():
            return
        path = input("JSON path to inspect (leave blank for entire document): ").strip()
        if not path:
            print(json.dumps(self.document, indent=2, ensure_ascii=False))
            return
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

    def _llm_cli_args(self) -> List[str]:
        args: List[str] = []
        if self.model != DEFAULT_MODEL:
            args.append(f"--model {self.model}")
        if self.server != DEFAULT_SERVER:
            args.append(f"--server {self.server}")
        if self.show_thinking:
            args.append("--show-thinking")
        if self.save_thinking:
            args.append("--save-thinking")
        return args

    def _document_cli_path(self) -> str:
        return self.document_path or "<file>"

    def _discover_sections(self) -> List[str]:
        if not isinstance(self.document, dict):
            return []
        candidates = []
        for key, value in self.document.items():
            if isinstance(value, (dict, list)):
                candidates.append(key)
        return candidates

    def _refresh_client(self) -> None:
        self.client = OllamaClient(
            base_url=self.server,
            model=self.model,
            show_thinking=self.show_thinking,
            save_thinking=self.save_thinking,
        )

    @staticmethod
    def _normalize_server(value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return DEFAULT_SERVER
        if "://" not in cleaned:
            cleaned = f"http://{cleaned}"
        return cleaned.rstrip("/")


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
    if document is not None and input_path:
        shell.document_path = input_path
    shell.start()


if __name__ == "__main__":
    main()
