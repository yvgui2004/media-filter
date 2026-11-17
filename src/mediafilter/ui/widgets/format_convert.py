"""Format convert dialog: remux (stream copy) or re-encode to another container."""

from __future__ import annotations

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QTextEdit,
    QVBoxLayout,
)

from ..dialog_base import (
    AppDialog,
    add_footer,
    count_label,
    dialog_button,
    lede_label,
    message_box,
    mono_font,
    note_label,
    section_label,
)
from ..select_field import SelectField
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


class FormatConvertDialog(AppDialog):
    def __init__(
        self,
        records: list[FileRecord],
        tr,
        parent=None,
        tokens: dict[str, str] | None = None,
    ):
        super().__init__(tokens, parent)
        self._records = records
        self._tr = tr

        self.setWindowTitle(tr("dialog.convert_title"))
        self.resize(720, 560)
        self.setMinimumSize(620, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        layout.addWidget(lede_label(tr("dialog.convert_lede", n=len(records))))

        # target + mode
        option_row = QHBoxLayout()
        option_row.setSpacing(16)
        target_box = QVBoxLayout()
        target_box.setSpacing(8)
        target_box.addWidget(section_label(tr("dialog.convert_to")))
        self._target = SelectField()
        self._target.set_tokens(self._tokens)
        self._target.set_accessible_label(tr("dialog.convert_to"))
        self._target.set_popup_width(160)
        target_box.addWidget(self._target)
        option_row.addLayout(target_box, 2)

        mode_box = QVBoxLayout()
        mode_box.setSpacing(8)
        mode_box.addWidget(section_label(tr("dialog.mode")))
        self._mode = SelectField()
        self._mode.set_tokens(self._tokens)
        self._mode.set_accessible_label(tr("dialog.mode"))
        self._mode.set_popup_width(380)
        mode_box.addWidget(self._mode)
        option_row.addLayout(mode_box, 5)
        layout.addLayout(option_row)

        # functional annotation for the selected mode
        self._mode_note = note_label()
        layout.addWidget(self._mode_note)

        preview_head = QHBoxLayout()
        preview_head.setSpacing(8)
        preview_head.addWidget(section_label(tr("dialog.section_preview")))
        preview_head.addStretch(1)
        self._count = count_label()
        preview_head.addWidget(self._count)
        layout.addLayout(preview_head)

        self._preview = QTextEdit()
        self._preview.setObjectName("PreviewBox")
        self._preview.setReadOnly(True)
        self._preview.setFont(mono_font(12))
        self._preview.setAccessibleName(tr("dialog.section_preview"))
        layout.addWidget(self._preview, 1)

        self._copy_btn = dialog_button(tr("dialog.copy"), "primary")
        self._close_btn = dialog_button(tr("dialog.close"))
        add_footer(layout, [self._close_btn, self._copy_btn])

        self._target.currentIndexChanged.connect(self._refresh)
        self._mode.currentIndexChanged.connect(self._refresh)
        self._copy_btn.clicked.connect(self._copy)
        self._close_btn.clicked.connect(self.reject)

        self._target.addItems([target.upper() for target in _TARGETS])
        for mode in _MODES:
            self._mode.addItem(self._tr(mode[1]))
        self._refresh()

    def _current_mode(self):
        return _MODES[self._mode.currentIndex()]

    def _template(self) -> str:
        return self._current_mode()[0]

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
        commands = self._commands()
        self._preview.setPlainText("\n\n".join(commands))
        self._mode_note.setText(self._mode_description())
        self._count.setText(self._tr("dialog.command_count", n=len(commands)))

    def _copy(self):
        commands = self._commands()
        if not commands:
            message_box(self, "info", self._tr("app.title"),
                                    self._tr("msg.nothing_selected"))
            return
        QGuiApplication.clipboard().setText("\n\n".join(commands))
        self._preview.append(self._tr("msg.copied", n=len(commands)))