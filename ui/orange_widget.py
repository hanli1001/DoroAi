from PySide6.QtWidgets import QWidget, QLabel
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtCore import Qt, QPoint, Signal, QPropertyAnimation, QEasingCurve
from utils.path_utils import get_resource_path
from utils.logger import logger

class OrangeWidget(QWidget):
    # 橘子位置实时更新信号，用于视线跟踪
    orange_moved = Signal(QPoint)
    # 橘子被拖拽信号
    orange_dragged = Signal()
    # 橘子被释放信号
    orange_released = Signal()

    def __init__(self, parent=None):
        super().__init__()
        # 窗口核心配置
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self.setFixedSize(80, 80)

        # 拖拽状态
        self._is_dragging = False
        self._mouse_start_pos = QPoint()
        self._window_start_pos = QPoint()

        # 橘子图片
        self.orange_label = QLabel(self)
        self.orange_label.setFixedSize(80, 80)
        # 请在resources/images/下放入orange.png橘子图片
        orange_pixmap = QPixmap(get_resource_path("resources/images/orange.png")).scaled(
            80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.orange_label.setPixmap(orange_pixmap)
        self.orange_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        logger.info("橘子窗口初始化完成")

    def paintEvent(self, event):
        pass

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._mouse_start_pos = event.globalPos()
            self._window_start_pos = self.pos()
            self.orange_dragged.emit()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            delta = event.globalPos() - self._mouse_start_pos
            self.move(self._window_start_pos + delta)
            # 实时发送位置信号（橘子中心点坐标）
            self.orange_moved.emit(self.pos() + QPoint(40, 40))
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            self.orange_released.emit()
            event.accept()

    def smooth_move_to(self, target_pos: QPoint, duration: int = 300):
        """平滑移动橘子，用于抢夺成功后的动画"""
        self.animation = QPropertyAnimation(self, b"pos")
        self.animation.setDuration(duration)
        self.animation.setEndValue(target_pos)
        self.animation.setEasingCurve(QEasingCurve.OutQuad)
        self.animation.start()