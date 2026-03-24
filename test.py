import sys
import requests
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
                               QLineEdit, QPushButton, QScrollArea, QFrame)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont

class DoroPet(QWidget):
    def __init__(self):
        super().__init__()
        # 拖拽用的变量
        self.drag_start_pos = QPoint()
        self.is_dragging = False
        self.init_ui()

    def init_ui(self):
        # 窗口基础设置：无边框+置顶+透明背景
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(320, 400)

        # 主容器（实现圆角+半透明背景）
        self.main_frame = QFrame(self)
        self.main_frame.setGeometry(0, 0, self.width(), self.height())
        self.main_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 240, 245, 220);
                border-radius: 16px;
                border: 1px solid rgba(255, 182, 193, 180);
            }
        """)

        # 主布局
        main_layout = QVBoxLayout(self.main_frame)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 顶部标题+关闭按钮
        self.title_label = QLabel("Doro🐾")
        self.title_label.setFont(QFont("微软雅黑", 12, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #FF69B4; padding-left: 8px;")
        self.title_label.setAlignment(Qt.AlignLeft)

        # 关闭按钮
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 105, 180, 150);
                color: white;
                border-radius: 12px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FF69B4;
            }
        """)
        self.close_btn.clicked.connect(self.close)

        # 顶部布局组装
        top_bar = QWidget()
        top_bar_layout = QVBoxLayout(top_bar)
        top_bar_layout.addWidget(self.title_label)
        top_bar_layout.addWidget(self.close_btn, alignment=Qt.AlignRight)
        main_layout.addWidget(top_bar)

        # 对话气泡滚动区域（长文本自动滚动）
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 182, 193, 180);
                border-radius: 3px;
                min-height: 20px;
            }
        """)

        # 对话内容容器
        self.chat_content = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_content)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.setSpacing(10)
        self.scroll_area.setWidget(self.chat_content)
        main_layout.addWidget(self.scroll_area)

        # 输入框+发送按钮
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("和Doro说点什么吧~")
        self.input_box.setFont(QFont("微软雅黑", 10))
        self.input_box.setStyleSheet("""
            QLineEdit {
                border: 1px solid rgba(255, 182, 193, 200);
                border-radius: 12px;
                padding: 10px 12px;
                background-color: rgba(255, 255, 255, 180);
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #FF69B4;
            }
        """)
        # 回车发送
        self.input_box.returnPressed.connect(self.on_send)

        self.send_btn = QPushButton("发送")
        self.send_btn.setFont(QFont("微软雅黑", 10, QFont.Weight.Bold))
        self.send_btn.setFixedHeight(36)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 182, 193, 200);
                color: white;
                border-radius: 12px;
                padding: 0 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #FF69B4;
            }
            QPushButton:pressed {
                background-color: #FF1493;
            }
        """)
        self.send_btn.clicked.connect(self.on_send)

        # 输入区域组装
        input_bar = QWidget()
        input_bar_layout = QVBoxLayout(input_bar)
        input_bar_layout.addWidget(self.input_box)
        input_bar_layout.addWidget(self.send_btn, alignment=Qt.AlignRight)
        main_layout.addWidget(input_bar)

        # 初始欢迎消息
        self.add_bubble("Doro在这里！有什么想和我说的吗~", is_ai=True)

    # 添加对话气泡
    def add_bubble(self, text, is_ai=False):
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setFont(QFont("微软雅黑", 11))
        bubble.setMaximumWidth(self.width() - 60)

        # AI气泡和用户气泡样式区分
        if is_ai:
            bubble.setStyleSheet("""
                QLabel {
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FFB6C1, stop:1 #FF69B4);
                    color: white;
                    border-radius: 12px;
                    padding: 10px 14px;
                }
            """)
            self.chat_layout.addWidget(bubble, alignment=Qt.AlignLeft)
        else:
            bubble.setStyleSheet("""
                QLabel {
                    background-color: rgba(255, 255, 255, 200);
                    color: #333333;
                    border-radius: 12px;
                    padding: 10px 14px;
                    border: 1px solid rgba(255, 182, 193, 150);
                }
            """)
            self.chat_layout.addWidget(bubble, alignment=Qt.AlignRight)

        # 自动滚动到底部
        self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        )

    def on_send(self):
        user_input = self.input_box.text().strip()
        if not user_input:
            return

        # 添加用户气泡
        self.add_bubble(user_input, is_ai=False)
        self.input_box.clear()

        # 获取AI回复
        reply = self.get_ai_reply(user_input)
        # 添加AI气泡
        self.add_bubble(reply, is_ai=True)

    def get_ai_reply(self, user_input):
        # 火山引擎方舟 API 配置（已修正完整地址）
        url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
        headers = {
            "Authorization": "Bearer 90d84c3f-e6c0-411c-a046-fc9db871fd3e",
            "Content-Type": "application/json"
        }
        data = {
            "model": "doubao-seed-2-0-pro-260215",
            "messages": [
                {"role": "system", "content": "你是一只可爱的桌面宠物Doro，性格活泼，喜欢吃欧润橘，用人称呼用户，说话简短可爱，不要说太长的句子"},
                {"role": "user", "content": user_input}
            ]
        }
        try:
            res = requests.post(url, json=data, headers=headers, timeout=10)
            res.raise_for_status()
            return res.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"❌ API 请求失败: {e}")
            if 'res' in locals():
                print(f"📄 服务器响应: {res.text}")
            return f"人说的{user_input}，Doro听到啦~🐾"

    # 窗口拖拽功能实现
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.is_dragging = True

    def mouseMoveEvent(self, event):
        if self.is_dragging and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_start_pos)

    def mouseReleaseEvent(self, event):
        self.is_dragging = False

    # 窗口大小变化时自适应
    def resizeEvent(self, event):
        self.main_frame.resize(self.width(), self.height())
        super().resizeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 全局字体设置
    app.setFont(QFont("微软雅黑"))
    pet = DoroPet()
    pet.show()
    sys.exit(app.exec())