from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QWidget

from speaker_transcriber.ui.theme import Theme


APP_NAME = "Summit"
APP_USER_MODEL_ID = "SpeakerTranscriber.Summit"
_ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
_DISPLAY_FONT_FILE = "SpaceGrotesk-Bold.ttf"

_font_family: str | None = None
_font_loaded = False
_icon: QIcon | None = None


def assets_dir() -> Path:
    package_dir = Path(__file__).resolve().parents[1] / "assets"
    if package_dir.is_dir():
        return package_dir

    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    if getattr(sys, "frozen", False):
        install_dir = Path(sys.executable).resolve().parent
        roots.extend((install_dir / "_internal", install_dir))

    for root in roots:
        candidate = root / "speaker_transcriber" / "assets"
        if candidate.is_dir():
            return candidate
    return package_dir


def configure_process_identity() -> None:
    """Set the Windows AppUserModelID so the taskbar uses this app's icon."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except Exception:
        return


def apply_application_identity(application: QApplication) -> None:
    application.setApplicationName(APP_NAME)
    application.setApplicationDisplayName(APP_NAME)
    application.setWindowIcon(summit_icon())


def display_font(
    point_size: int = 24,
    weight: QFont.Weight = QFont.Weight.Bold,
) -> QFont:
    family = _ensure_display_font()
    font = QFont()
    families = []
    if family:
        families.append(family)
    families.extend(
        ["Bahnschrift", "Segoe UI Variable Display", "Segoe UI", "Arial"]
    )
    font.setFamilies(families)
    font.setPointSize(point_size)
    font.setWeight(weight)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.6)
    font.setStyleStrategy(
        QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality
    )
    return font


def _ensure_display_font() -> str | None:
    global _font_family, _font_loaded
    if _font_loaded:
        return _font_family
    _font_loaded = True
    path = assets_dir() / "fonts" / _DISPLAY_FONT_FILE
    if not path.is_file():
        return None
    font_id = QFontDatabase.addApplicationFont(str(path))
    if font_id == -1:
        return None
    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        return None
    _font_family = families[0]
    return _font_family


def paint_summit_mark(painter: QPainter, rect: QRectF, *, framed: bool = True) -> None:
    """Paint the Summit mark: mountain peaks with radiating voice waves."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    size = min(rect.width(), rect.height())
    if size <= 0:
        return

    if framed:
        _paint_mark_frame(painter, rect, size)

    if size <= 20:
        _paint_compact_peak(painter, rect, size)
        return

    _paint_peaks(painter, rect, size)
    if size >= 28:
        _paint_voice_waves(painter, rect, size)
    _paint_summit_beacon(painter, rect, size)


def _paint_mark_frame(painter: QPainter, rect: QRectF, size: float) -> None:
    radius = size * 0.22
    tile = QPainterPath()
    tile.addRoundedRect(rect, radius, radius)

    background = QLinearGradient(rect.topLeft(), rect.bottomRight())
    background.setColorAt(0.0, QColor("#2A3940"))
    background.setColorAt(0.55, QColor(Theme.SURFACE))
    background.setColorAt(1.0, QColor(Theme.WINDOW))
    painter.fillPath(tile, background)

    glow = QRadialGradient(rect.center().x(), rect.top() + size * 0.28, size * 0.55)
    glow.setColorAt(0.0, QColor(126, 200, 212, 70))
    glow.setColorAt(1.0, QColor(126, 200, 212, 0))
    painter.fillPath(tile, glow)

    painter.save()
    painter.setClipPath(tile)
    highlight = QLinearGradient(
        rect.topLeft(),
        QPointF(rect.center().x(), rect.top() + size * 0.45),
    )
    highlight.setColorAt(0.0, QColor(255, 255, 255, 28))
    highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillPath(tile, highlight)
    painter.restore()

    rim = QPen(QColor(126, 200, 212, 48), max(size * 0.018, 1.0))
    painter.setPen(rim)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(tile)


def _content_rect(rect: QRectF, size: float) -> QRectF:
    pad = size * 0.17
    return rect.adjusted(pad, pad * 0.92, -pad, -pad * 0.72)


def _paint_compact_peak(painter: QPainter, rect: QRectF, size: float) -> None:
    inner = rect.adjusted(size * 0.22, size * 0.2, -size * 0.22, -size * 0.18)
    peak = QPainterPath()
    peak.moveTo(QPointF(inner.center().x(), inner.top()))
    peak.lineTo(inner.bottomRight())
    peak.lineTo(inner.bottomLeft())
    peak.closeSubpath()
    painter.fillPath(peak, QColor(Theme.ACCENT))


