"""Recognition settings and the first-run welcome flow.

Sections mirror ``.interface-design/settings.md`` and
``recognition-mode-prototype.html``: default mode, API connection, built-in
tags, advanced options. Everything is a draft until Save; Cancel discards it
all. The welcome variant additionally shows the three mode cards and a
custom-tags entry.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from PySide6.QtCore import QRectF, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QFrame, QGraphicsOpacityEffect,
    QHBoxLayout, QLabel, QLayout, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from ...config import Config
from ...core import secret_store
from ...core.cloud_models import (
    IMAGE, TEXT, UNKNOWN, VERIFIED_IMAGE, CloudModelError, ModelInfo,
    list_models, normalize_base_url, probe_vision,
)
from ...core.vocabulary import (
    ALL_TAG_IDS, DEFAULT_ENABLED, TAG_GROUPS, group_label, tag_label,
)
from ..dialog_base import (
    AppDialog, count_label, dialog_button, hint_label,
    lede_label, message_box, note_label, section_label,
)
from ..icons import line_icon
from ..tokens import LIGHT, parse_color
from .flow_layout import FlowLayout
from .mode_widgets import MODES, DefaultModeList, ModeCardRow, mode_text
from .model_picker import ModelPicker
from .my_tags_dialog import MyTagsDialog

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# Workers are not parented to the dialog: closing the dialog while a request
# is in flight must not destroy a running QThread.  The module keeps them alive
# until their ``finished`` signal arrives; late signals are disconnected by Qt
# when the dialog is gone.
_ACTIVE_WORKERS: set[QThread] = set()

_FRAME_POLICIES = ("auto", "fast", "fine")
_ADVANCED_OPEN = False

# Width assumed for the wrapping tag grid when Qt asks for a height without
# knowing the final width. Wide enough for the largest built-in group to stay
# on one line, so minimum heights stay close to the real rendering.
_TAGS_WIDTH = 560


def _track_worker(worker: QThread) -> None:
    _ACTIVE_WORKERS.add(worker)
    worker.finished.connect(lambda: _release_worker(worker))


def _release_worker(worker: QThread) -> None:
    _ACTIVE_WORKERS.discard(worker)
    worker.deleteLater()


def wait_for_active_workers(timeout_ms: int = 5000) -> None:
    """Give in-flight model calls a chance to finish before app shutdown."""
    deadline = time.monotonic() + timeout_ms / 1000
    for worker in list(_ACTIVE_WORKERS):
        remaining = int(max(0.0, deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            break
        try:
            worker.wait(remaining)
        except RuntimeError:
            continue


def _t(tr, key: str, fallback: str) -> str:
    text = tr(key)
    return fallback if text == key else text


def _link_button(text: str, tokens: dict[str, str]) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("InlineLink")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFixedHeight(20)
    button.setMinimumWidth(0)
    button.setStyleSheet(
        "QPushButton#InlineLink { background: transparent; border: none; "
        f"color: {tokens['ink_3']}; font-size: 11px; padding: 0; "
        "min-width: 0; min-height: 0; }"
        f"QPushButton#InlineLink:hover {{ color: {tokens['accent']}; }}"
    )
    return button


class _StatusRow(QWidget):
    """6px status dot + 11px text + optional detail/action."""

    def __init__(self, tokens: dict[str, str], with_action: bool = False) -> None:
        super().__init__()
        self._tokens = tokens
        self._with_action = with_action
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.dot = QLabel()
        self.dot.setFixedSize(6, 6)
        row.addWidget(self.dot)
        self.text = QLabel()
        row.addWidget(self.text)
        self.detail: QLabel | None = None
        self.action: QPushButton | None = None
        if with_action:
            self.detail = QLabel()
            row.addWidget(self.detail)
            self.action = QPushButton()
            self.action.setObjectName("InlineLink")
            self.action.setCursor(Qt.CursorShape.PointingHandCursor)
            self.action.setFixedHeight(18)
            self.action.setMinimumWidth(0)
            row.addWidget(self.action)
        row.addStretch(1)
        self.set_status("idle", "")

    def _style_link(self) -> None:
        if self.action is None:
            return
        self.action.setStyleSheet(
            "QPushButton#InlineLink { background: transparent; border: none; "
            f"color: {self._tokens['accent']}; font-size: 11px; padding: 0; "
            "min-width: 0; min-height: 0; }"
            f"QPushButton#InlineLink:hover {{ color: {self._tokens['accent_strong']}; }}"
        )

    def set_status(
        self,
        tone: str,
        text: str,
        detail: str = "",
        action: str = "",
    ) -> None:
        self._style_link()
        colors = {
            "idle": self._tokens["ink_3"],
            "ok": self._tokens["green"],
            "bad": self._tokens["red"],
            "busy": self._tokens["accent"],
        }
        color = colors.get(tone, self._tokens["ink_3"])
        self.dot.setStyleSheet(f"background: {color}; border-radius: 3px;")
        self.text.setText(text)
        self.text.setStyleSheet(f"color: {color}; font-size: 11px;")
        if self.detail is not None:
            self.detail.setText(detail)
            self.detail.setStyleSheet(
                f"color: {self._tokens['ink_3']}; font-size: 10px;"
            )
            if self.action is not None:
                self.action.setText(action)
                self.action.setVisible(bool(action))


class _ModelListWorker(QThread):
    ok = Signal(list)
    failed = Signal(str)

    def __init__(self, base_url: str, api_key: str, parent=None) -> None:
        super().__init__(parent)
        self._base = base_url
        self._key = api_key

    def run(self) -> None:
        try:
            self.ok.emit(list_models(self._base, self._key))
        except CloudModelError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # network stack variations
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _ProbeWorker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, base_url: str, api_key: str, model_id: str,
                 parent=None) -> None:
        super().__init__(parent)
        self._base = base_url
        self._key = api_key
        self._model = model_id

    def run(self) -> None:
        try:
            self.done.emit(probe_vision(self._base, self._key, self._model))
        except CloudModelError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Small custom controls
# ---------------------------------------------------------------------------


class CheckRow(QAbstractButton):
    """16px rounded checkbox + 11px label, painted to match the prototype."""

    def __init__(self, text: str, tokens: dict[str, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._text = text
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(20)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        font = QFont(self.font())
        font.setPixelSize(11)
        self.setFont(font)
        self.toggled.connect(lambda _checked: self.update())

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        return QSize(24 + metrics.horizontalAdvance(self._text) + 4, 20)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tokens = self._tokens
        box = 16
        top = (self.height() - box) / 2
        rect = (0.75, top + 0.75, box - 1.5, box - 1.5)
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(parse_color(tokens["accent"]))
        else:
            painter.setPen(QPen(parse_color(tokens["line_strong"]), 1.5))
            painter.setBrush(parse_color(tokens["surface"]))
        painter.drawRoundedRect(QRectF(*rect), 4, 4)
        if self.isChecked():
            path = QPainterPath()
            path.moveTo(4.2, top + 8.4)
            path.lineTo(6.8, top + 11.0)
            path.lineTo(11.9, top + 4.6)
            painter.setPen(QPen(parse_color(tokens["on_accent"]), 1.7,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)
        painter.setPen(parse_color(tokens["ink_2"]))
        painter.setFont(self.font())
        painter.drawText(
            QRectF(24, 0, self.width() - 24, self.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            self._text,
        )
        painter.end()


class Segment(QFrame):
    """Three-button segmented control (抽帧强度)."""

    changed = Signal(str)

    def __init__(self, tr, tokens: dict[str, str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SegmentBox")
        self._tokens = tokens
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for policy in _FRAME_POLICIES:
            button = QPushButton(tr(f"settings.frame_{policy}"))
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedHeight(26)
            button.setMinimumWidth(56)
            self._group.addButton(button)
            layout.addWidget(button)
            self.buttons[policy] = button
            button.clicked.connect(lambda _checked=False, p=policy: self.changed.emit(p))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_policy(self, policy: str) -> None:
        button = self.buttons.get(policy)
        if button is not None:
            button.setChecked(True)

    def policy(self) -> str:
        for key, button in self.buttons.items():
            if button.isChecked():
                return key
        return "auto"


class BuiltinTagsPanel(QWidget):
    """The 26 built-in tags, grouped, with 全选 / 清空."""

    changed = Signal(int)

    def __init__(self, tr, tokens: dict[str, str], enabled: list[str],
                 show_header: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tr = tr
        self._tokens = tokens
        self._buttons: dict[str, QPushButton] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        self.header = QWidget(self)
        head = QHBoxLayout(self.header)
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        head.addWidget(section_label(tr("settings.tags_title")))
        self.count = QLabel()
        self.count.setObjectName("TagCount")
        head.addWidget(self.count)
        head.addStretch(1)
        self._all_btn = _link_button(tr("settings.tags_all"), tokens)
        self._none_btn = _link_button(tr("settings.tags_none"), tokens)
        head.addWidget(self._all_btn)
        head.addWidget(self._none_btn)
        self.header.setVisible(show_header)
        layout.addWidget(self.header)

        enabled_set = set(enabled)
        for group_key, tag_ids in TAG_GROUPS:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(12)
            group = QLabel(group_label(tr, group_key))
            group.setObjectName("TagGroupLabel")
            group.setFixedWidth(44)
            group.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            row.addWidget(group)
            chip_holder = QWidget()
            chip_holder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            flow = FlowLayout(chip_holder, h_spacing=5, v_spacing=5)
            for tag_id in tag_ids:
                button = QPushButton()
                button.setObjectName("TagChip")
                button.setCheckable(True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setFixedHeight(26)
                button.setChecked(tag_id in enabled_set)
                button.setProperty("tagId", tag_id)
                self._paint_text(button, tag_id)
                button.toggled.connect(
                    lambda checked, b=button, t=tag_id: self._on_toggled(b, t, checked)
                )
                self._buttons[tag_id] = button
                flow.addWidget(button)
            row.addWidget(chip_holder, 1)
            layout.addLayout(row)

        self.note = note_label(tr("settings.tags_note"))
        layout.addWidget(self.note)

        self._all_btn.clicked.connect(lambda: self.set_all(True))
        self._none_btn.clicked.connect(lambda: self.set_all(False))
        self._refresh_count()

    def _paint_text(self, button: QPushButton, tag_id: str) -> None:
        label = tag_label(self._tr, tag_id)
        button.setText(("✓ " if button.isChecked() else "") + label)

    def _on_toggled(self, button: QPushButton, tag_id: str, checked: bool) -> None:
        self._paint_text(button, tag_id)
        self._refresh_count()
        self.changed.emit(self.count_enabled())

    def set_all(self, enabled: bool) -> None:
        for button in self._buttons.values():
            button.blockSignals(True)
            button.setChecked(enabled)
            button.blockSignals(False)
        for tag_id, button in self._buttons.items():
            self._paint_text(button, tag_id)
        self._refresh_count()
        self.changed.emit(self.count_enabled())

    def set_enabled_ids(self, ids: list[str]) -> None:
        enabled = set(ids)
        for tag_id, button in self._buttons.items():
            button.blockSignals(True)
            button.setChecked(tag_id in enabled)
            button.blockSignals(False)
            self._paint_text(button, tag_id)
        self._refresh_count()
        self.changed.emit(self.count_enabled())

    def count_enabled(self) -> int:
        return sum(1 for button in self._buttons.values() if button.isChecked())

    def enabled_ids(self) -> list[str]:
        return [tag for tag in ALL_TAG_IDS if self._buttons[tag].isChecked()]

    # Qt asks a height-for-width widget for its height at its *minimum* width
    # when sizing a parent. With FlowLayout that means every chip on its own
    # line and a minimum height several times too tall, which the scroll area
    # then honours — leaving a large blank gap under the content. Report the
    # height for the width we are actually given instead.
    def hasHeightForWidth(self) -> bool:  # noqa: N802 (Qt name)
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        layout = self.layout()
        if layout is None:
            return super().heightForWidth(width)
        return layout.totalHeightForWidth(max(width, _TAGS_WIDTH))

    def sizeHint(self) -> QSize:  # noqa: N802
        hint = super().sizeHint()
        width = self.width() if self.width() > 0 else _TAGS_WIDTH
        return QSize(hint.width(), self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        hint = super().minimumSizeHint()
        width = max(self.width(), _TAGS_WIDTH)
        return QSize(hint.width(), self.heightForWidth(width))

    def _refresh_count(self) -> None:
        self.count.setText(self._tr("settings.tags_count", n=self.count_enabled()))


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------


class SettingsDialog(AppDialog):
    def __init__(
        self,
        config: Config,
        tr,
        parent=None,
        tokens: dict[str, str] | None = None,
        variant: str = "settings",
    ) -> None:
        super().__init__(tokens, parent)
        self._config = config
        self._tr = tr
        self._tokens = tokens or LIGHT
        self._variant = variant if variant in ("settings", "first_run") else "settings"
        self._first_run = self._variant == "first_run"

        self._models: list[ModelInfo] = []
        self._model_state = "none"
        self._list_worker: _ModelListWorker | None = None
        self._probe_worker: _ProbeWorker | None = None
        self._saved_key = ""
        self._key_error = ""
        self._key_unreadable = False
        self._request_base = ""
        self._probe_base = ""
        self._probe_key = ""
        self._loaded_base = ""
        self._pending_cache: dict[str, str] = {}
        self._probe_at = ""
        self._auto_started = False

        tags = [tag for tag in config.tag_palette if tag in ALL_TAG_IDS]
        self._enabled_tags = tags or list(DEFAULT_ENABLED)
        self._custom_labels = list(config.custom_labels)
        mode = config.recognition_mode if config.recognition_mode in MODES else "local"
        if (
            self._first_run
            and not config.first_run_done
            and config.cloud_api_key_dpapi
            and config.recognition_mode == "local"
        ):
            mode = "hybrid"
        self._mode = mode
        self._frame_policy = (
            config.frame_policy if config.frame_policy in _FRAME_POLICIES else "auto"
        )

        self.setWindowTitle(
            tr("first_run.window_title") if self._first_run else tr("settings.title")
        )
        self.setMinimumSize(680, 620)
        if not self._first_run:
            self.setMinimumSize(700, 520)
        self._size_dialog()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("SettingsScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body = QWidget()
        self._body.setObjectName("SettingsBody")
        body = QVBoxLayout(self._body)
        body.setContentsMargins(24, 22, 24, 18)
        body.setSpacing(12)
        self._scroll.setWidget(self._body)
        outer.addWidget(self._scroll, 1)

        self._build_intro(body)
        self._build_mode_section(body)
        body.addWidget(self._rule())
        self._build_api_section(body)
        self._api_effect: QGraphicsOpacityEffect | None = None
        body.addWidget(self._rule())
        if self._first_run:
            self._build_custom_section(body)
        self._build_tags_section(body)
        body.addWidget(self._rule())
        self._build_advanced_section(body)
        body.addStretch(1)

        self._build_footer(outer)
        self._load_saved_state()
        self._wire()

    # -- construction helpers --------------------------------------------

    def _size_dialog(self) -> None:
        screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry().height() if screen else 900
        if self._first_run:
            width = 760
            height = int(round(width * 815 / 760))
            ceiling = int(available * 0.9)
            floor = 620
        else:
            # Same 1200:760 proportion as the main window, at 75% scale:
            # 900×570 reads as the workspace shrunk into a dialog.
            width = 900
            height = int(round(width * 760 / 1200))
            ceiling = int(available * 0.88)
            floor = 520
        self.resize(width, max(floor, min(height, ceiling)))

    def _rule(self) -> QFrame:
        rule = QFrame()
        rule.setObjectName("DialogRule")
        rule.setFixedHeight(1)
        return rule

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    def _build_intro(self, body: QVBoxLayout) -> None:
        tr = self._tr
        if self._first_run:
            eyebrow = QLabel(tr("first_run.eyebrow"))
            eyebrow.setObjectName("FieldLabel")
            body.addWidget(eyebrow)
            title = QLabel(tr("first_run.title"))
            title.setStyleSheet(
                f"font-size: 19px; font-weight: 600; color: {self._tokens['ink']};"
            )
            body.addWidget(title)
            body.addWidget(lede_label(tr("first_run.lede")))
        else:
            body.addWidget(lede_label(tr("settings.lede")))

    def _build_mode_section(self, body: QVBoxLayout) -> None:
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(section_label(self._tr("settings.mode_title")))
        head.addStretch(1)
        if not self._first_run:
            head.addWidget(hint_label(self._tr("settings.mode_default_note")))
        body.addLayout(head)

        if self._first_run:
            self._mode_cards = ModeCardRow(self._tr, self._tokens, self)
            self._mode_cards.set_mode(self._mode)
            body.addWidget(self._mode_cards)
            self._mode_list = None
        else:
            self._mode_cards = None
            self._mode_list = DefaultModeList(self._tr, self._tokens, self)
            self._mode_list.set_mode(self._mode)
            self._mode_list.set_current(self._config.recognition_mode)
            body.addWidget(self._mode_list)
            self._current_note = QLabel(
                self._tr(
                    "settings.current_mode_note",
                    mode=mode_text(self._tr, self._config.recognition_mode),
                )
            )
            self._current_note.setObjectName("Hint")
            self._current_note.setWordWrap(True)
            body.addWidget(self._current_note)

    def _build_api_section(self, body: QVBoxLayout) -> None:
        tr = self._tr
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(section_label(tr("settings.api_title")))
        head.addStretch(1)
        head.addWidget(hint_label(tr("settings.api_compatible")))
        body.addLayout(head)

        self._api_body = QWidget()
        api = QVBoxLayout(self._api_body)
        api.setContentsMargins(0, 0, 0, 0)
        api.setSpacing(8)

        api.addWidget(self._field_label(tr("settings.api_key")))
        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        self._key = QLineEdit()
        self._key.setObjectName("FieldInput")
        self._key.setFixedHeight(34)
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setPlaceholderText(tr("settings.api_key_placeholder"))
        self._key.setAccessibleName(tr("settings.api_key"))
        self._eye_action = self._key.addAction(
            line_icon("eye", self._tokens["ink_3"], 15),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        self._eye_action.setToolTip(tr("settings.show_key"))
        self._eye_action.triggered.connect(self._toggle_key_visibility)
        key_row.addWidget(self._key, 1)
        self._test_btn = dialog_button(tr("settings.test"), "ghost")
        self._test_btn.setFixedWidth(96)
        key_row.addWidget(self._test_btn)
        api.addLayout(key_row)

        self._key_required = QLabel(tr("settings.key_required"))
        self._key_required.setStyleSheet(
            f"color: {self._tokens['red']}; font-size: 11px;"
        )
        self._key_required.setVisible(False)
        api.addWidget(self._key_required)

        self._api_status = _StatusRow(self._tokens)
        api.addWidget(self._api_status)

        api.addWidget(self._field_label("BASE URL"))
        self._base = QLineEdit()
        self._base.setObjectName("FieldInput")
        self._base.setFixedHeight(34)
        self._base.setPlaceholderText(DEFAULT_BASE_URL)
        self._base.setText(self._config.cloud_base_url or DEFAULT_BASE_URL)
        self._base.setAccessibleName("BASE URL")
        api.addWidget(self._base)

        model_head = QHBoxLayout()
        model_head.setSpacing(8)
        model_head.addWidget(self._field_label(tr("settings.model")))
        model_head.addStretch(1)
        self._model_count = count_label()
        model_head.addWidget(self._model_count)
        api.addLayout(model_head)

        self._picker = ModelPicker(tr, self._tokens, self)
        self._picker.setAccessibleName(tr("settings.model_title"))
        self._picker.selected.connect(self._on_model_selected)
        self._picker.refreshRequested.connect(self._load_models)
        api.addWidget(self._picker)

        self._model_status = _StatusRow(self._tokens, with_action=True)
        api.addWidget(self._model_status)

        api.addWidget(note_label(tr("settings.key_note")))
        body.addWidget(self._api_body)

        self._local_api_note = note_label(tr("settings.local_api_note"))
        self._local_api_note.setVisible(False)
        body.addWidget(self._local_api_note)

    def _build_custom_section(self, body: QVBoxLayout) -> None:
        tr = self._tr
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(section_label(tr("settings.custom_title")))
        head.addStretch(1)
        self._custom_count = QLabel(
            tr("settings.custom_count", n=len(self._custom_labels))
        )
        self._custom_count.setObjectName("Hint")
        head.addWidget(self._custom_count)
        self._custom_edit = dialog_button(tr("settings.custom_edit"), "ghost")
        self._custom_edit.setFixedWidth(76)
        head.addWidget(self._custom_edit)
        body.addLayout(head)
        self._custom_note = note_label(tr("settings.custom_note"))
        body.addWidget(self._custom_note)

    def _build_tags_section(self, body: QVBoxLayout) -> None:
        tr = self._tr
        self._tags_panel = BuiltinTagsPanel(
            tr, self._tokens, self._enabled_tags,
            show_header=not self._first_run, parent=self,
        )
        if self._first_run:
            self._tags_toggle = QToolButton()
            self._tags_toggle.setObjectName("AdvHead")
            self._tags_toggle.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            self._tags_toggle.setIcon(line_icon("chevron-right", self._tokens["ink_3"], 14))
            self._tags_toggle.setIconSize(QSize(14, 14))
            self._tags_toggle.setFixedHeight(34)
            self._tags_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
            self._tags_toggle.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self._update_tags_toggle_text(False)
            self._tags_toggle.clicked.connect(self._toggle_tags)
            body.addWidget(self._tags_toggle)
            self._tags_panel.setVisible(False)
            body.addWidget(self._tags_panel)
        else:
            body.addWidget(self._tags_panel)

    def _build_advanced_section(self, body: QVBoxLayout) -> None:
        tr = self._tr
        self._adv_toggle = QToolButton()
        self._adv_toggle.setObjectName("AdvHead")
        self._adv_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._adv_toggle.setIconSize(QSize(14, 14))
        self._adv_toggle.setFixedHeight(34)
        self._adv_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._adv_toggle.setText(tr("settings.advanced_title"))
        body.addWidget(self._adv_toggle)

        self._adv_panel = QWidget()
        panel = QVBoxLayout(self._adv_panel)
        panel.setContentsMargins(0, 2, 0, 0)
        panel.setSpacing(9)

        panel.addWidget(self._field_label(tr("settings.frame_title")))
        self._segment = Segment(tr, self._tokens, self)
        self._segment.set_policy(self._frame_policy)
        panel.addWidget(self._segment)
        self._frame_note = note_label(tr("settings.frame_note"))
        panel.addWidget(self._frame_note)

        self._upload_only = CheckRow(tr("settings.upload_only"), self._tokens)
        self._upload_only.setChecked(self._config.upload_target_only)
        panel.addWidget(self._upload_only)
        panel.addWidget(self._hint(tr("settings.upload_only_hint")))

        self._color_local = CheckRow(tr("settings.color_local"), self._tokens)
        self._color_local.setChecked(self._config.local_color_tags)
        panel.addWidget(self._color_local)
        panel.addWidget(self._hint(tr("settings.color_local_hint")))

        self._adv_panel.setVisible(_ADVANCED_OPEN)
        body.addWidget(self._adv_panel)
        self._sync_adv_head()
        self._adv_toggle.clicked.connect(self._toggle_advanced)

    def _hint(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("CheckHint")
        label.setWordWrap(True)
        label.setContentsMargins(24, 0, 0, 0)
        return label

    def _build_footer(self, outer: QVBoxLayout) -> None:
        tr = self._tr
        self._footer_rule = self._rule()
        outer.addWidget(self._footer_rule)
        footer_widget = QWidget()
        footer = QHBoxLayout(footer_widget)
        footer.setContentsMargins(24, 10, 24, 20)
        footer.setSpacing(10)

        if self._first_run:
            footer.addStretch(1)
            self._skip_btn = dialog_button(tr("first_run.skip"))
            self._save_btn = dialog_button(tr("first_run.start"), "primary")
            footer.addWidget(self._skip_btn)
            footer.addWidget(self._save_btn)
        else:
            self._reset_btn = _link_button(tr("settings.reset"), self._tokens)
            footer.addWidget(self._reset_btn)
            footer.addStretch(1)
            self._cancel_btn = dialog_button(tr("settings.cancel"))
            self._save_btn = dialog_button(tr("settings.save"), "primary")
            footer.addWidget(self._cancel_btn)
            footer.addWidget(self._save_btn)
        outer.addWidget(footer_widget)

    def _wire(self) -> None:
        if self._first_run and self._mode_cards is not None:
            self._mode_cards.modeChanged.connect(self._on_mode_changed)
        if not self._first_run and self._mode_list is not None:
            self._mode_list.modeChanged.connect(self._on_mode_changed)
        self._tags_panel.changed.connect(self._on_tags_changed)
        self._test_btn.clicked.connect(self._load_models)
        self._key.textChanged.connect(self._on_key_changed)
        self._base.textChanged.connect(self._on_base_changed)
        self._save_btn.clicked.connect(self._save)
        if self._first_run:
            self._skip_btn.clicked.connect(self._skip)
            self._custom_edit.clicked.connect(self._edit_custom_tags)
        else:
            self._reset_btn.clicked.connect(self._reset_page)
            self._cancel_btn.clicked.connect(self.reject)
        if self._model_status.action is not None:
            self._model_status.action.clicked.connect(self._model_action)
        self._update_save()
        self._refresh_mode_state()

    # -- initial state ----------------------------------------------------

    def _load_saved_state(self) -> None:
        tr = self._tr
        try:
            self._saved_key = secret_store.unprotect(self._config.cloud_api_key_dpapi)
            self._key.setText(self._saved_key)
        except secret_store.SecretStoreError as exc:
            self._key_error = str(exc)
            self._key_unreadable = True
            self._set_api_status("bad", tr("settings.key_unreadable"))

        if self._config.cloud_model:
            model = ModelInfo(
                id=self._config.cloud_model,
                name=self._config.cloud_model_name or self._config.cloud_model,
                context=self._config.cloud_model_context,
                capability=_config_capability(self._config.cloud_model_capability),
            )
            self._picker.set_model(model)
            self._apply_model_state(self._state_for_model(model), model=model)
        else:
            self._apply_model_state("none")

        if not self._key_error:
            self._set_api_status("idle", tr("settings.api_untested"))
        self._set_model_count(len(self._models))
        self._update_save()

    # -- mode / tags ------------------------------------------------------

    def _on_mode_changed(self, _mode: str) -> None:
        self._refresh_mode_state()

    def selected_mode(self) -> str:
        """The default mode currently drafted in the page."""
        if self._mode_cards is not None:
            return self._mode_cards.mode()
        if self._mode_list is not None:
            return self._mode_list.mode()
        return "local"

    def _selected_mode(self) -> str:
        return self.selected_mode()

    def _refresh_mode_state(self) -> None:
        mode = self._selected_mode()
        local = mode == "local"
        self._api_body.setEnabled(not local)
        # The prototype fades the whole API block in local mode; without this
        # the fields look editable even though clicks do nothing. The effect
        # stays detached (disabled) when the section is live so text rendering
        # is untouched.
        if self._api_effect is None:
            self._api_effect = QGraphicsOpacityEffect(self._api_body)
            self._api_effect.setOpacity(0.55)
            self._api_body.setGraphicsEffect(self._api_effect)
        self._api_effect.setEnabled(local)
        self._local_api_note.setVisible(local)
        if self._first_run:
            self._custom_edit.setEnabled(not local)
            self._custom_note.setText(
                self._tr("settings.local_custom_note") if local
                else self._tr("settings.custom_note")
            )
        if local:
            self._key_required.setVisible(False)
        else:
            self._update_save()

    def _on_tags_changed(self, count: int) -> None:
        if self._first_run:
            self._update_tags_toggle_text(self._tags_panel.isVisible())

    def _update_tags_toggle_text(self, expanded: bool) -> None:
        count = self._tags_panel.count_enabled()
        text = self._tr("settings.tags_collapsed", n=count)
        if expanded:
            text = self._tr("settings.tags_expanded", n=count)
        self._tags_toggle.setText("  " + text)
        self._tags_toggle.setIcon(
            line_icon(
                "chevron-down" if expanded else "chevron-right",
                self._tokens["ink_3"], 14,
            )
        )

    def _toggle_tags(self) -> None:
        visible = self._tags_panel.isHidden()
        self._tags_panel.setVisible(visible)
        self._update_tags_toggle_text(visible)

    def _toggle_advanced(self) -> None:
        global _ADVANCED_OPEN
        _ADVANCED_OPEN = not _ADVANCED_OPEN
        self._adv_panel.setVisible(_ADVANCED_OPEN)
        self._sync_adv_head()

    def _sync_adv_head(self) -> None:
        # isVisible() is False until the dialog is shown, which used to leave
        # the chevron pointing right on a panel that was already open.
        expanded = not self._adv_panel.isHidden()
        self._adv_toggle.setIcon(
            line_icon(
                "chevron-down" if expanded else "chevron-right",
                self._tokens["ink_3"], 14,
            )
        )

    def _edit_custom_tags(self) -> None:
        dialog = MyTagsDialog(self._custom_labels, self._tr, self, tokens=self._tokens)
        if dialog.exec() == int(MyTagsDialog.DialogCode.Accepted):
            self._custom_labels = dialog.labels()
            self._custom_count.setText(
                self._tr("settings.custom_count", n=len(self._custom_labels))
            )

    # -- API / model state (worker plumbing kept from the original page) ---

    def _set_api_status(self, tone: str, text: str) -> None:
        self._api_status.set_status(tone, text)

    def _set_model_status(
        self, tone: str, text: str, detail: str = "", action: str = ""
    ) -> None:
        self._model_status.set_status(tone, text, detail, action)

    def _set_model_count(self, count: int) -> None:
        if count:
            self._model_count.setText(
                _t(self._tr, "settings.model_count", "{n} 个模型").format(n=count)
            )
        else:
            self._model_count.setText("")

    def _update_save(self) -> None:
        self._save_btn.setEnabled(self._model_state not in ("text", "checking"))

    def _toggle_key_visibility(self) -> None:
        if self._key.echoMode() == QLineEdit.EchoMode.Password:
            self._key.setEchoMode(QLineEdit.EchoMode.Normal)
            self._eye_action.setIcon(line_icon("eye-off", self._tokens["ink_3"], 15))
            self._eye_action.setToolTip(self._tr("settings.hide_key"))
        else:
            self._key.setEchoMode(QLineEdit.EchoMode.Password)
            self._eye_action.setIcon(line_icon("eye", self._tokens["ink_3"], 15))
            self._eye_action.setToolTip(self._tr("settings.show_key"))

    def _on_key_changed(self) -> None:
        self._key_error = ""
        self._key_unreadable = False
        self._key_required.setVisible(False)
        if self._key.text().strip() != self._saved_key:
            self._set_api_status("idle", self._tr("settings.api_untested"))

    def _on_base_changed(self) -> None:
        if normalize_base_url(self._base.text()) != self._loaded_base:
            self._set_api_status("idle", self._tr("settings.api_untested"))
            current = self._picker.model()
            if current is not None:
                self._apply_model_state(
                    self._state_for_model(current, trust_saved=False), model=current
                )

    # -- model loading ----------------------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._auto_started:
            return
        self._auto_started = True
        if self._selected_mode() != "local":
            QTimer.singleShot(0, self._auto_load)

    def _auto_load(self) -> None:
        try:
            if not self.isVisible():
                return
        except RuntimeError:
            return
        base = self._base.text().strip()
        key = self._key.text().strip()
        if not base:
            return
        if key or "127.0.0.1" in base or "localhost" in base:
            self._load_models()

    def _load_models(self) -> None:
        if self._list_worker is not None and self._list_worker.isRunning():
            return
        base = normalize_base_url(self._base.text())
        if not base:
            self._set_api_status("bad", self._tr("settings.base_required"))
            self._base.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        key = self._key.text().strip()
        self._request_base = base
        self._test_btn.setEnabled(False)
        self._test_btn.setText(self._tr("settings.testing"))
        self._set_api_status("busy", self._tr("settings.api_testing"))
        self._picker.set_loading(True)

        worker = _ModelListWorker(base, key)
        _track_worker(worker)
        worker.ok.connect(self._on_models_loaded)
        worker.failed.connect(self._on_models_failed)
        worker.finished.connect(self._list_finished)
        self._list_worker = worker
        worker.start()

    def _list_finished(self) -> None:
        if self.sender() is not self._list_worker:
            return
        self._list_worker = None
        self._test_btn.setEnabled(True)
        self._test_btn.setText(self._tr("settings.test"))
        self._picker.set_loading(False)

    def _on_models_loaded(self, models: list[ModelInfo]) -> None:
        current_base = normalize_base_url(self._base.text())
        if self._request_base and current_base != self._request_base:
            return
        self._models = models
        self._loaded_base = self._request_base or current_base
        self._picker.set_models(models)
        self._set_model_count(len(models))
        self._set_api_status("ok", self._tr("settings.api_ok", n=len(models)))
        current = self._picker.model()
        if current is None:
            saved_id = self._config.cloud_model
            chosen = next((m for m in models if m.id == saved_id), None)
            if chosen is None:
                chosen = next((m for m in models if m.recommended), None)
            if chosen is None:
                chosen = next((m for m in models if m.capability == IMAGE), None)
            if chosen is None and models:
                chosen = models[0]
            if chosen is not None:
                self._picker.set_model(chosen)
                self._apply_model_state(self._state_for_model(chosen), model=chosen)
        elif self._model_state != "checking":
            self._apply_model_state(self._state_for_model(current), model=current)

    def _on_models_failed(self, message: str) -> None:
        if (
            self._request_base
            and normalize_base_url(self._base.text()) != self._request_base
        ):
            return
        self._set_api_status("bad", self._tr("settings.api_bad", msg=_short(message)))
        self._picker.set_error(message)
        if self._picker.model() is None:
            self._apply_model_state("none")

    # -- model state ------------------------------------------------------

    def _cache_key(self, model: ModelInfo) -> str:
        base = normalize_base_url(self._base.text())
        return f"{base}|{model.id}|png"

    def _state_for_model(self, model: ModelInfo, trust_saved: bool = True) -> str:
        cached = self._pending_cache.get(
            self._cache_key(model),
            self._config.cloud_model_cache.get(self._cache_key(model), ""),
        )
        if cached == VERIFIED_IMAGE:
            return "verified"
        if cached == TEXT:
            return "text"
        if trust_saved and model.capability == VERIFIED_IMAGE:
            return "verified"
        if model.capability == IMAGE:
            return "meta"
        if model.capability == TEXT:
            return "text"
        return "unknown"

    def _on_model_selected(self, model: ModelInfo) -> None:
        self._apply_model_state(self._state_for_model(model), model=model)

    def _apply_model_state(self, state: str, model: ModelInfo | None = None) -> None:
        self._model_state = state
        if model is not None:
            if state == "verified":
                self._picker.set_selected_capability(VERIFIED_IMAGE)
            elif state == "text":
                self._picker.set_selected_capability(TEXT)
            elif state == "meta":
                self._picker.set_selected_capability(model.capability)
            elif state == "checking":
                pass
            else:
                self._picker.set_selected_capability(UNKNOWN)

        tr = self._tr
        if state == "none":
            self._set_model_status("idle", tr("settings.model_none_status"), "")
        elif state == "meta":
            self._set_model_status(
                "ok", tr("settings.model_status_image"),
                tr("settings.model_detail_meta"), tr("settings.model_verify"),
            )
        elif state == "verified":
            self._set_model_status(
                "ok", tr("settings.model_status_image"),
                tr("settings.model_detail_verified"), tr("settings.model_reverify"),
            )
        elif state == "text":
            self._set_model_status(
                "bad", tr("settings.model_status_text"),
                tr("settings.model_detail_text"), tr("settings.model_change"),
            )
        elif state == "checking":
            self._set_model_status(
                "busy", tr("settings.model_status_checking"),
                tr("settings.model_detail_checking"), "",
            )
        elif state == "error":
            self._set_model_status(
                "bad", tr("settings.model_status_error"),
                tr("settings.model_detail_error"), tr("settings.model_retry"),
            )
        else:
            self._set_model_status(
                "busy", tr("settings.model_status_unknown"),
                tr("settings.model_detail_unknown"), tr("settings.model_verify"),
            )
        self._update_save()

    def _model_action(self) -> None:
        model = self._picker.model()
        if model is None or self._model_state == "text":
            self._picker.open_popup()
            return
        if self._model_state in ("meta", "verified", "unknown", "error"):
            self._probe_model(model)

    def _probe_model(self, model: ModelInfo) -> None:
        if self._probe_worker is not None and self._probe_worker.isRunning():
            return
        base = normalize_base_url(self._base.text())
        if not base:
            self._set_api_status("bad", self._tr("settings.base_required"))
            self._base.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        key = self._key.text().strip()
        self._probe_base = base
        self._probe_key = self._cache_key(model)
        self._apply_model_state("checking", model=model)
        worker = _ProbeWorker(base, key, model.id)
        _track_worker(worker)
        worker.done.connect(lambda result: self._on_probe_done(model, result))
        worker.failed.connect(lambda message: self._on_probe_failed(model, message))
        worker.finished.connect(self._probe_finished)
        self._probe_worker = worker
        worker.start()

    def _probe_finished(self) -> None:
        if self.sender() is not self._probe_worker:
            return
        self._probe_worker = None

    def _on_probe_done(self, model: ModelInfo, result) -> None:
        capability = getattr(result, "capability", UNKNOWN)
        detail = getattr(result, "detail", "")
        key = self._probe_key or self._cache_key(model)
        current = self._picker.model()
        same_model = current is not None and current.id == model.id
        same_context = (
            same_model
            and normalize_base_url(self._base.text()) == self._probe_base
        )
        if capability == VERIFIED_IMAGE:
            self._pending_cache[key] = VERIFIED_IMAGE
            if same_context:
                self._probe_at = _now_iso()
                self._apply_model_state("verified", model=model)
        elif capability == TEXT:
            self._pending_cache[key] = TEXT
            if same_context:
                self._probe_at = _now_iso()
                self._apply_model_state("text", model=model)
        else:
            self._pending_cache.pop(key, None)
            if not same_context:
                return
            self._picker.set_selected_capability(UNKNOWN)
            self._set_model_status(
                "busy", self._tr("settings.model_status_unknown"),
                _short(detail) if detail else self._tr("settings.model_detail_unknown"),
                self._tr("settings.model_retry"),
            )
            self._model_state = "unknown"
            self._update_save()

    def _on_probe_failed(self, model: ModelInfo, message: str) -> None:
        current = self._picker.model()
        if current is None or current.id != model.id:
            return
        if normalize_base_url(self._base.text()) != self._probe_base:
            return
        self._model_state = "error"
        self._set_model_status(
            "bad", self._tr("settings.model_status_error"),
            _short(message), self._tr("settings.model_retry"),
        )
        self._update_save()

    # -- reset / save -----------------------------------------------------

    def _reset_page(self) -> None:
        answer = message_box(
            self, "question", self._tr("settings.title"),
            self._tr("settings.reset_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != int(QMessageBox.StandardButton.Yes):
            return
        self._key.clear()
        self._base.setText(DEFAULT_BASE_URL)
        self._models = []
        self._pending_cache = {}
        self._probe_at = ""
        self._picker.set_model(None)
        self._picker.set_models([])
        self._set_model_count(0)
        self._set_api_status("idle", self._tr("settings.api_untested"))
        self._apply_model_state("none")
        if self._mode_list is not None:
            self._mode_list.set_mode("local")
        if self._mode_cards is not None:
            self._mode_cards.set_mode("local")
        self._tags_panel.set_enabled_ids(list(DEFAULT_ENABLED))
        self._frame_policy = "auto"
        self._segment.set_policy("auto")
        self._upload_only.setChecked(True)
        self._color_local.setChecked(True)
        self._refresh_mode_state()
        self._update_save()

    def _skip(self) -> None:
        self._config.recognition_mode = self._selected_mode()
        self._config.first_run_prompted = True
        self._config.save()
        self.reject()

    def _save(self) -> None:
        tr = self._tr
        mode = self._selected_mode()
        key = self._key.text().strip()
        base = normalize_base_url(self._base.text())
        model = self._picker.model()
        previous_model = self._config.cloud_model

        if mode in ("hybrid", "cloud") and not key:
            self._key_required.setVisible(True)
            self._key.setFocus(Qt.FocusReason.OtherFocusReason)
            return
        if self._model_state == "text":
            self._apply_model_state("text", model=model)
            return
        if (model is not None or key) and not base:
            self._set_api_status("bad", tr("settings.base_required"))
            self._base.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        if key != self._saved_key:
            if key:
                try:
                    self._config.cloud_api_key_dpapi = secret_store.protect(key)
                except secret_store.SecretStoreError as exc:
                    message_box(self, "critical", tr("settings.title"), str(exc))
                    return
                self._config.cloud_api_key_hint = secret_store.key_hint(key)
            else:
                self._config.cloud_api_key_dpapi = ""
                self._config.cloud_api_key_hint = ""
        elif self._key_unreadable and not key:
            self._config.cloud_api_key_dpapi = ""
            self._config.cloud_api_key_hint = ""

        self._config.cloud_base_url = base or DEFAULT_BASE_URL
        if model is None:
            self._config.cloud_model = ""
            self._config.cloud_model_name = ""
            self._config.cloud_model_context = ""
            self._config.cloud_model_capability = UNKNOWN
            self._config.cloud_model_probe_at = ""
        else:
            self._config.cloud_model = model.id
            self._config.cloud_model_name = model.name
            self._config.cloud_model_context = model.context
            if self._model_state == "verified":
                capability = VERIFIED_IMAGE
            elif self._model_state == "text":
                capability = TEXT
            elif self._model_state == "meta":
                capability = model.capability
            else:
                capability = UNKNOWN
            self._config.cloud_model_capability = capability
            if self._model_state in ("verified", "text"):
                self._config.cloud_model_probe_at = self._probe_at or _now_iso()
            elif model.id != previous_model:
                self._config.cloud_model_probe_at = self._probe_at
        for cache_key, value in self._pending_cache.items():
            self._config.cloud_model_cache[cache_key] = value

        self._config.recognition_mode = mode
        enabled = self._tags_panel.enabled_ids()
        self._config.tag_palette = [tag for tag in ALL_TAG_IDS if tag in enabled]
        self._config.custom_labels = list(self._custom_labels)
        self._config.frame_policy = self._segment.policy()
        self._config.upload_target_only = self._upload_only.isChecked()
        self._config.local_color_tags = self._color_local.isChecked()
        self._config.first_run_done = True
        self._config.first_run_prompted = True
        self._config.guide_dismissed = True
        self.accept()


def _config_capability(value: str) -> str:
    return value if value in (IMAGE, VERIFIED_IMAGE, TEXT, UNKNOWN) else UNKNOWN


def _short(text: str, limit: int = 110) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")