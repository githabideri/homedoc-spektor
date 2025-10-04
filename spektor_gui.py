"""Tkinter-based GUI wrapper for the Spektor CLI."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from typing import Callable
from tkinter import filedialog, messagebox, scrolledtext, ttk
from urllib.parse import urlparse, urlunparse

try:
    from spektor.llm import DEFAULT_BASE_URL, DEFAULT_MODEL
except Exception:  # pragma: no cover - import fallback for partial installs
    DEFAULT_BASE_URL = ""
    DEFAULT_MODEL = ""


def _default_server_port() -> int:
    try:
        parsed = urlparse(DEFAULT_BASE_URL)
        if parsed and parsed.port:
            return parsed.port
    except Exception:
        pass
    return 11434


DEFAULT_SERVER_PORT = _default_server_port()


SCRIPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spektor-cli.py")


class SpektorGUI:
    """Main application class for the Spektor Tkinter GUI."""

    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        master.title("Spektor CLI Helper")
        master.geometry("900x700")

        # Track background command execution state
        self._command_thread: threading.Thread | None = None

        # Tkinter variables for CLI flags
        cwd = os.getcwd()
        default_out_dir = os.path.join(cwd, "out")
        default_raw_dir = os.path.join(default_out_dir, "raw")
        default_document = os.path.join(default_out_dir, "system.json")
        self.action_var = tk.StringVar(value="collect")
        self.output_var = tk.StringVar(value=default_document)
        self.raw_dir_var = tk.StringVar(value=default_raw_dir)
        self.timeout_var = tk.StringVar(value="5")
        self.input_var = tk.StringVar(value=default_document)
        self.system_prompt_var = tk.StringVar()
        self.model_var = tk.StringVar(value=DEFAULT_MODEL or "")
        self.server_var = tk.StringVar(value=DEFAULT_BASE_URL or "")
        self.overview_var = tk.BooleanVar()
        self.json_only_var = tk.BooleanVar()
        self.show_thinking_var = tk.BooleanVar()
        self.save_thinking_var = tk.BooleanVar()
        self.debug_var = tk.BooleanVar()
        self.link_paths_var = tk.BooleanVar(value=True)

        # Widgets that require special handling (Text widgets do not support StringVar)
        self.section_text: tk.Text | None = None
        self.command_var = tk.StringVar()
        self.run_buttons: list[ttk.Button] = []

        # Layout
        self._build_layout()
        self._bind_updates()
        self.update_command_preview()

    # ------------------------------------------------------------------ UI setup
    def _build_layout(self) -> None:
        """Create and arrange all GUI widgets."""

        # Primary container with padding
        container = ttk.Frame(self.master, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        intro = ttk.Label(
            container,
            text=(
                "Follow the two-step workflow. Collect data first, then generate "
                "summaries from the saved file."
            ),
            wraplength=840,
            justify=tk.LEFT,
        )
        intro.pack(fill=tk.X, pady=(0, 10))

        collect_frame = ttk.LabelFrame(container, text="Step 1 – Collect system data")
        collect_frame.pack(fill=tk.X, pady=(0, 10))
        collect_frame.columnconfigure(1, weight=1)

        collect_header = ttk.Frame(collect_frame)
        collect_header.grid(row=0, column=0, columnspan=3, sticky=tk.EW, padx=6, pady=(6, 2))
        ttk.Label(
            collect_header,
            text="Gather the machine information and store it locally.",
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            collect_header,
            text="Preview Step 1 command",
            variable=self.action_var,
            value="collect",
            command=self._on_action_change,
        ).pack(side=tk.RIGHT)

        self._add_labeled_entry(
            collect_frame,
            "Collected data file (--output)",
            self.output_var,
            1,
            browse_command=lambda: self._browse_save_file(self.output_var),
        )
        self._add_labeled_entry(
            collect_frame,
            "Raw command output directory (--raw-dir)",
            self.raw_dir_var,
            2,
            browse_command=lambda: self._browse_directory(self.raw_dir_var),
        )

        ttk.Label(collect_frame, text="Command timeout (--timeout)").grid(
            row=3, column=0, sticky=tk.W, padx=6, pady=4
        )
        timeout_spin = ttk.Spinbox(
            collect_frame, from_=1, to=3600, textvariable=self.timeout_var, width=7
        )
        timeout_spin.grid(row=3, column=1, sticky=tk.W, padx=6, pady=4)
        self.timeout_spin = timeout_spin

        ttk.Label(
            collect_frame,
            text="Run this step first to create the summary input file.",
        ).grid(row=4, column=0, columnspan=3, sticky=tk.W, padx=6, pady=(4, 6))

        report_frame = ttk.LabelFrame(container, text="Step 2 – Generate summaries")
        report_frame.pack(fill=tk.X, pady=(0, 10))
        report_frame.columnconfigure(1, weight=1)

        report_header = ttk.Frame(report_frame)
        report_header.grid(row=0, column=0, columnspan=3, sticky=tk.EW, padx=6, pady=(6, 2))
        ttk.Label(
            report_header,
            text="Use the collected data to ask the LLM for summaries.",
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            report_header,
            text="Preview Step 2 command",
            variable=self.action_var,
            value="report",
            command=self._on_action_change,
        ).pack(side=tk.RIGHT)

        self._add_labeled_entry(
            report_frame,
            "Summary input file (--input)",
            self.input_var,
            1,
            browse_command=lambda: self._browse_file(self.input_var),
        )
        ttk.Button(
            report_frame,
            text="Use Step 1 output",
            command=self._use_collect_output_for_report,
        ).grid(row=1, column=2, sticky=tk.W, padx=6, pady=4)

        ttk.Checkbutton(
            report_frame,
            text="Keep Step 2 input in sync with Step 1 output",
            variable=self.link_paths_var,
            command=self._sync_input_with_output,
        ).grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=6, pady=(0, 4))

        ttk.Label(report_frame, text="Summary sections (--section per line)").grid(
            row=3, column=0, sticky=tk.W, padx=6, pady=(6, 2)
        )
        section_text = tk.Text(report_frame, height=4, width=40)
        section_text.grid(row=4, column=0, columnspan=3, sticky=tk.EW, padx=6, pady=(0, 6))
        section_text.bind("<KeyRelease>", lambda _event: self.update_command_preview())
        self.section_text = section_text

        options_frame = ttk.LabelFrame(
            container, text="Reporting and diagnostic options"
        )
        options_frame.pack(fill=tk.X, pady=(0, 10))
        for column in range(3):
            options_frame.columnconfigure(column, weight=1)

        ttk.Checkbutton(
            options_frame,
            text="Include overview (--overview)",
            variable=self.overview_var,
            command=self.update_command_preview,
        ).grid(row=0, column=0, sticky=tk.W, padx=6, pady=2)
        ttk.Checkbutton(
            options_frame,
            text="Only emit JSON (--json-only)",
            variable=self.json_only_var,
            command=self.update_command_preview,
        ).grid(row=0, column=1, sticky=tk.W, padx=6, pady=2)
        ttk.Checkbutton(
            options_frame,
            text="Show thinking (--show-thinking)",
            variable=self.show_thinking_var,
            command=self.update_command_preview,
        ).grid(row=0, column=2, sticky=tk.W, padx=6, pady=2)
        ttk.Checkbutton(
            options_frame,
            text="Save thinking (--save-thinking)",
            variable=self.save_thinking_var,
            command=self.update_command_preview,
        ).grid(row=1, column=0, sticky=tk.W, padx=6, pady=2)
        ttk.Checkbutton(
            options_frame,
            text="Debug mode (--debug)",
            variable=self.debug_var,
            command=self.update_command_preview,
        ).grid(row=1, column=1, sticky=tk.W, padx=6, pady=2)

        llm_frame = ttk.LabelFrame(container, text="LLM configuration")
        llm_frame.pack(fill=tk.X, pady=(0, 10))
        llm_frame.columnconfigure(1, weight=1)

        self._add_labeled_entry(
            llm_frame,
            "System prompt (--system-prompt)",
            self.system_prompt_var,
            0,
            browse_command=lambda: self._browse_file(self.system_prompt_var),
        )

        model_label = "Model name (--model)"
        if DEFAULT_MODEL:
            model_label += f" [default: {DEFAULT_MODEL}]"
        self._add_labeled_entry(llm_frame, model_label, self.model_var, 1)

        server_label = "Server URL (--server)"
        if DEFAULT_BASE_URL:
            server_label += f" [default: {DEFAULT_BASE_URL}]"
        server_entry = self._add_labeled_entry(llm_frame, server_label, self.server_var, 2)
        server_entry.bind("<FocusOut>", lambda _event: self._normalize_server_field())

        action_buttons = ttk.Frame(container)
        action_buttons.pack(fill=tk.X, pady=(0, 10))

        collect_button = ttk.Button(
            action_buttons,
            text="Run Step 1 (collect)",
            command=lambda: self._run_with_action("collect"),
        )
        collect_button.pack(side=tk.LEFT, padx=6)
        self.run_buttons.append(collect_button)

        report_button = ttk.Button(
            action_buttons,
            text="Run Step 2 (summaries)",
            command=lambda: self._run_with_action("report"),
        )
        report_button.pack(side=tk.LEFT, padx=6)
        self.run_buttons.append(report_button)

        ttk.Button(action_buttons, text="Clear output", command=self._clear_output).pack(
            side=tk.LEFT, padx=6
        )

        output_frame = ttk.LabelFrame(container, text="Console output")
        output_frame.pack(fill=tk.BOTH, expand=True)
        self.output_display = scrolledtext.ScrolledText(
            output_frame,
            wrap=tk.WORD,
            height=16,
        )
        self.output_display.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        command_frame = ttk.LabelFrame(container, text="CLI preview")
        command_frame.pack(fill=tk.X, pady=(0, 0))

        command_entry = ttk.Entry(
            command_frame, textvariable=self.command_var, state="readonly"
        )
        command_entry.pack(fill=tk.X, padx=6, pady=6)

        ttk.Button(command_frame, text="Copy command", command=self._copy_command).pack(
            anchor=tk.E, padx=6, pady=(0, 6)
        )

        self._on_action_change()

    def _add_labeled_entry(
        self,
        parent: ttk.LabelFrame,
        label: str,
        variable: tk.StringVar,
        row: int,
        browse_command: Callable[[], None] | None = None,
    ) -> ttk.Entry:
        """Create a labeled entry with an optional browse button."""

        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, padx=6, pady=4)
        entry = ttk.Entry(parent, textvariable=variable, width=50)
        entry.grid(row=row, column=1, sticky=tk.EW, padx=6, pady=4)
        parent.columnconfigure(1, weight=1)
        if browse_command:
            ttk.Button(parent, text="Browse", command=browse_command).grid(
                row=row, column=2, padx=6, pady=4
            )
        return entry

    # ----------------------------------------------------------------- UI helpers
    def _bind_updates(self) -> None:
        """Attach change listeners to StringVar based inputs."""

        def _refresh(*_args: object) -> None:
            self.update_command_preview()

        for var in (
            self.raw_dir_var,
            self.timeout_var,
            self.input_var,
            self.system_prompt_var,
            self.model_var,
        ):
            var.trace_add("write", _refresh)

        self.output_var.trace_add("write", lambda *_args: self._on_output_changed())
        self.server_var.trace_add("write", _refresh)
        self.link_paths_var.trace_add("write", lambda *_args: self._sync_input_with_output())

    def _on_action_change(self) -> None:
        """Adjust the UI when the primary action changes."""

        action = self.action_var.get()
        # Timeout is only relevant for collection
        timeout_state = tk.NORMAL if action == "collect" else tk.DISABLED
        self.timeout_spin.configure(state=timeout_state)
        if self.section_text is not None:
            section_state = tk.NORMAL if action == "report" else tk.DISABLED
            self.section_text.configure(state=section_state)
        self.update_command_preview()

    def _on_output_changed(self) -> None:
        """Update related fields when the collect output path changes."""

        if self.link_paths_var.get():
            self.input_var.set(self.output_var.get())
        self.update_command_preview()

    def _sync_input_with_output(self) -> None:
        """Keep the report input aligned with the collect output when requested."""

        if self.link_paths_var.get():
            self.input_var.set(self.output_var.get())

    def _use_collect_output_for_report(self) -> None:
        """Copy the Step 1 output path to the Step 2 input field."""

        self.input_var.set(self.output_var.get())

    # ---------------------------------------------------------------- Command building
    def _collect_sections(self) -> list[str]:
        if self.section_text is None or self.action_var.get() != "report":
            return []
        text = self.section_text.get("1.0", tk.END).strip()
        if not text:
            return []
        sections = [line.strip() for line in text.splitlines() if line.strip()]
        return sections

    def build_cli_args(self) -> list[str]:
        """Create a list of CLI arguments based on the current UI state."""

        args: list[str] = []
        action = self.action_var.get()
        if action == "collect":
            args.append("--collect")
            output_path = self.output_var.get().strip()
            if output_path:
                args.extend(["--output", output_path])
            raw_dir = self.raw_dir_var.get().strip()
            if raw_dir:
                args.extend(["--raw-dir", raw_dir])
            timeout_value = self.timeout_var.get().strip()
            if timeout_value:
                args.extend(["--timeout", timeout_value])
        elif action == "report":
            args.append("--report")
            input_path = self.input_var.get().strip()
            if input_path:
                args.extend(["--input", input_path])
            if self.overview_var.get():
                args.append("--overview")
            sections = self._collect_sections()
            for section in sections:
                args.extend(["--section", section])
            if self.json_only_var.get():
                args.append("--json-only")
            system_prompt = self.system_prompt_var.get().strip()
            if system_prompt:
                args.extend(["--system-prompt", system_prompt])
            model_value = self.model_var.get().strip()
            if model_value:
                args.extend(["--model", model_value])
            server_value = self._normalized_server_value()
            if server_value:
                args.extend(["--server", server_value])
            if self.show_thinking_var.get():
                args.append("--show-thinking")
            if self.save_thinking_var.get():
                args.append("--save-thinking")

        if self.debug_var.get():
            args.append("--debug")

        return args

    def _build_command_text(self) -> str:
        args = self.build_cli_args()
        quoted = [shlex.quote(arg) for arg in args]
        if not quoted:
            return "spektor"
        return "spektor " + " ".join(quoted)

    def _normalized_server_value(self) -> str:
        """Normalise the server input and ensure a default port is present."""

        value = self.server_var.get().strip()
        if not value:
            return ""

        url = value if "://" in value else f"http://{value}"
        parsed = urlparse(url)

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
            netloc = f"{netloc}:{DEFAULT_SERVER_PORT}"
            parsed = parsed._replace(netloc=netloc)

        normalized = urlunparse(parsed)
        return normalized.rstrip("/")

    def update_command_preview(self) -> None:
        """Refresh the command preview entry."""

        self.command_var.set(self._build_command_text())

    def _normalize_server_field(self) -> None:
        """Normalise the server entry widget value."""

        normalized = self._normalized_server_value()
        raw_value = self.server_var.get()
        current = raw_value.strip()
        if normalized != current or raw_value != current:
            self.server_var.set(normalized)
        else:
            self.update_command_preview()

    def _set_run_buttons_state(self, state: str) -> None:
        """Enable or disable all run buttons consistently."""

        for button in self.run_buttons:
            button.configure(state=state)

    def _run_with_action(self, action: str) -> None:
        """Set the active action and execute it."""

        self.action_var.set(action)
        self._on_action_change()
        self.run_command()

    # ---------------------------------------------------------------- Command execution
    def run_command(self) -> None:
        """Execute the assembled CLI command in a background thread."""

        if self._command_thread and self._command_thread.is_alive():
            messagebox.showinfo("Spektor", "A command is already running. Please wait.")
            return

        self._normalize_server_field()
        args = self.build_cli_args()
        action = self.action_var.get()

        if action == "report" and not self.input_var.get().strip():
            messagebox.showerror(
                "Spektor", "--report requires an input JSON file."
            )
            return

        if action == "collect" and not self.timeout_var.get().strip():
            self.timeout_var.set("5")
            args = self.build_cli_args()

        command = [sys.executable, SCRIPT_PATH] + args

        self._append_output(f"$ {' '.join(shlex.quote(part) for part in command)}\n")
        self._set_run_buttons_state(tk.DISABLED)

        def _execute() -> None:
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                output_parts = []
                if completed.stdout:
                    output_parts.append(completed.stdout)
                if completed.stderr:
                    output_parts.append("[stderr]\n" + completed.stderr)
                if not output_parts:
                    output_parts.append("(no output)")
                output_parts.append(f"[exit code {completed.returncode}]")
                output = "\n".join(output_parts)
                self.master.after(0, lambda: self._append_output(output + "\n"))
            except FileNotFoundError:
                self.master.after(0, lambda: messagebox.showerror(
                    "Spektor",
                    "Unable to locate spektor-cli.py. Ensure the script is in the same directory as this GUI.",
                ))
            except Exception as exc:  # pragma: no cover - GUI safety net
                self.master.after(0, lambda: messagebox.showerror("Spektor", f"Command failed: {exc}"))
            finally:
                self.master.after(0, lambda: self._set_run_buttons_state(tk.NORMAL))

        self._command_thread = threading.Thread(target=_execute, daemon=True)
        self._command_thread.start()

    # ---------------------------------------------------------------- Utility helpers
    def _clear_output(self) -> None:
        self.output_display.delete("1.0", tk.END)

    def _append_output(self, text: str) -> None:
        if not text:
            return

        lines = text.splitlines()
        if not lines:
            lines = [""]
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
        for line in lines:
            self.output_display.insert(tk.END, f"{timestamp}{line}\n")
        self.output_display.see(tk.END)

    def _copy_command(self) -> None:
        command_text = self.command_var.get()
        self.master.clipboard_clear()
        self.master.clipboard_append(command_text)

    def _browse_file(self, variable: tk.StringVar) -> None:
        filename = filedialog.askopenfilename()
        if filename:
            variable.set(filename)

    def _browse_save_file(self, variable: tk.StringVar) -> None:
        filename = filedialog.asksaveasfilename(defaultextension=".json")
        if filename:
            variable.set(filename)

    def _browse_directory(self, variable: tk.StringVar) -> None:
        directory = filedialog.askdirectory()
        if directory:
            variable.set(directory)


def main() -> None:
    root = tk.Tk()
    SpektorGUI(root)
    root.mainloop()


if __name__ == "__main__":  # pragma: no cover - GUI entry point
    main()
