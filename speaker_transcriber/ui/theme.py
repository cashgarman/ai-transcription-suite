from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory


class Theme:
    """Shared visual tokens matching the splash screen."""

    WINDOW = "#12181C"
    SURFACE = "#1B2429"
    SURFACE_RAISED = "#232D33"
    SURFACE_SUNKEN = "#0E1316"
    BORDER = "#2E3A41"
    BORDER_SUBTLE = "rgba(255, 255, 255, 0.09)"
    TEXT = "#F4F7F8"
    TEXT_MUTED = "#9AA7AE"
    TEXT_DIM = "#B7C2C8"
    ACCENT = "#7EC8D4"
    ACCENT_HOVER = "#95D5DF"
    ACCENT_PRESSED = "#5FA8B4"
    ACCENT_SOFT = "rgba(126, 200, 212, 0.18)"
    DANGER = "#E57373"
    SUCCESS = "#81C784"
    SCROLLBAR = "#3A474E"
    HIGHLIGHT_TEXT = "#0E1316"


def apply_application_theme(application: QApplication) -> None:
    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        application.setStyle(fusion)

    font = QFont()
    font.setFamilies(["Segoe UI Variable", "Segoe UI", "Inter", "Arial"])
    font.setPointSize(10)
    application.setFont(font)

    palette = QPalette()
    window = QColor(Theme.WINDOW)
    surface = QColor(Theme.SURFACE)
    text = QColor(Theme.TEXT)
    muted = QColor(Theme.TEXT_MUTED)
    accent = QColor(Theme.ACCENT)
    base = QColor(Theme.SURFACE_SUNKEN)
    border = QColor(Theme.BORDER)

    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, surface)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.PlaceholderText, muted)
    palette.setColor(QPalette.ColorRole.Button, surface)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, surface)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(Theme.HIGHLIGHT_TEXT))
    palette.setColor(QPalette.ColorRole.Link, accent)
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor(Theme.ACCENT_PRESSED))
    palette.setColor(QPalette.ColorRole.Light, QColor(Theme.SURFACE_RAISED))
    palette.setColor(QPalette.ColorRole.Mid, border)
    palette.setColor(QPalette.ColorRole.Dark, window)
    palette.setColor(QPalette.ColorRole.Shadow, QColor("#000000"))
    application.setPalette(palette)
    application.setStyleSheet(_stylesheet())

    from speaker_transcriber.ui.window_chrome import install_dark_window_chrome

    install_dark_window_chrome(application)


