import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QCoreApplication
from ui.main_window import PetMainWindow
from utils.logger import logger
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pygame.pkgdata")

def main():
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    except AttributeError:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    window = PetMainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
