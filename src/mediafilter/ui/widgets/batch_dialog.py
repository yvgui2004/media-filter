"""Batch command dialog: pick a preset, generate per-file ffmpeg commands,
copy to clipboard, save as .bat, or run them in the background."""

from __future__ import annotations

import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
)

from ..dialog_base import (
    AppDialog,
    add_footer,
    count_label,
    dialog_button,
    hint_label,
    lede_label,
    message_box,
    mono_font,
    note_label,
    section_label,
)
from ..select_field import SelectField
from ...core.ffmpeg import Preset, build_command, build_output_path
from ...core.models import FileRecord

_OUTPUT_FORMATS = (("original", None), ("mp4", "mp4"), ("mkv", "mkv"),
                   ("mov", "mov"), ("webm", "webm"), ("flv", "flv"))


class CommandRunner(QThread):
    """Runs the generated commands sequentially; cancel terminates the current
    process and stops before the next starts."""

    line = Signal(str)
    finished = Signal(int, int)   # succeeded, failed
    aborted = Signal(int, int)    # succeeded, failed before cancel

    def __init__(self, commands: list[str], parent=None):
        super().__init__(parent)
        self._commands = commands
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        succeeded = failed = 0
        for cmd in self._commands:
            if self._cancel:
                break
            self.line.emit(f"> {cmd}")
            code, detail, cancelled = self._run_one(cmd)
            if cancelled:
                break
            if code == 0:
                succeeded += 1
                self.line.emit("  [exit 0]")
            else:
                failed += 1
                if code is None:
                    self.line.emit("  [launch failed]")
                else:
                    self.line.emit(f"  [exit {code}]")
                for text in detail:
                    self.line.emit(f"  {text}")
        if self._cancel:
            self.aborted.emit(succeeded, failed)
        else:
            self.finished.emit(succeeded, failed)

    def _run_one(self, cmd: str) -> tuple[int | None, list[str], bool]:
        """Run one command; return (exit code, stderr tail, cancelled)."""
        with tempfile.TemporaryFile() as err_file:
            try:
                proc = self._start(cmd, err_file)
            except (OSError, ValueError) as exc:
                self.line.emit(f"  [launch failed: {exc}]")
                return None, [], False

            stop_requested = False
            while proc.poll() is None:
                if self._cancel and not stop_requested:
                    proc.terminate()
                    stop_requested = True
                time.sleep(0.1)

            if stop_requested:
                # Reap the process before returning so no console window lingers.
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
                return proc.returncode, [], True

            err_file.seek(0)
            raw = err_file.read(16_000)
            detail = _stderr_tail(raw)
            return proc.returncode, detail, False

    @staticmethod
    def _start(cmd: str, err_file):
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": err_file}
        if sys.platform == "win32":
            # A string is passed to CreateProcess verbatim on Windows, so the
            # quotes around paths survive intact. shlex(posix=False) keeps the
            # quote characters and makes ffmpeg look for a filename that
            # literally starts with a quote -- every preset failed that way.
            return subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
                **kwargs,
            )
        return subprocess.Popen(shlex.split(cmd, posix=True), **kwargs)


def _stderr_tail(raw: bytes, limit: int = 8) -> list[str]:
    """Last few non-empty stderr lines, safe to show in the log pane."""
    text = raw.decode("utf-8", errors="replace")
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    return [line[:220] for line in lines[-limit:]]


