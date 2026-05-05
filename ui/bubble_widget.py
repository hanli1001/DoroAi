from PySide6.QtWidgets import QLabel
from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen, QBrush, QFont
from PySide6.QtCore import Qt, QPoint, QRect, QSize
from utils.config_loader import ConfigLoader

class BubbleLabel(QLabel):
    """气泡对话框 — 作为子控件依附于主窗口，通过 WA_NativeWindow 获得独立 HWND"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ConfigLoader()
        self.setWordWrap(True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        self.setStyleSheet("background: transparent; border: none;")

        self.min_width = self.config.get_config("bubble.min_width", 100)
        self.max_width = self.config.get_config("bubble.max_width", 280)
        self.min_height = self.config.get_config("bubble.min_height", 45)
        self.setMaximumWidth(self.max_width)
        self.setMinimumSize(self.min_width, self.min_height)

        bg_color = self.config.get_config("bubble.bg_color", [255, 182, 193, 160])
        border_color = self.config.get_config("bubble.border_color", [255, 255, 255, 180])
        self.bg_color = QColor(*bg_color)
        self.border_color = QColor(*border_color)
        self.bubble_direction = "right"
        self.arrow_size = 12
        self.border_radius = 18
        self.padding = 12

        font = QFont()
        font.setFamilies(["微软雅黑", "Microsoft YaHei", "SimHei", "PingFang SC",
                          "Noto Sans CJK SC", "sans-serif"])
        font.setPixelSize(16)
        self.setFont(font)

    def set_direction(self, direction):
        if direction in ["left", "right"]:
            self.bubble_direction = direction
            self.update()

    def sizeHint(self):
        base_size = super().sizeHint()
        content_width = max(base_size.width(), self.min_width - self.arrow_size - self.padding * 2)
        content_height = max(base_size.height(), self.min_height - self.padding * 2)
        total_width = content_width + self.arrow_size + self.padding * 2
        total_height = content_height + self.padding * 2
        return QSize(min(total_width, self.max_width), total_height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setPen(QPen(self.border_color, 1.5))
        painter.setBrush(QBrush(self.bg_color))

        rect = self.rect()
        bubble_rect = QRect(rect)
        if self.bubble_direction == "right":
            bubble_rect.setLeft(rect.left() + self.arrow_size)
        else:
            bubble_rect.setRight(rect.right() - self.arrow_size)

        bubble_path = QPainterPath()
        bubble_path.addRoundedRect(bubble_rect, self.border_radius, self.border_radius)

        arrow_y = bubble_rect.center().y()
        if self.bubble_direction == "right":
            arrow_points = [
                QPoint(bubble_rect.left(), arrow_y - self.arrow_size // 2),
                QPoint(bubble_rect.left(), arrow_y + self.arrow_size // 2),
                QPoint(rect.left(), arrow_y)
            ]
        else:
            arrow_points = [
                QPoint(bubble_rect.right(), arrow_y - self.arrow_size // 2),
                QPoint(bubble_rect.right(), arrow_y + self.arrow_size // 2),
                QPoint(rect.right(), arrow_y)
            ]
        bubble_path.addPolygon(arrow_points)
        painter.drawPath(bubble_path)

        text_rect = bubble_rect.adjusted(self.padding, self.padding, -self.padding, -self.padding)
        painter.setPen(QColor(65, 25, 35))
        painter.setFont(self.font())
        painter.drawText(text_rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter, self.text())