def _stylesheet() -> str:
    return f"""
    * {{
        selection-background-color: {Theme.ACCENT};
        selection-color: {Theme.HIGHLIGHT_TEXT};
    }}

    QMainWindow, QDialog, QWidget {{
        background-color: {Theme.WINDOW};
        color: {Theme.TEXT};
    }}

    QWidget#SummitSplash {{
        background: transparent;
    }}

    QToolTip {{
        background-color: {Theme.SURFACE_RAISED};
        color: {Theme.TEXT};
        border: 1px solid {Theme.BORDER};
        padding: 6px 8px;
        border-radius: 6px;
    }}

    QGroupBox {{
        background-color: {Theme.SURFACE};
        border: 1px solid {Theme.BORDER};
        border-radius: 10px;
        margin-top: 14px;
        padding: 14px 12px 12px 12px;
        font-weight: 600;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 6px;
        color: {Theme.ACCENT};
    }}

    QLabel {{
        background: transparent;
        color: {Theme.TEXT};
    }}

    QPushButton {{
        background-color: {Theme.SURFACE_RAISED};
        color: {Theme.TEXT};
        border: 1px solid {Theme.BORDER};
        border-radius: 8px;
        padding: 7px 14px;
        min-height: 18px;
    }}

    QPushButton:hover {{
        background-color: #2B373E;
        border-color: {Theme.ACCENT};
    }}

    QPushButton:pressed {{
        background-color: #1A2328;
    }}

    QPushButton:disabled {{
        color: {Theme.TEXT_MUTED};
        background-color: {Theme.SURFACE};
        border-color: {Theme.BORDER};
    }}

    QPushButton:default, QPushButton#primaryButton {{
        background-color: {Theme.ACCENT};
        color: {Theme.HIGHLIGHT_TEXT};
        border: 1px solid {Theme.ACCENT};
        font-weight: 600;
    }}

    QPushButton:default:hover, QPushButton#primaryButton:hover {{
        background-color: {Theme.ACCENT_HOVER};
        border-color: {Theme.ACCENT_HOVER};
    }}

    QPushButton:default:pressed, QPushButton#primaryButton:pressed {{
        background-color: {Theme.ACCENT_PRESSED};
        border-color: {Theme.ACCENT_PRESSED};
    }}

    QPushButton#primaryButton:disabled {{
        background-color: {Theme.SURFACE_RAISED};
        color: {Theme.TEXT_MUTED};
        border-color: {Theme.BORDER};
        font-weight: 600;
    }}

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
        background-color: {Theme.SURFACE_SUNKEN};
        color: {Theme.TEXT};
        border: 1px solid {Theme.BORDER};
        border-radius: 8px;
        padding: 6px 8px;
        selection-background-color: {Theme.ACCENT};
        selection-color: {Theme.HIGHLIGHT_TEXT};
    }}

    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
    QPlainTextEdit:focus, QTextEdit:focus {{
        border: 1px solid {Theme.ACCENT};
    }}

    QComboBox {{
        combobox-popup: 0;
    }}

    QComboBox[modelInstalled="false"] {{
        color: {Theme.TEXT_MUTED};
    }}

    QComboBox[modelInstalled="true"] {{
        color: {Theme.TEXT};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}

    QComboBox::down-arrow {{
        width: 0;
        height: 0;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid {Theme.TEXT_MUTED};
        margin-right: 8px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {Theme.SURFACE_RAISED};
        color: {Theme.TEXT};
        border: 1px solid {Theme.BORDER};
        selection-background-color: {Theme.ACCENT};
        selection-color: {Theme.HIGHLIGHT_TEXT};
        outline: 0;
    }}

    QComboBox QAbstractItemView::item {{
        min-height: 24px;
        padding: 4px 8px;
        color: {Theme.TEXT};
    }}

    QComboBox QAbstractItemView::item:selected {{
        background-color: {Theme.ACCENT};
        color: {Theme.HIGHLIGHT_TEXT};
    }}

    QComboBox QAbstractItemView::item:disabled {{
        color: {Theme.TEXT_MUTED};
    }}

    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        background-color: {Theme.SURFACE_RAISED};
        border: none;
        width: 18px;
    }}

    QCheckBox {{
        spacing: 8px;
        color: {Theme.TEXT};
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {Theme.BORDER};
        background: {Theme.SURFACE_SUNKEN};
    }}

    QCheckBox::indicator:checked {{
        background: {Theme.ACCENT};
        border-color: {Theme.ACCENT};
    }}

    QTabWidget::pane {{
        border: 1px solid {Theme.BORDER};
        border-radius: 10px;
        top: -1px;
        background: {Theme.SURFACE};
    }}

    QTabBar::tab {{
        background: {Theme.WINDOW};
        color: {Theme.TEXT_MUTED};
        border: 1px solid {Theme.BORDER};
        border-bottom: none;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        padding: 8px 16px;
        margin-right: 4px;
    }}

    QTabBar::tab:selected {{
        background: {Theme.SURFACE};
        color: {Theme.TEXT};
        border-color: {Theme.BORDER};
    }}

    QTabBar::tab:hover:!selected {{
        color: {Theme.ACCENT};
    }}

    QHeaderView::section {{
        background-color: {Theme.SURFACE_RAISED};
        color: {Theme.TEXT_DIM};
        border: none;
        border-right: 1px solid {Theme.BORDER};
        border-bottom: 1px solid {Theme.BORDER};
        padding: 8px;
        font-weight: 600;
    }}

    QHeaderView::down-arrow {{
        width: 0;
        height: 0;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {Theme.TEXT_MUTED};
        margin-right: 6px;
    }}

    QHeaderView::up-arrow {{
        width: 0;
        height: 0;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-bottom: 5px solid {Theme.TEXT_MUTED};
        margin-right: 6px;
    }}

    QTableWidget, QTableView {{
        background-color: {Theme.SURFACE_SUNKEN};
        alternate-background-color: {Theme.SURFACE};
        color: {Theme.TEXT};
        gridline-color: {Theme.BORDER};
        border: 1px solid {Theme.BORDER};
        border-radius: 8px;
        outline: 0;
    }}

    QTableWidget::item:selected, QTableView::item:selected {{
        background-color: {Theme.ACCENT};
        color: {Theme.HIGHLIGHT_TEXT};
    }}

    QProgressBar {{
        background-color: {Theme.SURFACE_SUNKEN};
        border: 1px solid {Theme.BORDER};
        border-radius: 8px;
        text-align: center;
        color: {Theme.TEXT};
        min-height: 16px;
    }}

    QProgressBar::chunk {{
        background-color: {Theme.ACCENT};
        border-radius: 7px;
    }}

    QSplitter::handle {{
        background-color: {Theme.BORDER};
        width: 2px;
        height: 2px;
        margin: 2px;
    }}

    QScrollBar:vertical {{
        background: {Theme.SURFACE};
        width: 12px;
        margin: 0;
        border: none;
    }}

    QScrollBar::handle:vertical {{
        background: {Theme.SCROLLBAR};
        border-radius: 5px;
        min-height: 28px;
        margin: 2px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {Theme.ACCENT};
    }}

    QScrollBar:horizontal {{
        background: {Theme.SURFACE};
        height: 12px;
        margin: 0;
        border: none;
    }}

    QScrollBar::handle:horizontal {{
        background: {Theme.SCROLLBAR};
        border-radius: 5px;
        min-width: 28px;
        margin: 2px;
    }}

    QScrollBar::add-line, QScrollBar::sub-line,
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: transparent;
        border: none;
        height: 0;
        width: 0;
    }}

    QMenuBar {{
        background-color: {Theme.SURFACE};
        color: {Theme.TEXT};
        border-bottom: 1px solid {Theme.BORDER};
        spacing: 2px;
        padding: 2px 4px;
    }}

    QMenuBar::item {{
        background: transparent;
        color: {Theme.TEXT};
        padding: 6px 10px;
        border-radius: 6px;
    }}

    QMenuBar::item:selected {{
        background-color: {Theme.ACCENT_SOFT};
    }}

    QMenuBar::item:pressed {{
        background-color: {Theme.ACCENT_SOFT};
    }}

    QMenu {{
        background-color: {Theme.SURFACE_RAISED};
        color: {Theme.TEXT};
        border: 1px solid {Theme.BORDER};
        border-radius: 8px;
        padding: 4px;
    }}

    QMenu::item {{
        padding: 7px 18px 7px 32px;
        border-radius: 6px;
    }}

    QMenu::item:selected {{
        background-color: {Theme.ACCENT_SOFT};
        color: {Theme.TEXT};
    }}

    QMenu::item:disabled {{
        color: {Theme.TEXT_MUTED};
    }}

    QMenu::indicator {{
        width: 16px;
        height: 16px;
        left: 8px;
    }}

    QMenu::indicator:non-exclusive:unchecked {{
        border: 1px solid {Theme.BORDER};
        border-radius: 4px;
        background: {Theme.SURFACE_SUNKEN};
    }}

    QMenu::indicator:non-exclusive:checked {{
        border: 1px solid {Theme.ACCENT};
        border-radius: 4px;
        background: {Theme.ACCENT};
    }}

    QMenu::separator {{
        height: 1px;
        background: {Theme.BORDER};
        margin: 4px 8px;
    }}

    QDialogButtonBox QPushButton {{
        min-width: 84px;
    }}

    QMessageBox {{
        background-color: {Theme.SURFACE};
    }}

    QStatusBar {{
        background: {Theme.SURFACE};
        color: {Theme.TEXT_MUTED};
    }}

    QFrame#collapsibleSection {{
        background-color: {Theme.SURFACE};
        border: 1px solid {Theme.BORDER};
        border-radius: 10px;
    }}

    QFrame#statusStrip {{
        background-color: {Theme.SURFACE};
        border: 1px solid {Theme.BORDER};
        border-radius: 8px;
    }}

    QWidget#jobProgressHost,
    QWidget#jobProgressBar,
    QWidget#jobProgressOverlay {{
        background: transparent;
        min-height: 28px;
        max-height: 28px;
    }}

    QLabel#jobStageLabel,
    QLabel#jobStagePercentLabel {{
        background: transparent;
        color: {Theme.TEXT};
        font-size: 12px;
    }}

    QLabel#jobStagePercentLabel {{
        font-weight: 600;
        min-width: 2.6em;
    }}

    QProgressBar#cpuMeter,
    QProgressBar#ramMeter,
    QProgressBar#vramMeter,
    QProgressBar#gpuMeter {{
        background-color: {Theme.SURFACE_SUNKEN};
        border: 1px solid {Theme.BORDER};
        border-radius: 4px;
        min-height: 6px;
        max-height: 6px;
        text-align: center;
    }}

    QProgressBar#cpuMeter::chunk {{
        background-color: {Theme.ACCENT_PRESSED};
        border-radius: 3px;
    }}

    QProgressBar#ramMeter::chunk {{
        background-color: {Theme.ACCENT};
        border-radius: 3px;
    }}

    QProgressBar#vramMeter::chunk {{
        background-color: {Theme.ACCENT};
        border-radius: 3px;
    }}

    QProgressBar#gpuMeter::chunk {{
        background-color: {Theme.ACCENT_HOVER};
        border-radius: 3px;
    }}

    QLabel#meterCaption {{
        color: {Theme.TEXT_MUTED};
        font-size: 10px;
        padding: 0;
        background: transparent;
    }}

    QLabel#fieldCaption {{
        color: {Theme.TEXT_MUTED};
        padding: 6px 12px;
    }}

    QLabel#modelFieldCaption {{
        color: {Theme.TEXT_MUTED};
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 11px;
        background: transparent;
    }}

    QLabel#modelFieldCaption[active="true"] {{
        background-color: {Theme.ACCENT_SOFT};
        color: {Theme.TEXT};
    }}

    QLabel#detachedPlaceholderText {{
        color: {Theme.TEXT_MUTED};
    }}

    QWidget#collapsibleHeader {{
        background: transparent;
    }}

    QWidget#collapsibleContent {{
        background: transparent;
    }}

    QWidget#textSearchBar QLabel#searchMatchStatus {{
        color: {Theme.TEXT_MUTED};
        background: transparent;
        padding: 0 4px;
    }}

    QWidget#textSearchBar QLabel#searchMatchStatus[kind="empty"] {{
        color: {Theme.DANGER};
    }}

    QWidget#textSearchBar QToolButton {{
        min-width: 48px;
        padding: 5px 10px;
    }}

    QToolButton {{
        background-color: {Theme.SURFACE_RAISED};
        color: {Theme.TEXT};
        border: 1px solid {Theme.BORDER};
        border-radius: 8px;
        padding: 6px 10px;
    }}

    QToolButton:hover {{
        border-color: {Theme.ACCENT};
    }}

    QToolButton:disabled {{
        color: {Theme.TEXT_MUTED};
    }}

    QToolButton#collapseToggle {{
        background: transparent;
        border: none;
        color: {Theme.ACCENT};
        font-weight: 600;
        padding: 4px 2px;
        text-align: left;
    }}

    QToolButton#collapseToggle:hover {{
        color: {Theme.ACCENT_HOVER};
        border: none;
        background: transparent;
    }}

    QFrame#notificationBanner {{
        background-color: {Theme.SURFACE_RAISED};
        color: {Theme.TEXT};
        border: 1px solid {Theme.BORDER};
        border-radius: 10px;
    }}

    QFrame#notificationBanner[kind="info"] {{
        border: 1px solid {Theme.ACCENT};
        background-color: #1E2C31;
    }}

    QFrame#notificationBanner[kind="success"] {{
        border: 1px solid {Theme.SUCCESS};
        background-color: #1C2A22;
    }}

    QFrame#notificationBanner[kind="warning"] {{
        border: 1px solid #FFB74D;
        background-color: #2A2418;
    }}

    QFrame#notificationBanner[kind="error"] {{
        border: 1px solid {Theme.DANGER};
        background-color: #2A1C1C;
    }}

    QLabel#notificationBannerText {{
        background: transparent;
        color: {Theme.TEXT};
        font-weight: 600;
        font-size: 12px;
    }}
    """
