"""Pixel-card workshop theme, isolated from the player's global appearance."""
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QComboBox, QLabel


class PixelTitle(QLabel):
    """Rasterize only the short brand title; editable text stays full resolution."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._title_cache = None
        self.setMinimumSize(self.sizeHint())

    def sizeHint(self):
        return QSize(188, 44)

    def paintEvent(self, event):
        from pet.settings_widgets import _widget_dark
        key = (self.text(), _widget_dark(self))
        if self._title_cache is None or self._title_cache[0] != key:
            font = QFont("Microsoft YaHei UI")
            font.setPixelSize(14)
            font.setBold(True)
            font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
            metrics = QFontMetrics(font)
            image = QPixmap(metrics.horizontalAdvance(self.text()) + 5, metrics.height() + 5)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setFont(font)
            baseline = metrics.ascent() + 1
            painter.setPen(QColor("#070c16" if key[1] else "#b8c0ca"))
            painter.drawText(3, baseline + 3, self.text())
            painter.setPen(QColor("#91622f" if key[1] else "#6b4423"))
            painter.drawText(1, baseline + 1, self.text())
            painter.setPen(QColor("#f1c35c" if key[1] else "#8c5a19"))
            painter.drawText(0, baseline, self.text())
            painter.setClipRect(0, 0, image.width(), max(1, baseline - 7))
            painter.setPen(QColor("#fff2c8" if key[1] else "#554128"))
            painter.drawText(0, baseline, self.text())
            painter.end()
            self._title_cache = (key, image.scaled(
                image.size() * 2, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation))
        image = self._title_cache[1]
        painter = QPainter(self)
        painter.drawPixmap(0, max(0, (self.height() - image.height()) // 2), image)


class CharacterPreview(QLabel):
    """A gridded inspection surface with the actual imported character."""

    def sizeHint(self):
        return QSize(320, 180)

    def minimumSizeHint(self):
        return QSize(180, 140)

    def paintEvent(self, event):
        from pet.settings_widgets import _widget_dark
        dark = _widget_dark(self)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111a29" if dark else "#e5eaf0"))
        painter.setPen(QColor("#202c3d" if dark else "#d4dce5"))
        for x in range(0, self.width(), 20):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 20):
            painter.drawLine(0, y, self.width(), y)
        painter.setPen(QColor("#9a7c42" if dark else "#8b734b"))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        source = self.pixmap()
        if source and not source.isNull():
            bounds = QRect(16, 16, max(1, self.width() - 32), max(1, self.height() - 32))
            size = source.size().scaled(bounds.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRect(QPoint(), size)
            target.moveCenter(bounds.center())
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(target, source)
        else:
            painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


def paint_workshop_background(dialog):
    painter = QPainter(dialog)
    painter.drawTiledPixmap(dialog.rect(), dialog._workshop_texture)


class WorkshopSelect(QComboBox):
    """Keep native selection behavior with the shared visible chevron."""

    def paintEvent(self, event):
        super().paintEvent(event)
        from pet.settings_widgets import _draw_chevron
        _draw_chevron(self, self.height() / 2.0, down=True)


def apply_workshop_theme(dialog, dark=True):
    from pet.settings_theme_qss import _settings_stylesheet
    from pet.settings_widgets import refresh_settings_icons

    bg, panel, field, text, muted, border, accent, selected, warm = (
        ("#101725", "#171f30", "#1d2839", "#f2ecd9", "#b8b8b3",
         "#79643e", "#f2ca6d", "#492c35", "#e7b85a") if dark else
        ("#eef0f4", "#ffffff", "#f4f5f8", "#252a35", "#626574",
         "#9b835b", "#815a19", "#e9dbe0", "#805215"))
    button_fill = "#e7bc5b" if dark else "#f0d18a"
    button_ink = "#271d16"
    tile = QPixmap(8, 8)
    tile.fill(QColor(bg))
    painter = QPainter(tile)
    painter.fillRect(0, 0, 1, 1, QColor("#172032" if dark else "#e2e6ed"))
    painter.fillRect(4, 4, 1, 1, QColor("#151d2b" if dark else "#e7eaf0"))
    painter.end()
    dialog._workshop_texture = tile
    dialog.setProperty("menuStyle", "modern")
    dialog.setProperty("modernStyle", True)
    dialog.setProperty("settingsDark", dark)
    palette = dialog.palette()
    for role, color in (
        (QPalette.Window, bg), (QPalette.WindowText, text),
        (QPalette.Base, field), (QPalette.AlternateBase, panel),
        (QPalette.Text, text), (QPalette.Button, panel),
        (QPalette.ButtonText, text), (QPalette.Highlight, selected),
        (QPalette.HighlightedText, text), (QPalette.PlaceholderText, muted),
    ):
        palette.setColor(role, QColor(color))
    dialog.setPalette(palette)
    dialog.setStyleSheet(_settings_stylesheet("dark" if dark else "light") + f"""
        QDialog#characterStudio {{ background: {bg}; }}
        QDialog#characterStudio QWidget {{
            color: {text}; font-family: "Microsoft YaHei UI"; font-size: 13px;
            selection-background-color: {selected}; selection-color: {text};
        }}
        QDialog#characterStudio QLabel {{ background: transparent; }}
        QDialog#characterStudio QLabel#studioTitle {{
            color: {accent};
        }}
        QDialog#characterStudio QLabel[studioSection="true"] {{
            color: {accent}; font-size: 12px; font-weight: 600;
            padding: 6px 0px; border-bottom: 1px solid {border};
        }}
        QDialog#characterStudio QLabel#animationHint {{
            color: {warm}; padding: 8px 10px; border-left: 2px solid {warm};
            background: {selected};
        }}
        QDialog#characterStudio QLabel#studioStatus {{
            color: {muted}; border-top: 1px solid {border}; padding-top: 10px;
        }}
        QDialog#characterStudio QScrollArea, QWidget#studioPage {{
            background: transparent; border: none;
        }}
        QDialog#characterStudio QStackedWidget {{ background: transparent; }}
        QDialog#characterStudio QTabWidget::pane {{
            border: none; border-top: 1px solid {border}; top: -1px;
        }}
        QDialog#characterStudio QTabBar::tab {{
            background: {panel}; color: {text}; padding: 10px 22px;
            border: 1px solid {border}; border-bottom: 4px solid {border}; margin-right: 8px;
        }}
        QDialog#characterStudio QTabBar::tab:selected {{
            color: {accent}; background: {selected}; border-bottom-color: {accent};
        }}
        QDialog#characterStudio QTabBar::tab:hover {{ color: {text}; background: {panel}; }}
        QDialog#characterStudio QLineEdit, QDialog#characterStudio QPlainTextEdit,
        QDialog#characterStudio QComboBox, QDialog#characterStudio QDoubleSpinBox {{
            background: {field}; color: {text}; border: 1px solid {border};
            border-radius: 0px; padding: 9px;
        }}
        QDialog#characterStudio QLineEdit:focus, QDialog#characterStudio QPlainTextEdit:focus,
        QDialog#characterStudio QComboBox:focus, QDialog#characterStudio QDoubleSpinBox:focus {{
            border: 1px solid {accent}; padding: 9px;
        }}
        QDialog#characterStudio QPlainTextEdit#promptOutput {{
            background: {panel}; border-top: 3px solid {accent};
            font-family: "Cascadia Code", "Microsoft YaHei UI", "Consolas";
            font-size: 12px; padding: 14px;
        }}
        QDialog#characterStudio QPlainTextEdit#processLog {{
            background: {panel}; color: {muted}; font-family: "Consolas";
        }}
        QDialog#characterStudio QComboBox {{ padding-right: 28px; }}
        QDialog#characterStudio QComboBox::drop-down {{
            border: none; width: 24px;
        }}
        QDialog#characterStudio QComboBox::down-arrow {{ image: none; }}
        QDialog#characterStudio QComboBox QAbstractItemView {{
            background: {field}; color: {text}; border: 1px solid {border};
            selection-background-color: {selected}; selection-color: {text};
        }}
        QDialog#characterStudio QPushButton {{
            background: {panel}; color: {text}; border: 1px solid {border};
            border-bottom: 4px solid {border}; border-radius: 0px; padding: 8px 14px;
        }}
        QDialog#characterStudio QPushButton:hover {{
            background: {selected}; border-color: {accent};
        }}
        QDialog#characterStudio QPushButton:pressed {{
            background: {selected}; border-bottom-color: {panel};
        }}
        QDialog#characterStudio QPushButton:focus {{ border-color: {accent}; }}
        QDialog#characterStudio QPushButton[studioPrimary="true"] {{
            background: {button_fill}; color: {button_ink}; border-color: {accent};
            border-bottom-color: #96703b; font-weight: 600;
        }}
        QDialog#characterStudio QPushButton[studioPrimary="true"]:hover {{
            background: #f4d58e; color: {button_ink};
        }}
        QDialog#characterStudio QPushButton[studioPrimary="true"]:pressed {{
            background: #cca04b; color: {button_ink}; border-bottom-color: #cca04b;
        }}
        QDialog#characterStudio QWidget:disabled {{ color: {muted}; }}
        QDialog#characterStudio QPushButton:disabled {{
            background: {bg}; border-color: {border}; color: {muted};
        }}
        QDialog#characterStudio QListWidget {{
            background: {panel}; border: 1px solid {border}; border-radius: 0px; padding: 5px;
        }}
        QDialog#characterStudio QListWidget::item {{
            padding: 10px 8px; border-bottom: 1px solid {border};
        }}
        QDialog#characterStudio QListWidget::item:selected {{
            background: {selected}; color: {accent}; border-bottom-color: {accent};
        }}
        QDialog#characterStudio QListWidget::item:hover {{ background: {field}; }}
        QDialog#characterStudio QLabel#petPreview {{
            color: {muted};
        }}
        QDialog#characterStudio QCheckBox {{ spacing: 8px; background: transparent; }}
        QDialog#characterStudio QCheckBox::indicator {{
            width: 16px; height: 16px; border-radius: 0px;
            border: 1px solid {border}; background: {field};
        }}
        QDialog#characterStudio QCheckBox::indicator:checked {{
            background: {accent}; border-color: {accent};
        }}
        QDialog#characterStudio QCheckBox::indicator:hover {{ border-color: {accent}; }}
        QDialog#characterStudio QProgressBar {{
            background: {field}; border: 1px solid {border}; border-radius: 0px;
            color: {text}; min-height: 18px; text-align: center;
        }}
        QDialog#characterStudio QProgressBar::chunk {{ background: #8c6835; }}
        QDialog#characterStudio QSplitter::handle {{ background: transparent; }}
        QDialog#characterStudio QSplitter::handle:hover {{ background: {border}; }}
        QDialog#characterStudio QScrollBar:vertical {{
            background: {bg}; width: 8px; margin: 0px;
        }}
        QDialog#characterStudio QScrollBar::handle:vertical {{
            background: {border}; min-height: 28px; border-radius: 0px;
        }}
        QDialog#characterStudio QScrollBar::add-line:vertical,
        QDialog#characterStudio QScrollBar::sub-line:vertical {{ height: 0px; }}
        QDialog#characterStudio QScrollBar::add-page:vertical,
        QDialog#characterStudio QScrollBar::sub-page:vertical {{ background: transparent; }}
    """)
    refresh_settings_icons(dialog)
