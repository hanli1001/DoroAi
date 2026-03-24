import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QCoreApplication
from ui.main_window import PetMainWindow
from utils.logger import logger


QCoreApplication.setAttribute(Qt.AA_UseDesktopOpenGL, True)


try:

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
except AttributeError:
    # 兼容PySide6旧版本
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

# 3. 渲染优化，避免窗口闪烁
QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings, True)


def main():
    logger.info("Doro桌面宠物启动中...")
    # 初始化Qt应用
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    # 创建主窗口并显示
    window = PetMainWindow()
    window.show()
    logger.info("Doro启动完成！")

    # 启动应用事件循环
    sys.exit(app.exec())


if __name__ == "__main__":
    main()