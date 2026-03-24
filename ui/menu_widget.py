from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QAction
from PySide6.QtCore import QObject, Signal
from utils.config_loader import ConfigLoader

class PetMenu(QMenu):
    feed_orange = Signal()
    show_about = Signal()
    exit_app = Signal()
    reload_config = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ConfigLoader()
        self.setStyleSheet("""
            QMenu {
                background-color: rgba(255, 182, 193, 220);
                color: white;
                border-radius: 8px;
                padding: 5px;
                font-size: 14px;
                font-family: "微软雅黑", "Microsoft YaHei", "SimHei", "黑体", "PingFang SC", sans-serif;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 5px;
            }
            QMenu::item:hover {
                background-color: rgba(255, 105, 180, 220);
            }
        """)
        self._init_actions()

    def _init_actions(self):
        # 投喂橘子
        self.feed_action = QAction("🍊 给Doro喂橘子", self)
        self.feed_action.triggered.connect(self.feed_orange.emit)
        self.addAction(self.feed_action)

        # 关于Doro
        self.about_action = QAction("📖 关于Doro", self)
        self.about_action.triggered.connect(self.show_about.emit)
        self.addAction(self.about_action)

        # 重载配置
        self.reload_action = QAction("🔄 重载配置", self)
        self.reload_action.triggered.connect(self.reload_config.emit)
        self.addAction(self.reload_action)

        # 分隔线
        self.addSeparator()

        # 退出
        self.exit_action = QAction("❌ 退出", self)
        self.exit_action.triggered.connect(self.exit_app.emit)
        self.addAction(self.exit_action)