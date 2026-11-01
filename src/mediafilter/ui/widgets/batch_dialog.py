"""Batch command dialog: pick a preset, generate per-file ffmpeg commands,
copy to clipboard, save as .bat, or run them in the background."""

from __future__ import annotations

import shlex
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ...core.ffmpeg import Preset, build_command, build_output_path
from ...core.models import FileRecord

_OUTPUT_FORMATS = (("original", None), ("mp4", "mp4"), ("mkv", "mkv"),
                   ("mov", "mov"), ("webm", "webm"), ("flv", "flv"))


class CommandRunner(QThread):
    """Runs the generated commands sequentially; cancel terminates the current
    process and stops before the next starts."""

    line = Signal(str)
    finished = Signal(int)   # success count
    aborted = Signal(int)    # count completed before cancel

    def __init__(self, commands: list[str], parent=None):
        super().__init__(parent)
        self._commands = commands
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        completed = 0
        for cmd in self._commands:
            if self._cancel:
                break
            self.line.emit(f"> {cmd}")
            try:
                argv = shlex.split(cmd, posix=(sys.platform != "win32"))
            except ValueError as exc:
                self.line.emit(f"  [bad command: {exc}]")
                continue
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0  # type: ignore[attr-defined]
            try:
                proc = subprocess.Popen(
                    argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=flags,
                )
            except OSError as exc:
                self.line.emit(f"  [launch failed: {exc}]")
                continue
            while proc.poll() is None:
                if self._cancel:
                    proc.terminate()
                time.sleep(0.1)
            completed += 1
            self.line.emit(f"  [exit {proc.returncode}]")
        if self._cancel:
            self.aborted.emit(completed)
        else:
            self.finished.emit(completed)


class BatchCommandDialog(QDialog):
    def __init__(self, records: list[FileRecord], tr, presets: list[Preset], parent=None):
        super().__init__(parent)
        self._records = records
        self._tr = tr
        self._presets = presets
        self._runner: CommandRunner | None = None

        self.setWindowTitle(tr("dialog.batch_title"))
        self.setMinimumSize(640, 480)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # preset selector
        preset_row = QHBoxLayout()
        preset_row.addWidget(self._label(tr("dialog.preset")))
        self._preset_combo = QComboBox()
        preset_row.addWidget(self._preset_combo, 1)
        layout.addLayout(preset_row)

        # functional annotation for the selected preset
        self._preset_note = QLabel()
        self._preset_note.setObjectName("presetNote")
        self._preset_note.setWordWrap(True)
        layout.addWidget(self._preset_note)

        # command template
        layout.addWidget(self._label(tr("dialog.command")))
        self._template = QTextEdit()
        self._template.setFixedHeight(80)
        self._template.setAcceptRichText(False)
        layout.addWidget(self._template)

        # output options
        opts_row = QHBoxLayout()
        opts_row.addWidget(self._label(tr("dialog.output_suffix")))
        self._suffix = QLineEdit("_out")
        opts_row.addWidget(self._suffix, 1)
        opts_row.addWidget(self._label(tr("dialog.output_ext")))
        self._ext_combo = QComboBox()
        for key, _ext in _OUTPUT_FORMATS:
            self._ext_combo.addItem(_display_format(tr, key))
        opts_row.addWidget(self._ext_combo, 1)
        layout.addLayout(opts_row)

        # preview / progress log
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        layout.addWidget(self._log, 1)

        # buttons
        btn_row = QHBoxLayout()
        self._copy_btn = QPushButton(tr("dialog.copy"))
        self._bat_btn = QPushButton(tr("dialog.save_bat"))
        self._run_btn = QPushButton(tr("dialog.run"))
        self._close_btn = QPushButton(tr("dialog.close"))
        for b in (self._copy_btn, self._bat_btn, self._run_btn, self._close_btn):
            btn_row.addWidget(b)
        layout.addLayout(btn_row)

        # Wire signals BEFORE populating the combo: the first addItem() selects
        # index 0, which emits currentIndexChanged and fills the template box.
        self._preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        self._suffix.textChanged.connect(self._update_preview)
        self._ext_combo.currentIndexChanged.connect(self._update_preview)
        self._copy_btn.clicked.connect(self._copy)
        self._bat_btn.clicked.connect(self._save_bat)
        self._run_btn.clicked.connect(self._run)
        self._close_btn.clicked.connect(self.reject)

        for p in presets:
            self._preset_combo.addItem(self._preset_label(p))

    # -- helpers ---------------------------------------------------------

    def _label(self, text: str) -> QLabel:
        return QLabel(text)

    @property
    def _current_preset(self) -> Preset | None:
        i = self._preset_combo.currentIndex()
        return self._presets[i] if 0 <= i < len(self._presets) else None

    def _preset_description(self, preset: Preset) -> str:
        key = f"preset.{preset.key}.desc"
        text = self._tr(key)
        return preset.description if text == key else text

    def _preset_label(self, preset: Preset) -> str:
        return f"{preset.name} — {self._preset_description(preset)}"

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

    def _on_preset_changed(self):
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
            QMessageBox.information(self, self._tr("app.title"),
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
        content = "@echo off\n" + "\n".join(commands) + "\npause\n"
        Path(path).write_text(content, encoding="gbk", errors="replace")
        QMessageBox.information(self, self._tr("dialog.save_bat"),
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

    def _on_run_done(self, count):
        self._run_btn.setEnabled(True)
        self._run_btn.setText(self._tr("dialog.run"))
        self._log.append(f"[{self._tr('status.done', files=count, errors=0)}]")

    def _on_run_aborted(self, count):
        self._run_btn.setEnabled(True)
        self._run_btn.setText(self._tr("dialog.run"))
        self._log.append(f"[{self._tr('status.cancelled')} ({count})]")

    def reject(self):
        if self._runner and self._runner.isRunning():
            self._runner.cancel()
            self._runner.wait(2000)
        super().reject()


def _display_format(tr, key: str) -> str:
    if key == "original":
        return tr("dialog.keep_original")
    return key