"""Tkinter-based GUI wrapper for the Spektor CLI."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
import tkinter as tk
from typing import Callable
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    from spektor.llm import DEFAULT_BASE_URL, DEFAULT_MODEL
except Exception:  # pragma: no cover - import fallback for partial installs
    DEFAULT_BASE_URL = ""
    DEFAULT_MODEL = ""


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
        self.model_var = tk.StringVar()
        self.server_var = tk.StringVar()
        self.overview_var = tk.BooleanVar()
        self.json_only_var = tk.BooleanVar()
        self.show_thinking_var = tk.BooleanVar()
        self.save_thinking_var = tk.BooleanVar()
        self.debug_var = tk.BooleanVar()

        # Widgets that require special handling (Text widgets do not support StringVar)
        self.section_text: tk.Text | None = None

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

        # Action selection frame
        action_frame = ttk.LabelFrame(container, text="Workflow")
        action_frame.pack(fill=tk.X, pady=(0, 10))

        actions = (
            ("Step 1: Collect system information (--collect)", "collect"),
            ("Step 2: Generate summaries (--report)", "report"),
        )
        for text, value in actions:
            ttk.Radiobutton(action_frame, text=text, variable=self.action_var, value=value,
                            command=self._on_action_change).pack(anchor=tk.W, padx=6, pady=2)

        # Paths and document options
        doc_frame = ttk.LabelFrame(container, text="Document and collection options")
        doc_frame.pack(fill=tk.X, pady=(0, 10))

        self._add_labeled_entry(
            doc_frame,
            "Step 2 input JSON (--input)",
            self.input_var,
            0,
            browse_command=lambda: self._browse_file(self.input_var),
        )
        self._add_labeled_entry(
            doc_frame,
            "Step 1 output file (--output)",
            self.output_var,
            1,
                                browse_command=lambda: self._browse_save_file(self.output_var))
        self._add_labeled_entry(doc_frame, "Raw directory (--raw-dir)", self.raw_dir_var, 2,
                                browse_command=lambda: self._browse_directory(self.raw_dir_var))

        ttk.Label(doc_frame, text="Command timeout (--timeout)").grid(row=3, column=0, sticky=tk.W, padx=6, pady=4)
        timeout_spin = ttk.Spinbox(doc_frame, from_=1, to=3600, textvariable=self.timeout_var, width=7)
        timeout_spin.grid(row=3, column=1, sticky=tk.W, padx=6, pady=4)
        self.timeout_spin = timeout_spin
        ttk.Label(
            doc_frame,
            text="Start with Step 1 to create the JSON file, then reuse it as the Step 2 input.",
        ).grid(row=4, column=0, columnspan=3, sticky=tk.W, padx=6, pady=(4, 0))

        # Reporting options
        report_frame = ttk.LabelFrame(container, text="Reporting options")
        report_frame.pack(fill=tk.BOTH, pady=(0, 10))

        ttk.Checkbutton(report_frame, text="Include overview (--overview)",
                        variable=self.overview_var, command=self.update_command_preview).grid(
            row=0, column=0, sticky=tk.W, padx=6, pady=2)
        ttk.Checkbutton(report_frame, text="Only emit JSON (--json-only)",
                        variable=self.json_only_var, command=self.update_command_preview).grid(
            row=0, column=1, sticky=tk.W, padx=6, pady=2)

        ttk.Label(report_frame, text="Sections (--section per line)").grid(
            row=1, column=0, sticky=tk.W, padx=6, pady=(6, 2))
        section_text = tk.Text(report_frame, height=4, width=40)
        section_text.grid(row=2, column=0, columnspan=2, sticky=tk.EW, padx=6, pady=(0, 6))
        report_frame.columnconfigure(0, weight=1)
        report_frame.columnconfigure(1, weight=1)
        section_text.bind("<KeyRelease>", lambda _event: self.update_command_preview())
        self.section_text = section_text

        # LLM configuration
        llm_frame = ttk.LabelFrame(container, text="LLM configuration")
        llm_frame.pack(fill=tk.X, pady=(0, 10))

        self._add_labeled_entry(llm_frame, "System prompt (--system-prompt)", self.system_prompt_var, 0,
                                browse_command=lambda: self._browse_file(self.system_prompt_var))
        model_label = "Model name (--model)"
        if DEFAULT_MODEL:
            model_label += f" [default: {DEFAULT_MODEL}]"
        self._add_labeled_entry(llm_frame, model_label, self.model_var, 1)

        server_label = "Server URL (--server)"
        if DEFAULT_BASE_URL:
            server_label += f" [default: {DEFAULT_BASE_URL}]"
        self._add_labeled_entry(llm_frame, server_label, self.server_var, 2)

        ttk.Checkbutton(llm_frame, text="Show thinking (--show-thinking)",
                        variable=self.show_thinking_var, command=self.update_command_preview).grid(
            row=3, column=0, sticky=tk.W, padx=6, pady=2)
        ttk.Checkbutton(llm_frame, text="Save thinking (--save-thinking)",
                        variable=self.save_thinking_var, command=self.update_command_preview).grid(
            row=3, column=1, sticky=tk.W, padx=6, pady=2)
        ttk.Checkbutton(llm_frame, text="Debug mode (--debug)",
                        variable=self.debug_var, command=self.update_command_preview).grid(
            row=3, column=2, sticky=tk.W, padx=6, pady=2)

        # Command preview and execution controls
        command_frame = ttk.LabelFrame(container, text="Equivalent CLI command")
        command_frame.pack(fill=tk.X, pady=(0, 10))

        self.command_var = tk.StringVar()
        command_entry = ttk.Entry(command_frame, textvariable=self.command_var, state="readonly")
        command_entry.pack(fill=tk.X, padx=6, pady=6)

        ttk.Button(command_frame, text="Copy command", command=self._copy_command).pack(
            anchor=tk.E, padx=6, pady=(0, 6)
        )

        action_buttons = ttk.Frame(container)
        action_buttons.pack(fill=tk.X, pady=(0, 10))

        self.run_button = ttk.Button(action_buttons, text="Run", command=self.run_command)
        self.run_button.pack(side=tk.LEFT, padx=6)

        ttk.Button(action_buttons, text="Clear output", command=self._clear_output).pack(side=tk.LEFT, padx=6)

        # Output display
        output_frame = ttk.LabelFrame(container, text="Command output")
        output_frame.pack(fill=tk.BOTH, expand=True)

        self.output_display = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, height=12)
        self.output_display.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self._on_action_change()

    def _add_labeled_entry(
        self,
        parent: ttk.LabelFrame,
        label: str,
        variable: tk.StringVar,
        row: int,
        browse_command: Callable[[], None] | None = None,
    ) -> None:
        """Create a labeled entry with an optional browse button."""

        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, padx=6, pady=4)
        entry = ttk.Entry(parent, textvariable=variable, width=50)
        entry.grid(row=row, column=1, sticky=tk.EW, padx=6, pady=4)
        parent.columnconfigure(1, weight=1)
        if browse_command:
            ttk.Button(parent, text="Browse", command=browse_command).grid(row=row, column=2, padx=6, pady=4)

    # ----------------------------------------------------------------- UI helpers
    def _bind_updates(self) -> None:
        """Attach change listeners to StringVar based inputs."""

        for var in (
            self.output_var,
            self.raw_dir_var,
            self.timeout_var,
            self.input_var,
            self.system_prompt_var,
            self.model_var,
            self.server_var,
        ):
            var.trace_add("write", lambda *_args: self.update_command_preview())

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
            if self.output_var.get():
                args.extend(["--output", self.output_var.get()])
            if self.raw_dir_var.get():
                args.extend(["--raw-dir", self.raw_dir_var.get()])
            if self.timeout_var.get():
                args.extend(["--timeout", self.timeout_var.get()])
        elif action == "report":
            args.append("--report")
            if self.input_var.get():
                args.extend(["--input", self.input_var.get()])
            if self.overview_var.get():
                args.append("--overview")
            sections = self._collect_sections()
            for section in sections:
                args.extend(["--section", section])
            if self.json_only_var.get():
                args.append("--json-only")
            if self.system_prompt_var.get():
                args.extend(["--system-prompt", self.system_prompt_var.get()])
            if self.model_var.get():
                args.extend(["--model", self.model_var.get()])
            if self.server_var.get():
                args.extend(["--server", self.server_var.get()])
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

    def update_command_preview(self) -> None:
        """Refresh the command preview entry."""

        self.command_var.set(self._build_command_text())

    # ---------------------------------------------------------------- Command execution
    def run_command(self) -> None:
        """Execute the assembled CLI command in a background thread."""

        if self._command_thread and self._command_thread.is_alive():
            messagebox.showinfo("Spektor", "A command is already running. Please wait.")
            return

        args = self.build_cli_args()
        action = self.action_var.get()

        if action == "report" and not self.input_var.get():
            messagebox.showerror(
                "Spektor", "--report requires an input JSON file."
            )
            return

        if action == "collect" and not self.timeout_var.get():
            self.timeout_var.set("5")
            args = self.build_cli_args()

        command = [sys.executable, SCRIPT_PATH] + args

        self._append_output(f"$ {' '.join(shlex.quote(part) for part in command)}\n")
        self.run_button.configure(state=tk.DISABLED)

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
                self.master.after(0, lambda: self.run_button.configure(state=tk.NORMAL))

        self._command_thread = threading.Thread(target=_execute, daemon=True)
        self._command_thread.start()

    # ---------------------------------------------------------------- Utility helpers
    def _clear_output(self) -> None:
        self.output_display.delete("1.0", tk.END)

    def _append_output(self, text: str) -> None:
        self.output_display.insert(tk.END, text)
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
