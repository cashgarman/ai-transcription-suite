from PySide6.QtWidgets import QApplication

from speaker_transcriber.ui.branding import (
    assets_dir,
    display_font,
    summit_icon,
    summit_pixmap,
)


def _application() -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def test_assets_dir_contains_font_and_icon() -> None:
    directory = assets_dir()
    assert (directory / "fonts" / "SpaceGrotesk-Bold.ttf").is_file()
    assert (directory / "fonts" / "OFL.txt").is_file()
    assert (directory / "summit.ico").is_file()


def test_summit_icon_and_font_load() -> None:
    _application()
    pixmap = summit_pixmap(64)
    assert not pixmap.isNull()
    assert pixmap.width() >= 64
    assert pixmap.height() >= 64
    icon = summit_icon()
    assert not icon.isNull()
    font = display_font(24)
    assert font.pointSize() == 24
    assert font.family()
