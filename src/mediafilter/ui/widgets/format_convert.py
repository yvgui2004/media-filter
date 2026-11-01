"""Format convert dialog: remux (stream copy) or re-encode to another container."""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ...core.ffmpeg import build_command, build_output_path
from ...core.models import FileRecord

_TARGETS = ("mp4", "mkv", "mov", "webm", "avi", "flv", "ts", "m4v")

_COPY = 'ffmpeg -i "{input}" -map 0 -c copy "{output}"'
_X265_CRF23 = ('ffmpeg -hwaccel auto -i "{input}" -c:v libx265 -crf 23 -preset medium '
               '-c:a aac -b:a 96k -movflags +faststart "{output}"')
_X265_CRF26 = ('ffmpeg -hwaccel auto -i "{input}" -c:v libx265 -crf 26 -preset medium '
               '-c:a aac -b:a 96k -movflags +faststart "{output}"')
_NVENC_HEVC = ('ffmpeg -hwaccel cuda -i "{input}" -c:v hevc_nvenc -cq 23 -rc vbr '
               '-c:a aac -b:a 96k -movflags +faststart "{output}"')
_NVENC_H264 = ('ffmpeg -hwaccel cuda -i "{input}" -c:v h264_nvenc -preset p7 -tune hq '
               '-rc vbr -cq 23 -c:a aac -b:a 96k -movflags +faststart "{output}"')
_NVENC_AV1 = ('ffmpeg -hwaccel cuda -i "{input}" -c:v av1_nvenc -preset p7 -rc constqp '
              '-qp 30 -c:a aac -b:a 96k -movflags +faststart "{output}"')

# (template, name i18n key, desc i18n key)
_MODES = (
    (_COPY,       "convert.mode.copy",       "convert.mode.copy.desc"),
    (_X265_CRF23, "convert.mode.x265_crf23", "convert.mode.x265_crf23.desc"),
    (_X265_CRF26, "convert.mode.x265_crf26", "convert.mode.x265_crf26.desc"),
    (_NVENC_HEVC, "convert.mode.nvenc_hevc", "convert.mode.nvenc_hevc.desc"),
    (_NVENC_H264, "convert.mode.nvenc_h264", "convert.mode.nvenc_h264.desc"),
    (_NVENC_AV1,  "convert.mode.nvenc_av1",  "convert.mode.nvenc_av1.desc"),
)


class FormatConvertDialog(QDialog):
    def __init__(self, records: list[FileRecord], tr, parent=None):
        super().__init__(parent)
        self._records = records
        self._tr = tr

        self.setWindowTitle(tr("dialog.convert_title"))
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # target + mode
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("dialog.convert_to")))
        self._target = QComboBox()
        self._target.addItems(_TARGETS)
        row.addWidget(self._target, 1)
        self._mode = QComboBox()
        for mode in _MODES:
            self._mode.addItem(self._mode_label(mode))
        row.addWidget(self._mode, 1)
        layout.addLayout(row)

        # functional annotation for the selected mode
        self._mode_note = QLabel()
        self._mode_note.setObjectName("presetNote")
        self._mode_note.setWordWrap(True)
        layout.addWidget(self._mode_note)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        layout.addWidget(self._preview, 1)

        btn_row = QHBoxLayout()
        self._copy_btn = QPushButton(tr("dialog.copy"))
        self._close_btn = QPushButton(tr("dialog.close"))
        btn_row.addWidget(self._copy_btn)
        btn_row.addWidget(self._close_btn)
        layout.addLayout(btn_row)

        self._target.currentIndexChanged.connect(self._refresh)
        self._mode.currentIndexChanged.connect(self._refresh)
        self._copy_btn.clicked.connect(self._copy)
        self._close_btn.clicked.connect(self.reject)

        self._refresh()

    def _current_mode(self):
        return _MODES[self._mode.currentIndex()]

    def _template(self) -> str:
        return self._current_mode()[0]

    def _mode_label(self, mode) -> str:
        return f"{self._tr(mode[1])} — {self._tr(mode[2])}"

    def _mode_description(self) -> str:
        return self._tr(self._current_mode()[2])

    def _commands(self) -> list[str]:
        target = _TARGETS[self._target.currentIndex()]
        return [
            build_command(self._template(), rec.path,
                          build_output_path(rec.path, "_converted", target))
            for rec in self._records
        ]

    def _refresh(self):
        self._preview.setPlainText("\n\n".join(self._commands()))
        self._mode_note.setText(self._mode_description())

    def _copy(self):
        commands = self._commands()
        if not commands:
            QMessageBox.information(self, self._tr("app.title"),
                                    self._tr("msg.nothing_selected"))
            return
        QGuiApplication.clipboard().setText("\n\n".join(commands))
        self._preview.append(self._tr("msg.copied", n=len(commands)))