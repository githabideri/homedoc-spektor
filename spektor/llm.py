"""Ollama client wrapper with thinking controls and debug capture."""

from __future__ import annotations

import json
import os
import pathlib
import re
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse, urlunparse
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .util import now_iso, safe_json_dump, sha256_text

DEFAULT_MODEL = "gemma3:12b"
DEFAULT_BASE_URL = "http://localhost:11434"


def _default_port() -> int:
    try:
        parsed = urlparse(DEFAULT_BASE_URL)
        if parsed and parsed.port:
            return parsed.port
    except Exception:
        pass
    return 11434


DEFAULT_PORT = _default_port()
DEBUG_DIR = pathlib.Path("debug")


@dataclass
class OllamaResponse:
    text: str
    raw_text: str
    meta: Dict[str, Any]


def _strip_thinking(text: str) -> str:
    pattern = re.compile(r"<thinking>.*?</thinking>", re.DOTALL | re.IGNORECASE)
    return pattern.sub("", text)


def _sanitize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", value)


class OllamaClient:
    """Minimal Ollama HTTP client."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        *,
        show_thinking: Optional[bool] = None,
        save_thinking: Optional[bool] = None,
        debug: bool = False,
    ) -> None:
        cleaned_url = (base_url or DEFAULT_BASE_URL).strip()
        if "://" not in cleaned_url:
            cleaned_url = f"http://{cleaned_url}"

        parsed = urlparse(cleaned_url)
        if parsed.scheme in {"http", "https"} and parsed.hostname and parsed.port is None:
            host = parsed.hostname
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            netloc = host
            if parsed.username:
                auth = parsed.username
                if parsed.password:
                    auth += f":{parsed.password}"
                netloc = f"{auth}@{netloc}"
            netloc = f"{netloc}:{DEFAULT_PORT}"
            parsed = parsed._replace(netloc=netloc)
        cleaned_url = urlunparse(parsed)

        self.base_url = cleaned_url.rstrip("/")
        self.model = model
        self.debug = debug or os.environ.get("SPEKTOR_DEBUG_LLM") == "1"
        thinking_env = os.environ.get("SPEKTOR_THINKING", "").strip().lower()
        self.show_thinking = show_thinking if show_thinking is not None else thinking_env == "show"
        self.save_thinking = save_thinking if save_thinking is not None else thinking_env == "save"
        self.session_id = _sanitize(os.urandom(4).hex())
        if self.save_thinking or self.debug:
            DEBUG_DIR.mkdir(exist_ok=True)

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        task: str = "query",
        show_thinking: Optional[bool] = None,
        save_thinking: Optional[bool] = None,
    ) -> OllamaResponse:
        """Generate a completion using the configured Ollama endpoint."""

        show_think = self.show_thinking if show_thinking is None else show_thinking
        save_think = self.save_thinking if save_thinking is None else save_thinking

        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": True,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

        start_time = time.time()
        raw_lines: list[str] = []
        response_text_parts: list[str] = []
        http_status: Optional[int] = None
        meta_chunk: Dict[str, Any] = {}

        try:
            with urllib.request.urlopen(request) as resp:
                http_status = resp.status
                for raw in resp:
                    decoded = raw.decode("utf-8").strip()
                    if not decoded:
                        continue
                    raw_lines.append(decoded)
                    try:
                        chunk = json.loads(decoded)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("done"):
                        meta_chunk = chunk
                        break
                    part = chunk.get("response", "")
                    response_text_parts.append(part)
        except urllib.error.HTTPError as exc:  # pragma: no cover - depends on runtime server
            http_status = exc.code
            error_text = exc.read().decode("utf-8", errors="replace")
            raw_lines.append(error_text)
            response_text_parts.append(error_text)
        except urllib.error.URLError as exc:  # pragma: no cover - depends on runtime server
            error_text = str(exc)
            raw_lines.append(error_text)
            response_text_parts.append(error_text)

        duration = time.time() - start_time
        raw_text = "".join(response_text_parts)
        display_text = raw_text if show_think else _strip_thinking(raw_text)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        model_clean = _sanitize(self.model.replace(":", "-"))
        host = _sanitize(socket.gethostname())
        pid = os.getpid()

        debug_meta = {
            "model": self.model,
            "system_prompt_sha256": sha256_text(system or ""),
            "prompt_sha256": sha256_text(prompt),
            "http_status": http_status,
            "timings": {
                "started_at": now_iso(),
                "duration_seconds": duration,
            },
            "meta_chunk": meta_chunk,
        }

        if self.debug:
            DEBUG_DIR.mkdir(exist_ok=True)
            jsonl_path = DEBUG_DIR / f"ollama_{timestamp}_{self.session_id}.jsonl"
            with jsonl_path.open("w", encoding="utf-8") as fh:
                fh.write("\n".join(raw_lines))
                fh.write("\n")
            safe_json_dump(debug_meta, DEBUG_DIR / "ollama_meta.json")

        if save_think or self.debug:
            DEBUG_DIR.mkdir(exist_ok=True)
            raw_filename = DEBUG_DIR / f"{timestamp}_{model_clean}_{task}_{host}_{pid}.raw.txt"
            with raw_filename.open("w", encoding="utf-8") as fh:
                fh.write(raw_text)

        return OllamaResponse(text=display_text.strip(), raw_text=raw_text.strip(), meta=debug_meta)
