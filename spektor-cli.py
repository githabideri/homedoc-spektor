"""Command line interface for the Spektor toolkit."""

from __future__ import annotations

import argparse
import json
import os
import sys
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
    question = " ".join(args.question).strip()
    if not question:
        print("A question is required for the query command.")
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
    subparsers = parser.add_subparsers(dest="command")

    collect_p = subparsers.add_parser("collect", help="Collect system information")
    collect_p.add_argument("--output", help="Destination file for JSON output")
    collect_p.add_argument("--debug", action="store_true", help="Enable debug artifact capture")
    collect_p.add_argument("--raw-dir", help="Directory for raw command output")
    collect_p.add_argument("--timeout", type=int, default=5, help="Command timeout seconds")
    collect_p.set_defaults(func=handle_collect)

    common_llm = {
        "--model": {"default": DEFAULT_MODEL, "help": "Ollama model name"},
        "--server": {"default": DEFAULT_BASE_URL, "help": "Ollama server URL"},
        "--show-thinking": {"action": "store_true", "help": "Display <thinking> blocks"},
        "--save-thinking": {"action": "store_true", "help": "Persist raw responses"},
        "--debug": {"action": "store_true", "help": "Enable debug capture"},
    }

    report_p = subparsers.add_parser("report", help="Generate LLM assisted report")
    report_p.add_argument("--input", required=True, help="Path to JSON document")
    report_p.add_argument("--overview", action="store_true", help="Include system overview")
    report_p.add_argument("--section", action="append", help="Analyse named section", metavar="NAME")
    report_p.add_argument("--json-only", action="store_true", help="Print JSON and skip LLM")
    report_p.add_argument("--system-prompt", help="Override system prompt (path or text)")
    for flag, options in common_llm.items():
        report_p.add_argument(flag, **options)
    report_p.set_defaults(func=handle_report)

    query_p = subparsers.add_parser("query", help="Answer ad-hoc question")
    query_p.add_argument("--input", required=True, help="Path to JSON document")
    query_p.add_argument("--json-only", action="store_true")
    query_p.add_argument("--system-prompt", help="Override system prompt (path or text)")
    for flag, options in common_llm.items():
        query_p.add_argument(flag, **options)
    query_p.add_argument("question", nargs=argparse.REMAINDER, help="Question to answer")
    query_p.set_defaults(func=handle_query)

    interactive_p = subparsers.add_parser("interactive", help="Start interactive shell")
    interactive_p.add_argument("--input", help="Load JSON document on start")
    interactive_p.add_argument("--model", default=DEFAULT_MODEL)
    interactive_p.add_argument("--server", default=DEFAULT_BASE_URL)
    interactive_p.set_defaults(func=handle_interactive)

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)
    if not args.command:
        interactive_main()
        return 0
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return func(args)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
