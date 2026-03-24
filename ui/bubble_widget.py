from PySide6.QtWidgets import QLabel
from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen, QBrush
from PySide6.QtCore import Qt, QPoint, QRect, QSize
from utils.config_loader import ConfigLoader

class BubbleLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ConfigLoader()
        self.setWordWrap(True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        self.setStyleSheet("background-color: transparent;")

        # 从配置加载参数
        self.setMinimumWidth(self.config.get_config("bubble.min_width", 100))
        self.setMaximumWidth(self.config.get_config("bubble.max_width", 280))
        self.setMinimumHeight(self.config.get_config("bubble.min_height", 45))

        bg_color = self.config.get_config("bubble.bg_color", [255, 182, 193, 160])
        border_color = self.config.get_config("bubble.border_color", [255, 255, 255, 180])
        self.bg_color = QColor(*bg_color)
        self.border_color = QColor(*border_color)

        self.bubble_direction = "right"
        self.arrow_size = 12
        self.border_radius = 18
        self.padding = 12

    def set_direction(self, direction):
        if direction in ["left", "right"]:
            self.bubble_direction = direction
            self.update()

    def sizeHint(self):
        base_size = super().sizeHint()
        content_width = max(base_size.width(), self.minimumWidth() - self.arrow_size - self.padding * 2)
        content_height = max(base_size.height(), self.minimumHeight() - self.padding * 2)
        total_width = content_width + self.arrow_size + self.padding * 2
        total_height = content_height + self.padding * 2
        return QSize(total_width, total_height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(self.border_color, 1.5))
        painter.setBrush(QBrush(self.bg_color))

        rect = self.rect()
        bubble_rect = QRect(rect)

        if self.bubble_direction == "right":
            bubble_rect.setLeft(rect.left() + self.arrow_size)
        else:
            bubble_rect.setRight(rect.right() - self.arrow_size)

        # 绘制气泡主体
        bubble_path = QPainterPath()
        bubble_path.addRoundedRect(bubble_rect, self.border_radius, self.border_radius)

        # 绘制箭头
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

        # 绘制文字
        text_rect = bubble_rect.adjusted(self.padding, self.padding, -self.padding, -self.padding)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(text_rect, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter, self.text())