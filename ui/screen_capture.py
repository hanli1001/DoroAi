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
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setCursor(Qt.CursorShape.CrossCursor)

        screen = QApplication.primaryScreen()
        self._screen = screen
        screen_geo = screen.geometry()
        self.setGeometry(screen_geo)
        # DPI缩放比：全屏截图是物理像素，鼠标坐标是逻辑像素
        self._dpr = screen.devicePixelRatio()
        self._full_screenshot = screen.grabWindow(0)
        if self._full_screenshot.isNull():
            logger.error("全屏截图失败")
            self._full_screenshot = None

        self._origin = QPoint()
        self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)

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
                        # 鼠标坐标是逻辑像素，截图是物理像素，需要乘DPR
                        dpr_rect = QRect(
                            int(rect.x() * self._dpr),
                            int(rect.y() * self._dpr),
                            int(rect.width() * self._dpr),
                            int(rect.height() * self._dpr),
                        )
                        cropped = self._full_screenshot.copy(dpr_rect)
                        if not cropped.isNull():
                            logger.info(f"截图完成: {rect.width()}x{rect.height()} dpr={self._dpr}")
                            self.capture_finished.emit(cropped)
                except Exception as e:
                    logger.error(f"截图失败: {e}", exc_info=True)
            self.close()
            event.accept()

    def paintEvent(self, event):
        if self._full_screenshot and not self._full_screenshot.isNull():
            painter = QPainter(self)
            painter.drawPixmap(self.rect(), self._full_screenshot)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
