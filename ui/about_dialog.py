from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
from PySide6.QtCore import Qt
from utils.config_loader import ConfigLoader


class AboutDoroDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = ConfigLoader()
        self.setWindowTitle("关于Doro")
        self.setFixedSize(500, 600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)

        self.text_edit = QTextEdit()
        self.text_edit.setText(self.config.get_config("character.background", ""))
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

        self.close_btn = QPushButton("知道啦")
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)