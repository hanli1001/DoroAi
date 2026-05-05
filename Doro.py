from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
import sys
from utils.path_utils import get_resource_path

class PetWidget(QWidget):
    """独立的透明桌宠窗口示例"""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), Qt.GlobalColor.transparent)
        self.setPalette(palette)

        self.resize(300, 300)
        self.pet_img = QPixmap(get_resource_path("resources/images/logo.png"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        if not self.pet_img.isNull():
            painter.drawPixmap(self.rect(), self.pet_img)

if __name__ == "__main__":
    import os
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

    app = QApplication(sys.argv)
    try:
        app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)
    except AttributeError:
        pass

    pet_window = PetWidget()
    pet_window.show()
    sys.exit(app.exec())
