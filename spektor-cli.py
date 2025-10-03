"""Command line interface for the Spektor toolkit."""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, List

from spektor.interactive import main as interactive_main
from spektor.llm import DEFAULT_BASE_URL, DEFAULT_MODEL, OllamaClient
from spektor.reporting import answer_query, overview, per_section
from spektor.sysprobe import collect as collect_probe
from spektor.util import safe_json_dump


def _load_document(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _save_document(path: str, document: Dict[str, Any]) -> None:
    safe_json_dump(document, path)


def _resolve_system_prompt(value: str | None) -> str:
    if not value:
        return ""
    if os.path.exists(value):
        with open(value, "r", encoding="utf-8") as fh:
            return fh.read()
    return value


def _create_client(args: argparse.Namespace) -> OllamaClient:
    return OllamaClient(
        base_url=args.server or DEFAULT_BASE_URL,
        model=args.model or DEFAULT_MODEL,
        show_thinking=args.show_thinking,
        save_thinking=args.save_thinking,
        debug=args.debug,
    )


def handle_collect(args: argparse.Namespace) -> int:
    document = collect_probe(debug=args.debug, raw_dir=args.raw_dir, timeout=args.timeout)
    if args.output:
        _save_document(args.output, document)
    else:
        print(json.dumps(document, ensure_ascii=False, indent=2))
    return 0


def handle_report(args: argparse.Namespace) -> int:
    document = _load_document(args.input)
    if args.json_only:
        print(json.dumps(document, ensure_ascii=False, indent=2))
        return 0
    client = _create_client(args)
    system_prompt = _resolve_system_prompt(args.system_prompt)
    responses: List[str] = []
    if args.overview:
        responses.append(
            overview(
                document,
                client,
                system_override=system_prompt or None,
                show_thinking=args.show_thinking,
                save_thinking=args.save_thinking,
            ).text
        )
    if args.section:
        responses.append(
            per_section(
                document,
                args.section,
                client,
                system_override=system_prompt or None,
                show_thinking=args.show_thinking,
                save_thinking=args.save_thinking,
            ).text
        )
    if not responses:
        responses.append(
            overview(
                document,
                client,
                system_override=system_prompt or None,
                show_thinking=args.show_thinking,
                save_thinking=args.save_thinking,
            ).text
        )
    print("\n\n".join(responses))
    return 0


def handle_query(args: argparse.Namespace) -> int:
    document = _load_document(args.input)
    if args.json_only:
        print(json.dumps(document, ensure_ascii=False, indent=2))
        return 0
    client = _create_client(args)
    question_parts = args.question or []
    question = " ".join(question_parts).strip()
    if not question:
        print("A question is required. Provide one with --question.")
        return 1
    response = answer_query(
        document,
        question,
        client,
        system_override=_resolve_system_prompt(args.system_prompt) or None,
        show_thinking=args.show_thinking,
        save_thinking=args.save_thinking,
    )
    print(response.text)
    return 0


def handle_interactive(args: argparse.Namespace) -> int:
    interactive_main(input_path=args.input, model=args.model, server=args.server)
    return 0


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spektor")

    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--collect",
        action="store_true",
        help="Collect system information from the current machine",
    )
    actions.add_argument(
        "--report",
        action="store_true",
        help="Generate an LLM assisted report from a JSON document",
    )
    actions.add_argument(
        "--question",
        nargs="+",
        metavar="WORD",
        help="Ask an ad-hoc question about a JSON document",
    )
    actions.add_argument(
        "--interactive",
        action="store_true",
        help="Launch the interactive shell",
    )

    parser.add_argument("--output", help="Destination file for --collect JSON output")
    parser.add_argument(
        "--raw-dir", help="Directory for raw command output when using --collect"
    )
    parser.add_argument(
        "--timeout", type=int, default=5, help="Command timeout seconds for --collect"
    )
    parser.add_argument("--input", help="Path to an existing JSON document")
    parser.add_argument(
        "--overview",
        action="store_true",
        help="Include the system overview when using --report",
    )
    parser.add_argument(
        "--section",
        action="append",
        metavar="NAME",
        help="Analyse a named section; repeat for multiple sections",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print raw JSON instead of calling the LLM",
    )
    parser.add_argument(
        "--system-prompt",
        help="Override the system prompt (path or text) for LLM operations",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model name")
    parser.add_argument("--server", default=DEFAULT_BASE_URL, help="Ollama server URL")
    parser.add_argument(
        "--show-thinking",
        action="store_true",
        help="Display <thinking> blocks from the LLM",
    )
    parser.add_argument(
        "--save-thinking",
        action="store_true",
        help="Persist raw LLM responses to disk",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug capture for collectors or LLM calls",
    )

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.collect:
        return handle_collect(args)

    if args.report:
        if not args.input:
            parser.error("--report requires --input")
        return handle_report(args)

    if args.question is not None:
        if not args.input:
            parser.error("--question requires --input")
        return handle_query(args)

    if args.interactive:
        return handle_interactive(args)

    # Default to the interactive shell when no action is provided.
    return handle_interactive(args)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
