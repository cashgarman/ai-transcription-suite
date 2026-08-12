from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QLinearGradient,
    QBrush,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from speaker_transcriber.ui.branding import BrandMark, display_font, summit_icon
from speaker_transcriber.ui.theme import Theme


class _HazardProgressBar(QWidget):
    """Determinate bar with an animated diagonal hazard-tape fill."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._minimum = 0
        self._maximum = 1000
        self._value = 0
        self._offset = 0.0
        self._stripe_period = 14.0
        self.setFixedHeight(10)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def setRange(self, minimum: int, maximum: int) -> None:
        self._minimum = int(minimum)
        self._maximum = max(int(maximum), self._minimum + 1)
        self.update()

    def setValue(self, value: int) -> None:
        self._value = max(self._minimum, min(int(value), self._maximum))
        self.update()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._offset = (self._offset + 0.55) % self._stripe_period
        if self._value > self._minimum:
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
        track_path = QPainterPath()
        track_path.addRoundedRect(track, 4.0, 4.0)

        painter.fillPath(track_path, QColor(Theme.SURFACE_SUNKEN))
        painter.setPen(QPen(QColor(Theme.BORDER), 1.0))
        painter.drawPath(track_path)

        fraction = self._fraction()
        if fraction <= 0.0:
            painter.end()
            return

        fill_width = max(track.width() * fraction, 4.0)
        fill_rect = QRectF(track.left(), track.top(), fill_width, track.height())
        fill_path = QPainterPath()
        fill_path.addRoundedRect(fill_rect, 3.0, 3.0)

        painter.save()
        painter.setClipPath(fill_path)

        stripe_a = QColor(Theme.ACCENT)
        stripe_b = QColor(Theme.ACCENT_PRESSED)
        stripe_b.setAlpha(210)

        period = self._stripe_period
        stripe_width = period * 0.5
        # Extra coverage so diagonal stripes fill the clip cleanly while scrolling.
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


class SplashScreen(QWidget):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setObjectName("SummitSplash")
        self.setWindowIcon(summit_icon())
        self.setFixedSize(460, 236)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 36, 36, 20)
        root.setSpacing(0)

        mark = BrandMark(72, framed=False)

        brand = QLabel("Summit")
        brand.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        brand_font = display_font(28, QFont.Weight.Bold)
        brand_font.setCapitalization(QFont.Capitalization.SmallCaps)
        brand.setFont(brand_font)
        brand.setStyleSheet(
            f"color: {Theme.TEXT}; background: transparent;"
        )

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(10)
        brand_row.addStretch(1)
        brand_row.addWidget(mark, 0, Qt.AlignmentFlag.AlignVCenter)
        brand_row.addWidget(brand, 0, Qt.AlignmentFlag.AlignVCenter)
        brand_row.addStretch(1)
        root.addLayout(brand_row)

        tagline = QLabel(
            "Locally generated, completely private, transcription and "
            "summarization of multi-speaker meetings"
        )
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setWordWrap(True)
        tagline.setStyleSheet(
            f"color: {Theme.TEXT_MUTED}; background: transparent; "
            "font-size: 12px; padding-top: 8px; line-height: 1.3;"
        )

        root.addWidget(tagline)
        root.addSpacing(16)

        self._progress = _HazardProgressBar()
        self._progress.setRange(0, 1000)
        self._progress.setValue(0)
        root.addWidget(self._progress)

        self._status = QLabel("Starting…")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet(
            f"color: {Theme.TEXT_DIM}; background: transparent; "
            "font-size: 12px; padding-top: 10px;"
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

        # Fully clear the rectangular window so rounded corners stay transparent.
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)

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
        painter.drawLine(QPointF(48, 22), QPointF(self.width() - 48, 22))
        painter.end()

    def set_status(self, message: str, progress: float | None = None) -> None:
        self._status.setText(message)
        if progress is not None:
            value = max(0.0, min(float(progress), 1.0))
            self._progress.setValue(round(value * 1000))

    def finish(self, window: QWidget) -> None:
        self._progress.setValue(1000)
        self._progress.stop()
        window.show()
        window.raise_()
        window.activateWindow()
        self.close()
