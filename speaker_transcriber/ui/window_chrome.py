from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

from speaker_transcriber.ui.theme import Theme

# Windows 10 1809+ / Windows 11 DWM attributes
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def _colorref(color: QColor) -> int:
    """Pack a Qt color into a Win32 COLORREF (0x00BBGGRR)."""
    return int(color.red()) | (int(color.green()) << 8) | (int(color.blue()) << 16)


def apply_dark_window_chrome(widget: QWidget) -> None:
    """Match the native titlebar and border to the app's dark theme on Windows."""
    if sys.platform != "win32" or not widget.isWindow():
        return

    try:
        import ctypes
    except ImportError:
        return

    hwnd = int(widget.winId())
    if hwnd == 0:
        return

    dwmapi = ctypes.windll.dwmapi
    value = ctypes.c_int(1)
    dwmapi.DwmSetWindowAttribute(
        hwnd,
        _DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(value),
        ctypes.sizeof(value),
    )

    caption = ctypes.c_int(_colorref(QColor(Theme.WINDOW)))
    border = ctypes.c_int(_colorref(QColor(Theme.BORDER)))
    text = ctypes.c_int(_colorref(QColor(Theme.TEXT)))
    for attribute, color_value in (
        (_DWMWA_CAPTION_COLOR, caption),
        (_DWMWA_BORDER_COLOR, border),
        (_DWMWA_TEXT_COLOR, text),
    ):
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            attribute,
            ctypes.byref(color_value),
            ctypes.sizeof(color_value),
        )


class _DarkChromeFilter(QObject):
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.Show
            and isinstance(obj, QWidget)
            and obj.isWindow()
            and not (obj.windowFlags() & Qt.WindowType.FramelessWindowHint)
        ):
            apply_dark_window_chrome(obj)
        return False


def install_dark_window_chrome(application: QApplication) -> None:
    """Prefer dark native chrome app-wide, and restyle top-level windows on show."""
    hints = QGuiApplication.styleHints()
    if hints is not None:
        hints.setColorScheme(Qt.ColorScheme.Dark)

    existing = application.property("_summit_dark_chrome_filter")
    if existing is not None:
        return

    event_filter = _DarkChromeFilter(application)
    application.installEventFilter(event_filter)
    application.setProperty("_summit_dark_chrome_filter", event_filter)
