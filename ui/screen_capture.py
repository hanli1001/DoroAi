import sys
from PySide6.QtWidgets import QWidget, QApplication, QRubberBand
from PySide6.QtGui import QPainter, QColor, QPen, QPixmap
from PySide6.QtCore import Qt, QPoint, QRect, Signal, QSize
from utils.logger import logger

class ScreenCaptureWidget(QWidget):
    """全屏截图框选：先截全屏作背景，QRubberBand 框选区域"""
    capture_finished = Signal(QPixmap)

    def __init__(self):
        super().__init__()
        # 用简单的窗口标志
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setCursor(Qt.CursorShape.CrossCursor)

        # 截取全屏作为背景
        screen = QApplication.primaryScreen()
        screen_geo = screen.geometry()
        self.setGeometry(screen_geo)
        self._full_screenshot = screen.grabWindow(0)
        if self._full_screenshot.isNull():
            logger.error("全屏截图失败")
            self._full_screenshot = None

        self._origin = QPoint()
        self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self._rubber_band.setStyleSheet("background-color: transparent; border: 2px solid rgb(255,105,180);")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.globalPos()
            geo = QRect(self._origin, QSize())
            self._rubber_band.setGeometry(geo)
            self._rubber_band.show()
            event.accept()

    def mouseMoveEvent(self, event):
        if not self._origin.isNull():
            geo = QRect(self._origin, event.globalPos()).normalized()
            self._rubber_band.setGeometry(geo)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._origin.isNull():
            self._rubber_band.hide()
            rect = QRect(self._origin, event.globalPos()).normalized()
            if rect.width() > 10 and rect.height() > 10:
                try:
                    if self._full_screenshot and not self._full_screenshot.isNull():
                        cropped = self._full_screenshot.copy(rect)
                        if not cropped.isNull():
                            logger.info(f"截图完成: {rect.width()}x{rect.height()}")
                            self.capture_finished.emit(cropped)
                except Exception as e:
                    logger.error(f"截图失败: {e}", exc_info=True)
            self.close()
            event.accept()

    def paintEvent(self, event):
        if self._full_screenshot and not self._full_screenshot.isNull():
            painter = QPainter(self)
            # 全屏截图 + 半透明暗色遮罩
            painter.drawPixmap(self.rect(), self._full_screenshot)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
