import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QCoreApplication
from ui.main_window import PetMainWindow
from utils.logger import logger
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pygame.pkgdata")

def _global_exception_hook(exc_type, exc_value, exc_tb):
    import traceback
    tb_text = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical(f"未捕获异常，进程即将退出:\n{tb_text}")
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _global_exception_hook

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