def _paint_peaks(painter: QPainter, rect: QRectF, size: float) -> None:
    inner = _content_rect(rect, size)
    left, top, right, bottom = inner.left(), inner.top(), inner.right(), inner.bottom()
    width = inner.width()
    height = inner.height()

    mountain = QPainterPath()
    mountain.moveTo(QPointF(left, bottom))
    mountain.lineTo(QPointF(left + width * 0.16, top + height * 0.52))
    mountain.lineTo(QPointF(left + width * 0.30, top + height * 0.64))
    mountain.lineTo(QPointF(left + width * 0.50, top + height * 0.04))
    mountain.lineTo(QPointF(left + width * 0.68, top + height * 0.58))
    mountain.lineTo(QPointF(left + width * 0.80, top + height * 0.42))
    mountain.lineTo(QPointF(right, bottom))
    mountain.closeSubpath()

    fill = QLinearGradient(
        QPointF(inner.center().x(), top),
        QPointF(inner.center().x(), bottom),
    )
    fill.setColorAt(0.0, QColor("#D7F4F8"))
    fill.setColorAt(0.22, QColor(Theme.ACCENT))
    fill.setColorAt(1.0, QColor(Theme.ACCENT_PRESSED))
    painter.fillPath(mountain, fill)


def _paint_voice_waves(painter: QPainter, rect: QRectF, size: float) -> None:
    inner = _content_rect(rect, size)
    origin = QPointF(
        inner.left() + inner.width() * 0.50,
        inner.top() + inner.height() * 0.10,
    )
    pen = QPen(QColor(Theme.ACCENT_HOVER))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    radii = (0.20, 0.30, 0.40) if size >= 48 else (0.24, 0.36)
    for index, fraction in enumerate(radii):
        radius = size * fraction
        pen.setWidthF(max(size * (0.038 - index * 0.006), 1.2))
        pen.setColor(QColor(149, 213, 223, 210 - index * 40))
        painter.setPen(pen)
        arc = QRectF(origin.x() - radius, origin.y() - radius, radius * 2, radius * 2)
        painter.drawArc(arc, 18 * 16, 54 * 16)


def _paint_summit_beacon(painter: QPainter, rect: QRectF, size: float) -> None:
    inner = _content_rect(rect, size)
    center = QPointF(
        inner.left() + inner.width() * 0.50,
        inner.top() + inner.height() * 0.04,
    )
    glow_radius = max(size * 0.09, 2.4)
    glow = QRadialGradient(center, glow_radius)
    glow.setColorAt(0.0, QColor(255, 255, 255, 230))
    glow.setColorAt(0.45, QColor(Theme.ACCENT_HOVER))
    glow.setColorAt(1.0, QColor(149, 213, 223, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(center, glow_radius, glow_radius)

    core = max(size * 0.035, 1.4)
    painter.setBrush(QColor("#F4F7F8"))
    painter.drawEllipse(center, core, core)


def render_summit_image(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    inset = 0.0 if size <= 20 else 0.5
    paint_summit_mark(painter, QRectF(inset, inset, size - inset * 2, size - inset * 2))
    painter.end()
    return image


def summit_pixmap(logical_size: int) -> QPixmap:
    application = QApplication.instance()
    dpr = float(application.devicePixelRatio()) if application is not None else 1.0
    pixel = max(1, int(round(logical_size * dpr)))
    pixmap = QPixmap.fromImage(render_summit_image(pixel))
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def summit_icon() -> QIcon:
    global _icon
    if _icon is not None and not _icon.isNull():
        return _icon
    icon = QIcon()
    ico_path = assets_dir() / "summit.ico"
    if ico_path.is_file():
        icon.addFile(str(ico_path))
    for size in _ICON_SIZES:
        icon.addPixmap(QPixmap.fromImage(render_summit_image(size)))
    _icon = icon
    return icon


def write_summit_ico(path: Path, sizes: tuple[int, ...] = (16, 24, 32, 48, 64, 256)) -> None:
    pngs = [_image_png_bytes(render_summit_image(size)) for size in sizes]
    offset = 6 + 16 * len(pngs)
    entries: list[tuple[int, int, int]] = []
    for size, data in zip(sizes, pngs):
        entries.append((size, len(data), offset))
        offset += len(data)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(struct.pack("<HHH", 0, 1, len(pngs)))
        for size, length, image_offset in entries:
            edge = 0 if size >= 256 else size
            handle.write(
                struct.pack("<BBBBHHII", edge, edge, 0, 0, 1, 32, length, image_offset)
            )
        for data in pngs:
            handle.write(data)


def _image_png_bytes(image: QImage) -> bytes:
    buffer = QByteArray()
    device = QBuffer(buffer)
    device.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(device, "PNG")
    return bytes(buffer.data())


class BrandMark(QWidget):
    def __init__(self, size: int = 72, parent=None, *, framed: bool = True) -> None:
        super().__init__(parent)
        self._size = size
        self._framed = framed
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        paint_summit_mark(
            painter,
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
            framed=self._framed,
        )
        painter.end()
