from PySide6.QtWidgets import QApplication,QLabel,QWidget,QVBoxLayout,QLineEdit,QPushButton
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt,QPoint
import sys
import requests

class PetMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
    def initUI(self):
            self.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.SubWindow)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.resize(200,200)
            self.is_dragging = False

            self.layout=QVBoxLayout()
            self.layout.setAlignment(Qt.AlignCenter)

            self.pet_label=QLabel(self)
            self.pet_pixmap=QPixmap("").scaled(180,180,Qt.KeepAspectRatio,Qt.SmoothTransformation)
            self.pet_label.setPixmap(self.pet_pixmap)
            self.layout.addWidget(self.pet_label,alignment=Qt.AlignCenter)

            self.input_box=QLineEdit(self)
            self.input_box.setPlaceholderText("speek")
            self.input_box.hide()
            self.send_btn=QPushButton("push",self)
            self.send_btn.hide()
            self.send_btn.clicked.connect(self.send_to_ai)

            self.reply_label=QLabel(self)
            self.reply_label.setWordWrap(True)
            self.reply_label.setStyleSheet("background:white; border-radius:10px;padding:10px;")
            self.reply_label.hide()

            self.layout.addWidget(self.input_box)
            self.layout.addWidget(self.send_btn)
            self.layout.addWidget(self.reply_label,alignment=Qt.AlignCenter)


    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.drag_position=event.globalPosition().toPoint()-self.pos()
            self.is_dragging=True
            self.input_box.show()
            self.send_btn.show()
            self.reply_label.show()
            self.reply_label.hide()


    def mouseMoveEvent(self,event):
        if self.is_dragging:
            self.move(event.globalPosition().toPoint() - self.drag_position)

    def mouseReleaseEvent(self,event):
        self.is_dragging=False


    def send_to_ai(self):
        user_input=self.input_box.text()
        if not user_input:
            return
        reply=self.get_ai_reply(user_input)
        self.reply_label.setText(reply)
        self.reply_label.show()
        self.input_box.clear()

    def get_ai_reply(self, user_input):
        url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
        headers = {
            "Authorization": "Bearer 90d84c3f-e6c0-411c-a046-fc9db871fd3e",
            "Content-Type": "application/json"  # 修正为标准驼峰写法
        }
        data = {
            "model": "doubao-seed-2-0-pro-260215",
            "messages": [  # 关键修正：单数message → 复数messages
                {"role": "system", "content": "你是一只可爱的桌面宠物Doro，性格活泼，喜欢吃欧润橘，用人称呼用户"},
                {"role": "user", "content": user_input},
            ]
        }
        try:
            res = requests.post(url, json=data, headers=headers)
            res.raise_for_status()  # 主动检查HTTP状态码，提前发现错误
            # 修正API返回路径：choice → choices（复数）
            return res.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"❌ API 请求失败: {e}")
            if 'res' in locals():
                print(f"📄 服务器响应详情: {res.text}")
            return f"人说的{user_input}Doro听到啦~~~"

if __name__=="__main__":
    app=QApplication(sys.argv)
    window=PetMainWindow()
    window.show()
    app.exit(app.exec())








