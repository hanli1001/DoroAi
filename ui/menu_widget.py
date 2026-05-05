"""哑光玻璃拟态右键菜单 — 悬浮感、薄边高光、莫兰迪色系"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PySide6.QtGui import QPainter, QPainterPath, QLinearGradient, QColor, QBrush, QPen, QFont
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QPoint, QPropertyAnimation, QEasingCurve


class _MenuButton(QPushButton):
    """菜单项按钮：悬停玻璃高亮"""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        self.setFixedHeight(38)
        self._hovered = False
        f = QFont()
        f.setFamilies(["微软雅黑", "Microsoft YaHei", "SimHei", "PingFang SC", "sans-serif"])
        f.setPixelSize(15)
        f.setWeight(QFont.Weight.Medium)
        self.setFont(f)
        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #3d3548;
                border: none;
                border-radius: 10px;
                padding: 6px 18px;
                text-align: left;
            }
        """)

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # 悬停高亮
        if self._hovered:
            r = QRectF(self.rect()).adjusted(4, 2, -4, -2)
            path = QPainterPath()
            path.addRoundedRect(r, 9, 9)
            grad = QLinearGradient(r.topLeft(), r.bottomRight())
            grad.setColorAt(0.0, QColor(230, 224, 236, 160))
            grad.setColorAt(1.0, QColor(220, 214, 228, 150))
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)
            # 高光线
            hp = QPen(QColor(255, 255, 255, 45), 0.5)
            painter.setPen(hp)
            painter.drawLine(QPointF(r.left() + 12, r.top() + 0.5),
                             QPointF(r.right() - 12, r.top() + 0.5))
        super().paintEvent(event)


class PetMenu(QWidget):
    """磨砂玻璃右键菜单 — 独立弹出窗口"""
    feed_orange = Signal()
    show_about = Signal()
    exit_app = Signal()
    reload_config = Signal()
    screen_capture = Signal()
    spawn_orange = Signal()
    toggle_tts = Signal()
    toggle_backend = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tts_enabled = True
        self._backend = "gpt_sovits"
        self._tts_btn = None
        self._backend_btn = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Popup |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAutoFillBackground(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(2)

        # TTS toggle button
        self._tts_btn = _MenuButton(self._tts_label())
        self._tts_btn.clicked.connect(lambda checked: self._on_click(self.toggle_tts))
        layout.addWidget(self._tts_btn)

        # Backend switch button
        self._backend_btn = _MenuButton(self._backend_label())
        self._backend_btn.clicked.connect(lambda checked: self._on_click(self.toggle_backend))
        layout.addWidget(self._backend_btn)

        items = [
            ("🍊  给Doro喂橘子", self.feed_orange),
            ("🍊  生成橘子", self.spawn_orange),
            ("📷  框选识别", self.screen_capture),
            ("📖  关于Doro", self.show_about),
            ("🔄  重载配置", self.reload_config),
            ("─", None),
            ("✕  退出", self.exit_app),
        ]
        for text, signal in items:
            if text == "─":
                sep = QWidget()
                sep.setFixedHeight(1)
                sep.setStyleSheet("background: rgba(185,178,192,70); margin: 3px 8px;")
                layout.addWidget(sep)
            else:
                btn = _MenuButton(text)
                btn.clicked.connect(lambda checked, s=signal: self._on_click(s))
                layout.addWidget(btn)
        self.adjustSize()

    def _tts_label(self):
        return "🔊  语音播报" if self._tts_enabled else "🔇  语音播报(已关)"

    def _backend_label(self):
        name = "本地克隆" if self._backend == "gpt_sovits" else "在线TTS"
        return f"🎤  语音引擎: {name}"

    def set_tts_enabled(self, enabled: bool):
        self._tts_enabled = enabled
        if self._tts_btn:
            self._tts_btn.setText(self._tts_label())

    def set_backend(self, backend: str):
        self._backend = backend
        if self._backend_btn:
            self._backend_btn.setText(self._backend_label())

    def _on_click(self, signal):
        self.hide()
        signal.emit()

    def exec(self, pos: QPoint):
        self.adjustSize()
        self.move(pos)
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        path = QPainterPath()
        path.addRoundedRect(r, 18, 18)

        # ── 软阴影（AO多层） ──
        s = QPainterPath()
        s.addRoundedRect(r.adjusted(1, 4, 0, 3), 18, 18)
        painter.fillPath(s, QColor(140, 132, 148, 28))
        s2 = QPainterPath()
        s2.addRoundedRect(r.adjusted(2, 1, -2, -1), 18, 18)
        painter.fillPath(s2, QColor(155, 148, 162, 18))

        # ── 磨砂玻璃基底 ──
        base = QLinearGradient(r.topLeft(), r.bottomRight())
        base.setColorAt(0.0, QColor(252, 251, 253, 175))
        base.setColorAt(0.3, QColor(248, 246, 250, 178))
        base.setColorAt(0.7, QColor(244, 242, 248, 172))
        base.setColorAt(1.0, QColor(249, 247, 251, 175))
        painter.setBrush(QBrush(base))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)

        # ── 顶光柔光 ──
        light_rect = QRectF(r.left() + 5, r.top() + 3, r.width() - 10, r.height() * 0.35)
        lp = QPainterPath()
        lp.addRoundedRect(light_rect, 14, 14)
        lg = QLinearGradient(light_rect.topLeft(), light_rect.bottomLeft())
        lg.setColorAt(0.0, QColor(255, 255, 255, 38))
        lg.setColorAt(0.6, QColor(255, 255, 255, 10))
        lg.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(lg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(lp)

        # ── 哑光细边框 ──
        pen = QPen(QColor(182, 176, 190, 145), 1.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(r.adjusted(0.4, 0.4, -0.4, -0.4), 18, 18)

        # ── 顶边高光线 ──
        hp = QPen(QColor(255, 255, 255, 50), 0.5)
        hp.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(hp)
        painter.drawLine(QPointF(r.left() + 20, r.top() + 0.5),
                         QPointF(r.right() - 20, r.top() + 0.5))
