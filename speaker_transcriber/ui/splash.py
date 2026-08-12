from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QLinearGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.ui.theme import Theme


class _Spinner(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._angle = 0
        self.setFixedSize(44, 44)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _tick(self) -> None:
        self._angle = (self._angle + 8) % 360
        self.update()

    def stop(self) -> None:
        self._timer.stop()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        track = QPen(QColor(255, 255, 255, 28), 3.0)
        track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track)
        painter.drawEllipse(rect)

        gradient = QConicalGradient(rect.center(), -self._angle)
        gradient.setColorAt(0.0, QColor(Theme.ACCENT))
        gradient.setColorAt(0.35, QColor(Theme.ACCENT))
        gradient.setColorAt(0.75, QColor(126, 200, 212, 0))
        gradient.setColorAt(1.0, QColor(126, 200, 212, 0))
        arc = QPen(gradient, 3.0)
        arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc)
        painter.drawArc(rect, int((-self._angle) * 16), int(270 * 16))
        painter.end()


class SplashScreen(QWidget):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setObjectName("SpeakerTranscriberSplash")
        self.setFixedSize(440, 280)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 44, 40, 36)
        root.setSpacing(0)

        brand = QLabel("Speaker Transcriber")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_font = QFont()
        brand_font.setFamilies(["Segoe UI Variable", "Segoe UI", "Inter", "Arial"])
        brand_font.setPointSize(22)
        brand_font.setWeight(QFont.Weight.DemiBold)
        brand.setFont(brand_font)
        brand.setStyleSheet(
            f"color: {Theme.TEXT}; background: transparent; letter-spacing: 0.4px;"
        )

        tagline = QLabel("Local transcription with speaker labels")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(
            f"color: {Theme.TEXT_MUTED}; background: transparent; "
            "font-size: 12px; padding-top: 8px;"
        )

        root.addWidget(brand)
        root.addWidget(tagline)
        root.addStretch(1)

        self._spinner = _Spinner(self)
        spinner_row = QVBoxLayout()
        spinner_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spinner_row.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignCenter)
        root.addLayout(spinner_row)

        self._status = QLabel("Starting…")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet(
            f"color: {Theme.TEXT_DIM}; background: transparent; "
            "font-size: 12px; padding-top: 18px;"
        )
        root.addWidget(self._status)

        self._center_on_screen()

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        self.move(
            geometry.center().x() - self.width() // 2,
            geometry.center().y() - self.height() // 2,
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 18, 18)

        fill = QLinearGradient(QPointF(0, 0), QPointF(0, self.height()))
        fill.setColorAt(0.0, QColor(Theme.SURFACE))
        fill.setColorAt(1.0, QColor(Theme.WINDOW))
        painter.fillPath(path, fill)

        border = QPen(QColor(255, 255, 255, 24), 1.0)
        painter.setPen(border)
        painter.drawPath(path)

        accent = QLinearGradient(QPointF(48, 0), QPointF(self.width() - 48, 0))
        accent.setColorAt(0.0, QColor(126, 200, 212, 0))
        accent.setColorAt(0.5, QColor(126, 200, 212, 90))
        accent.setColorAt(1.0, QColor(126, 200, 212, 0))
        painter.setPen(QPen(accent, 1.5))
        painter.drawLine(QPointF(56, 34), QPointF(self.width() - 56, 34))
        painter.end()
        super().paintEvent(event)

    def set_status(self, message: str) -> None:
        self._status.setText(message)

    def finish(self, window: QWidget) -> None:
        self._spinner.stop()
        window.show()
        window.raise_()
        window.activateWindow()
        self.close()