class BatchCommandDialog(AppDialog):
    def __init__(
        self,
        records: list[FileRecord],
        tr,
        presets: list[Preset],
        parent=None,
        tokens: dict[str, str] | None = None,
    ):
        super().__init__(tokens, parent)
        self._records = records
        self._tr = tr
        self._presets = presets
        self._runner: CommandRunner | None = None

        self.setWindowTitle(tr("dialog.batch_title"))
        self.resize(780, 700)
        self.setMinimumSize(680, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        layout.addWidget(lede_label(tr("dialog.batch_lede", n=len(records))))

        # preset selector + functional annotation
        preset_box = QVBoxLayout()
        preset_box.setSpacing(8)
        preset_box.addWidget(section_label(tr("dialog.preset")))
        self._preset_combo = SelectField()
        self._preset_combo.set_tokens(self._tokens)
        self._preset_combo.set_accessible_label(tr("dialog.preset"))
        self._preset_combo.set_popup_width(360)
        preset_box.addWidget(self._preset_combo)
        self._preset_note = note_label()
        preset_box.addWidget(self._preset_note)
        layout.addLayout(preset_box)

        # command template
        template_head = QHBoxLayout()
        template_head.setSpacing(8)
        template_head.addWidget(section_label(tr("dialog.command")))
        template_head.addStretch(1)
        template_head.addWidget(hint_label(tr("dialog.template_hint")))
        layout.addLayout(template_head)
        self._template = QTextEdit()
        self._template.setObjectName("CodeInput")
        self._template.setAcceptRichText(False)
        self._template.setFixedHeight(96)
        self._template.setFont(mono_font(12))
        self._template.setAccessibleName(tr("dialog.command"))
        layout.addWidget(self._template)

        # output options
        out_row = QHBoxLayout()
        out_row.setSpacing(16)
        suffix_box = QVBoxLayout()
        suffix_box.setSpacing(8)
        suffix_box.addWidget(section_label(tr("dialog.output_suffix")))
        self._suffix = QLineEdit("_out")
        self._suffix.setObjectName("FieldInput")
        self._suffix.setFixedHeight(34)
        self._suffix.setAccessibleName(tr("dialog.output_suffix"))
        suffix_box.addWidget(self._suffix)
        out_row.addLayout(suffix_box, 2)

        ext_box = QVBoxLayout()
        ext_box.setSpacing(8)
        ext_box.addWidget(section_label(tr("dialog.output_ext")))
        self._ext_combo = SelectField()
        self._ext_combo.set_tokens(self._tokens)
        self._ext_combo.set_accessible_label(tr("dialog.output_ext"))
        self._ext_combo.set_popup_width(250)
        ext_box.addWidget(self._ext_combo)
        out_row.addLayout(ext_box, 3)
        layout.addLayout(out_row)

        # preview / progress log
        preview_head = QHBoxLayout()
        preview_head.setSpacing(8)
        preview_head.addWidget(section_label(tr("dialog.section_preview")))
        preview_head.addStretch(1)
        self._count = count_label()
        preview_head.addWidget(self._count)
        layout.addLayout(preview_head)
        self._log = QTextEdit()
        self._log.setObjectName("PreviewBox")
        self._log.setReadOnly(True)
        self._log.setFont(mono_font(12))
        self._log.setAccessibleName(tr("dialog.section_preview"))
        layout.addWidget(self._log, 1)

        # buttons
        self._copy_btn = dialog_button(tr("dialog.copy"), "primary")
        self._bat_btn = dialog_button(tr("dialog.save_bat"))
        self._run_btn = dialog_button(tr("dialog.run"))
        self._close_btn = dialog_button(tr("dialog.close"))
        add_footer(
            layout,
            [self._close_btn, self._bat_btn, self._run_btn, self._copy_btn],
        )

        self._preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        self._suffix.textChanged.connect(self._update_preview)
        self._ext_combo.currentIndexChanged.connect(self._update_preview)
        self._template.textChanged.connect(self._update_preview)
        self._copy_btn.clicked.connect(self._copy)
        self._bat_btn.clicked.connect(self._save_bat)
        self._run_btn.clicked.connect(self._run)
        self._close_btn.clicked.connect(self.reject)

        for p in presets:
            self._preset_combo.addItem(p.name)
        for key, _ext in _OUTPUT_FORMATS:
            self._ext_combo.addItem(_display_format(tr, key))
        # SelectField does not emit on addItem; seed the template explicitly.
        self._on_preset_changed()

    # -- helpers ---------------------------------------------------------

    @property
    def _current_preset(self) -> Preset | None:
        i = self._preset_combo.currentIndex()
        return self._presets[i] if 0 <= i < len(self._presets) else None

    def _preset_description(self, preset: Preset) -> str:
        key = f"preset.{preset.key}.desc"
        text = self._tr(key)
        return preset.description if text == key else text

    def _output_extension(self) -> str | None:
        return _OUTPUT_FORMATS[self._ext_combo.currentIndex()][1]

    def _commands(self) -> list[str]:
        preset = self._current_preset
        if preset is None:
            return []
        template = self._template.toPlainText().strip()
        suffix = self._suffix.text().strip() or "_out"
        ext = self._output_extension()
        commands = []
        for rec in self._records:
            out = build_output_path(rec.path, suffix, ext)
            commands.append(build_command(template, rec.path, out))
        return commands

    def _update_preview(self):
        commands = self._commands()
        self._log.setPlainText("\n\n".join(commands))
        self._count.setText(self._tr("dialog.command_count", n=len(commands)))

    def _on_preset_changed(self, _index: int = 0):
        preset = self._current_preset
        if preset is not None:
            self._template.setPlainText(preset.template)
            self._suffix.setText(f"_{preset.key}")
            self._preset_note.setText(self._preset_description(preset))
        self._update_preview()

    # -- actions ---------------------------------------------------------

    def _copy(self):
        commands = self._commands()
        if not commands:
            message_box(self, "info", self._tr("app.title"),
                                    self._tr("msg.nothing_selected"))
            return
        QGuiApplication.clipboard().setText("\n\n".join(commands))
        self._log.append(self._tr("msg.copied", n=len(commands)))

    def _save_bat(self):
        commands = self._commands()
        if not commands:
            return
        path, _ = QFileDialog.getSaveFileName(self, self._tr("dialog.save_bat"),
                                              "transcode.bat", "Batch (*.bat)")
        if not path:
            return
        content = "@echo off\n" + "\n".join(_for_batch_file(c) for c in commands) + "\npause\n"
        Path(path).write_text(content, encoding="gbk", errors="replace")
        message_box(self, "info", self._tr("dialog.save_bat"),
                                self._tr("dialog.bat_saved", path=path))

    def _run(self):
        commands = self._commands()
        if not commands:
            return
        self._log.clear()
        self._run_btn.setEnabled(False)
        self._runner = CommandRunner(commands, self)
        self._runner.line.connect(self._log.append)
        self._runner.finished.connect(self._on_run_done)
        self._runner.aborted.connect(self._on_run_aborted)
        self._runner.start()
        self._run_btn.setText("…")

    def _on_run_done(self, ok: int, failed: int):
        self._run_btn.setEnabled(True)
        self._run_btn.setText(self._tr("dialog.run"))
        self._log.append(f"[{self._tr('dialog.run_done', ok=ok, failed=failed)}]")

    def _on_run_aborted(self, ok: int, failed: int):
        self._run_btn.setEnabled(True)
        self._run_btn.setText(self._tr("dialog.run"))
        self._log.append(f"[{self._tr('dialog.run_cancelled', ok=ok, failed=failed)}]")

    def reject(self):
        if self._runner and self._runner.isRunning():
            self._runner.cancel()
            self._runner.wait(2000)
        super().reject()


def _display_format(tr, key: str) -> str:
    if key == "original":
        return tr("dialog.keep_original")
    return key.upper()


def _for_batch_file(command: str) -> str:
    """Escape a command for a double-clicked .bat file.

    Paths are already quoted; ``%`` is the one character that still expands
    inside quotes in cmd.exe. Doubling it keeps file names like ``100%.mp4``
    intact.
    """
    return command.replace("%", "%%")