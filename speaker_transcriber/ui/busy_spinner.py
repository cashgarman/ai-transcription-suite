from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QConicalGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from speaker_transcriber.ui.theme import Theme


class BusySpinner(QWidget):
    """Small translucent animated spinner."""

    def __init__(self, parent=None, *, size: int = 40) -> None:
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start(16)
        self.show()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(3, 3, -3, -3)

        track = QPen(QColor(255, 255, 255, 36), 3.0)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track)
        painter.drawEllipse(rect)

        gradient = QConicalGradient(rect.center(), -self._angle)
        accent = QColor(Theme.ACCENT)
        accent.setAlpha(230)
        faded = QColor(Theme.ACCENT)
        faded.setAlpha(0)
        gradient.setColorAt(0.0, accent)
        gradient.setColorAt(0.35, accent)
        gradient.setColorAt(0.75, faded)
        gradient.setColorAt(1.0, faded)
        arc = QPen(gradient, 3.0)
        arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc)
        painter.drawArc(rect, int((-self._angle) * 16), int(270 * 16))
        painter.end()


class BusySpinnerOverlay(QWidget):
    """Centered translucent spinner overlay for a host panel."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self._spinner = BusySpinner(self, size=42)
        self.hide()

    def set_busy(self, busy: bool) -> None:
        if busy:
            self._reposition()
            self.show()
            self.raise_()
            self._spinner.start()
        else:
            self._spinner.stop()
            self.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposition()

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(parent.rect())
        self._spinner.move(
            (self.width() - self._spinner.width()) // 2,
            (self.height() - self._spinner.height()) // 2,
        )
