from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from speaker_transcriber.ui.theme import Theme


class HazardProgressBar(QWidget):
    """Determinate bar with an animated diagonal hazard-tape fill."""

    def __init__(
        self,
        parent=None,
        *,
        bar_height: int = 10,
        autostart: bool = True,
    ) -> None:
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 1000
        self._value = 0
        self._offset = 0.0
        self._stripe_period = 14.0
        self.setFixedHeight(int(bar_height))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        if autostart:
            self.start()

    def setRange(self, minimum: int, maximum: int) -> None:
        self._minimum = int(minimum)
        self._maximum = max(int(maximum), self._minimum + 1)
        self.update()

    def setValue(self, value: int) -> None:
        self._value = max(self._minimum, min(int(value), self._maximum))
        self.update()

    def value(self) -> int:
        return self._value

    def setTextVisible(self, _visible: bool) -> None:
        return

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start(16)

    def stop(self) -> None:
        self._timer.stop()
        self.update()

    def is_animating(self) -> bool:
        return self._timer.isActive()

    def _tick(self) -> None:
        self._offset = (self._offset + 0.55) % self._stripe_period
        if self._value > self._minimum or self._timer.isActive():
            self.update()

    def _fraction(self) -> float:
        span = self._maximum - self._minimum
        if span <= 0:
            return 0.0
        return (self._value - self._minimum) / span

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        track = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = min(8.0, max(3.0, track.height() / 2.0))
        track_path = QPainterPath()
        track_path.addRoundedRect(track, radius, radius)

        painter.fillPath(track_path, QColor(Theme.SURFACE_SUNKEN))
        painter.setPen(QPen(QColor(Theme.BORDER), 1.0))
        painter.drawPath(track_path)

        fraction = self._fraction()
        if fraction <= 0.0:
            if not self._timer.isActive():
                painter.end()
                return
            fill_width = max(24.0, track.height() * 1.6)
        else:
            fill_width = max(track.width() * fraction, 4.0)
        fill_rect = QRectF(track.left(), track.top(), fill_width, track.height())
        fill_path = QPainterPath()
        fill_path.addRoundedRect(fill_rect, max(2.0, radius - 1.0), max(2.0, radius - 1.0))

        painter.save()
        painter.setClipPath(fill_path)

        stripe_a = QColor(Theme.ACCENT)
        stripe_b = QColor(Theme.ACCENT_PRESSED)
        stripe_b.setAlpha(210)

        period = self._stripe_period
        stripe_width = period * 0.5
        start = -period * 2 - self._offset
        end = fill_width + period * 2
        height = fill_rect.height()
        skew = height

        x = start
        toggle = False
        while x < end:
            color = stripe_a if not toggle else stripe_b
            band = QPainterPath()
            band.moveTo(QPointF(fill_rect.left() + x, fill_rect.top()))
            band.lineTo(QPointF(fill_rect.left() + x + stripe_width, fill_rect.top()))
            band.lineTo(
                QPointF(fill_rect.left() + x + stripe_width - skew, fill_rect.bottom())
            )
            band.lineTo(QPointF(fill_rect.left() + x - skew, fill_rect.bottom()))
            band.closeSubpath()
            painter.fillPath(band, QBrush(color))
            x += stripe_width
            toggle = not toggle

        gloss = QLinearGradient(fill_rect.topLeft(), fill_rect.bottomLeft())
        gloss.setColorAt(0.0, QColor(255, 255, 255, 36))
        gloss.setColorAt(0.45, QColor(255, 255, 255, 0))
        gloss.setColorAt(1.0, QColor(0, 0, 0, 28))
        painter.fillPath(fill_path, gloss)
        painter.restore()

        painter.setPen(QPen(QColor(Theme.BORDER), 1.0))
        painter.drawPath(track_path)
        painter.end()
