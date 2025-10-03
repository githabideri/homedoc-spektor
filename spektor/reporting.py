"""High level reporting utilities backed by the Ollama client."""

from __future__ import annotations

import copy
import json
from typing import Iterable

from .llm import OllamaClient

_SYSTEM = (
    "Use ONLY provided JSON. If missing, state what to run to obtain it. "
    "Bullet points. Reference JSON paths."
)


def _compact(doc: dict, max_pkgs: int = 100) -> dict:
    compacted = copy.deepcopy(doc)
    try:
        packages = compacted["software"]["packages"]
        items = packages.get("items", [])
        if isinstance(items, list) and len(items) > max_pkgs:
            remaining = len(items) - max_pkgs
            packages["items"] = items[:max_pkgs] + [f"(+{remaining} more)"]
            packages["truncated"] = True
    except KeyError:
        pass
    return compacted


def _render_json(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2)


def _call_llm(
    client: OllamaClient,
    prompt: str,
    task: str,
    *,
    system_override: str | None = None,
    show_thinking: bool | None = None,
    save_thinking: bool | None = None,
):
    system_prompt = system_override if system_override is not None else _SYSTEM
    return client.generate(
        prompt,
        system=system_prompt,
        task=task,
        show_thinking=show_thinking,
        save_thinking=save_thinking,
    )


def overview(
    doc: dict,
    client: OllamaClient,
    *,
    system_override: str | None = None,
    show_thinking: bool | None = None,
    save_thinking: bool | None = None,
):
    payload = _render_json(_compact(doc))
    prompt = (
        "Summarise hardware and software capabilities with constraints. "
        "Call out virtualization readiness, GPU status, storage, networking."
        "\n" + payload
    )
    return _call_llm(
        client,
        prompt,
        task="overview",
        system_override=system_override,
        show_thinking=show_thinking,
        save_thinking=save_thinking,
    )


def per_section(
    doc: dict,
    sections: Iterable[str],
    client: OllamaClient,
    *,
    system_override: str | None = None,
    show_thinking: bool | None = None,
    save_thinking: bool | None = None,
):
    payload = _render_json(_compact(doc))
    section_list = ", ".join(sections) if sections else "(all)"
    prompt = (
        f"Provide actionable checks for sections: {section_list}. "
        "Highlight missing data and remediation commands.\n" + payload
    )
    return _call_llm(
        client,
        prompt,
        task="section",
        system_override=system_override,
        show_thinking=show_thinking,
        save_thinking=save_thinking,
    )


def answer_query(
    doc: dict,
    question: str,
    client: OllamaClient,
    *,
    system_override: str | None = None,
    show_thinking: bool | None = None,
    save_thinking: bool | None = None,
):
    payload = _render_json(_compact(doc))
    prompt = f"Question: {question}\nAnswer strictly from JSON.\n{payload}"
    return _call_llm(
        client,
        prompt,
        task="query",
        system_override=system_override,
        show_thinking=show_thinking,
        save_thinking=save_thinking,
    )
