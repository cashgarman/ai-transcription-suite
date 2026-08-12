from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QTimer,
    Qt,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QWidget,
)


@dataclass(frozen=True)
class _Notice:
    text: str
    kind: str
    duration_ms: int


class NotificationBanner(QFrame):
    """Reusable dropdown notices anchored to the top center of a host window."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self._host = host
        self._queue: deque[_Notice] = deque()
        self._active: _Notice | None = None
        self._hiding = False

        self.setObjectName("notificationBanner")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMaximumWidth(460)
        self.hide()

        self._label = QLabel()
        self._label.setObjectName("notificationBannerText")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(0)
        layout.addWidget(self._label)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._dismiss)

        self._animation = QPropertyAnimation(self, b"pos", self)
        self._animation.setDuration(280)
        self._animation.finished.connect(self._on_animation_finished)

        host.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if watched is self._host and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
        ):
            if self.isVisible() and not self._hiding:
                self.move(self._shown_pos())
        return False

    def show_message(
        self,
        text: str,
        *,
        kind: str = "info",
        duration_ms: int = 3800,
    ) -> None:
        notice = _Notice(text.strip(), kind, max(int(duration_ms), 800))
        if not notice.text:
            return
        self._queue.append(notice)
        if self._active is None:
            self._present_next()

    def _present_next(self) -> None:
        if not self._queue:
            self._active = None
            self.hide()
            return
        self._active = self._queue.popleft()
        self._hiding = False
        self._apply_notice(self._active)
        self.adjustSize()
        self.show()
        self.raise_()
        start = self._hidden_pos()
        end = self._shown_pos()
        self.move(start)
        self._animation.stop()
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        self._animation.start()
        self._hide_timer.start(self._active.duration_ms)

    def _apply_notice(self, notice: _Notice) -> None:
        self._label.setText(notice.text)
        self.setProperty("kind", notice.kind)
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

    def _top_offset(self) -> int:
        if isinstance(self._host, QMainWindow):
            menu = self._host.menuBar()
            if menu is not None and not menu.isNativeMenuBar():
                return menu.height() + 10
        return 10

    def _shown_pos(self) -> QPoint:
        x = max((self._host.width() - self.width()) // 2, 8)
        return QPoint(x, self._top_offset())

    def _hidden_pos(self) -> QPoint:
        x = max((self._host.width() - self.width()) // 2, 8)
        return QPoint(x, -self.height() - 12)

    def _dismiss(self) -> None:
        if self._active is None or self._hiding:
            return
        self._hiding = True
        self._hide_timer.stop()
        self._animation.stop()
        self._animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self._animation.setStartValue(self.pos())
        self._animation.setEndValue(self._hidden_pos())
        self._animation.start()

    def _on_animation_finished(self) -> None:
        if self._hiding:
            self._present_next()

    def mousePressEvent(self, event) -> None:
        self._dismiss()
        event.accept()
