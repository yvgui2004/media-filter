"""Small motion primitives shared by the window, popovers and dialogs.

Everything here is short (120–180 ms), interrupted cleanly when a second
action overtakes the first, and silently becomes a plain jump when Windows
is configured with "Show animations in Windows" turned off or when the
process sets ``MEDIAFILTER_MOTION=off``.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from functools import lru_cache

from PySide6.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, QVariantAnimation, QAbstractAnimation,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

FAST = 120          # hover-level feedback, popover open, dialog fade
REVEAL = 160        # guide bar / progress strip reveal
BASE = 180          # empty-state fades, toast out
SLOW = 240

_OUT = QEasingCurve.Type.OutCubic
_IN_OUT = QEasingCurve.Type.InOutSine

_SPI_GETCLIENTAREAANIMATION = 0x1042


@lru_cache(maxsize=1)
def animations_enabled() -> bool:
    """Follow the Windows accessibility preference; default to on."""
    if os.environ.get("MEDIAFILTER_MOTION", "").lower() in ("0", "off", "false"):
        return False
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        enabled = ctypes.c_int(1)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            _SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0
        )
        return bool(ok) and bool(enabled.value)
    except Exception:
        return True


def _stop(widget: QWidget, attr: str) -> None:
    anim = getattr(widget, attr, None)
    if isinstance(anim, QAbstractAnimation):
        try:
            anim.stop()
        except RuntimeError:
            pass
    setattr(widget, attr, None)


def _effect(widget: QWidget) -> QGraphicsOpacityEffect:
    effect = getattr(widget, "_mf_opacity_effect", None)
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(1.0)
        widget.setGraphicsEffect(effect)
        widget._mf_opacity_effect = effect
    return effect


def opacity(widget: QWidget) -> float:
    effect = getattr(widget, "_mf_opacity_effect", None)
    if isinstance(effect, QGraphicsOpacityEffect):
        return float(effect.opacity())
    return 1.0 if widget.isVisible() else 0.0


def fade_widget(
    widget: QWidget,
    start: float,
    end: float,
    duration: int = FAST,
    on_done: Callable[[], None] | None = None,
) -> None:
    """Animate a widget's opacity; a new call cancels the previous one."""
    _stop(widget, "_mf_fade_anim")
    effect = _effect(widget)
    if not animations_enabled() or duration <= 0:
        effect.setOpacity(end)
        if on_done is not None:
            on_done()
        return
    effect.setOpacity(start)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(_OUT)
    if on_done is not None:
        anim.finished.connect(on_done)
    widget._mf_fade_anim = anim
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def set_faded_visible(widget: QWidget, visible: bool, duration: int = FAST) -> None:
    """Show/hide with a short fade instead of a hard pop."""
    if not animations_enabled():
        widget.setVisible(visible)
        return
    if visible:
        if not widget.isVisible():
            _effect(widget).setOpacity(0.0)
            widget.setVisible(True)
            fade_widget(widget, 0.0, 1.0, duration)
        else:
            fade_widget(widget, opacity(widget), 1.0, duration)
        return
    if not widget.isVisible():
        return
    fade_widget(widget, opacity(widget), 0.0, duration,
                on_done=lambda: widget.setVisible(False))


def fade_in_window(widget: QWidget, duration: int = FAST) -> None:
    """Fade a top-level window (dialog/popup) in from transparent."""
    if not animations_enabled():
        try:
            widget.setWindowOpacity(1.0)
        except RuntimeError:
            pass
        return
    try:
        widget.setWindowOpacity(0.0)
        anim = QPropertyAnimation(widget, b"windowOpacity", widget)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(_OUT)
        anim.finished.connect(lambda: widget.setWindowOpacity(1.0))
        widget._mf_window_fade = anim
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    except RuntimeError:
        pass


def rise_popup(popup: QWidget, final_pos: QPoint, rise: int = 6,
               duration: int = FAST) -> None:
    """Fade a popup in while it lifts the last few pixels into place."""
    if not animations_enabled():
        popup.move(final_pos)
        fade_in_window(popup, duration=0)
        return
    popup.move(final_pos + QPoint(0, rise))
    fade_in_window(popup, duration)
    anim = QPropertyAnimation(popup, b"pos", popup)
    anim.setDuration(duration)
    anim.setStartValue(popup.pos())
    anim.setEndValue(final_pos)
    anim.setEasingCurve(_OUT)
    popup._mf_rise_anim = anim
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def animate_height(
    widget: QWidget,
    start: int,
    end: int,
    duration: int = REVEAL,
    on_done: Callable[[], None] | None = None,
) -> None:
    """Reveal or collapse a bar by animating its fixed height."""
    _stop(widget, "_mf_height_anim")
    if not animations_enabled() or duration <= 0:
        widget.setFixedHeight(end)
        if on_done is not None:
            on_done()
        return
    anim = QVariantAnimation(widget)
    anim.setDuration(duration)
    anim.setStartValue(float(start))
    anim.setEndValue(float(end))
    anim.setEasingCurve(_IN_OUT)

    def step(value) -> None:
        try:
            widget.setFixedHeight(int(round(float(value))))
        except RuntimeError:
            anim.stop()

    anim.valueChanged.connect(step)
    if on_done is not None:
        anim.finished.connect(on_done)
    widget._mf_height_anim = anim
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)