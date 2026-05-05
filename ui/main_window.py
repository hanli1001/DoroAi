import random
import json
import sys
from utils.config_loader import ConfigLoader
from PySide6.QtWidgets import QWidget, QApplication, QLineEdit, QPushButton, QLabel, QScrollArea, QHBoxLayout, QVBoxLayout
from PySide6.QtGui import QPixmap, QMovie, Qt, QPainter, QPainterPath, QColor, QPen, QBrush, QFont, QLinearGradient
from PySide6.QtCore import QPoint, QElapsedTimer, QThread, QTimer, QPropertyAnimation, QEasingCurve, QRect
from utils.path_utils import get_resource_path
from utils.logger import logger
from ui.menu_widget import PetMenu
from ui.about_dialog import AboutDoroDialog
from ui.orange_widget import OrangeWidget
from ui.screen_capture import ScreenCaptureWidget
from ui.glass_widget import GlassBorderWidget
from core.event_system import event_bus
from core.pet_state import PetStateMachine, PetState
from core.action_manager import ActionManager
from core.command_parser import CommandParser
from core.ocr_worker import OCRWorker
from ai.ai_worker import AIWorker
from ai.memory_manager import MemoryManager
from utils.tts_engine import TTSEngine


class PetMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.config = ConfigLoader()

        self._mouse_start_pos = QPoint()
        self._window_start_pos = QPoint()
        self._is_dragging = False
        self._move_threshold = self.config.get_config("window.move_threshold", default=10)
        self._click_threshold = self.config.get_config("window.click_threshold", default=400)
        self._press_timer = QElapsedTimer()
        self.is_panel_show = False
        self.last_interact_time = QElapsedTimer()
        self.last_interact_time.start()
        self.current_reply = ""
        self._last_ocr_text = ""  # 最近一次OCR识别文本
        self._conversation_history = []  # 对话上下文记忆 [(role, content), ...]
        self._is_ocr_answer = False  # 当前回复是否为OCR答案（决定显示位置）

        self.memory_manager = MemoryManager()
        self.state_machine = PetStateMachine()
        self.action_manager = ActionManager(self.state_machine)
        self.command_parser = CommandParser(self.memory_manager)
        self.tts_engine = TTSEngine()

        self.orange_widget = None
        self.orange_grab_threshold = self.config.get_config("orange.grab_threshold", default=150)
        self.orange_grab_chance = self.config.get_config("orange.grab_chance", default=0.6)
        self.orange_chase_speed = self.config.get_config("orange.chase_speed", default=0.1)
        self.is_chasing = False

        self.roam_timer = QTimer(self)
        self.roam_timer.timeout.connect(self.trigger_roam)
        self.roam_min_interval = self.config.get_config("roam.min_interval", default=10000)
        self.roam_max_interval = self.config.get_config("roam.max_interval", default=30000)
        self.roam_min_duration = self.config.get_config("roam.min_duration", default=1000)
        self.roam_max_duration = self.config.get_config("roam.max_duration", default=8000)
        self.roam_animation = None
        self.is_roaming = False

        # 气泡绘制状态
        self._bubble_text = ""
        self._bubble_visible = False
        self._bubble_direction = "right"
        self._bubble_arrow_size = 12
        self._bubble_radius = 18
        self._bubble_padding = 12
        self._bubble_max_width = self.config.get_config("bubble.max_width", default=280)
        self._bubble_min_width = self.config.get_config("bubble.min_width", default=100)
        self._bubble_min_height = self.config.get_config("bubble.min_height", default=45)
        self._bubble_font = QFont()
        self._bubble_font.setFamilies(["微软雅黑", "Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC", "sans-serif"])
        self._bubble_font.setPixelSize(15)
        self._bubble_font.setWeight(QFont.Weight.Medium)

        self.initUI()
        self.init_ai_thread()
        self.init_ocr_thread()
        self.init_timers()
        self._register_event_handlers()
        self.show_doro_line("汪呜～主人好！我是Doro～")


    def nativeEvent(self, eventType, message):
        """WM_NCHITTEST: 防止透明窗口区域鼠标事件穿透"""
        if sys.platform != "win32":
            return super().nativeEvent(eventType, message)
        try:
            import ctypes
            from PySide6.QtCore import QByteArray
            if eventType != QByteArray(b"windows_generic_MSG"):
                return super().nativeEvent(eventType, message)
            class MSG(ctypes.Structure):
                _fields_ = [("hwnd", ctypes.c_void_p),
                            ("message", ctypes.c_uint),
                            ("wParam", ctypes.c_ulonglong),
                            ("lParam", ctypes.c_longlong),
                            ("time", ctypes.c_uint),
                            ("pt_x", ctypes.c_long),
                            ("pt_y", ctypes.c_long)]
            msg = ctypes.cast(message, ctypes.POINTER(MSG)).contents
            if msg.message == 0x0084:
                return True, 1
        except Exception:
            pass
        return super().nativeEvent(eventType, message)

    # ========== UI 初始化 ==========
    def initUI(self):
        window_width = self.config.get_config("window.width", default=400)
        window_height = self.config.get_config("window.height", default=300)
        self.setFixedSize(window_width, window_height)

        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setUpdatesEnabled(True)

        # 右键菜单
        self.right_menu = PetMenu()
        self.right_menu.feed_orange.connect(self.on_feed_orange)
        self.right_menu.show_about.connect(self.on_show_about)
        self.right_menu.exit_app.connect(self.on_exit_app)
        self.right_menu.reload_config.connect(self.on_reload_config)
        self.right_menu.screen_capture.connect(self.start_screen_capture)
        self.right_menu.spawn_orange.connect(self.spawn_orange)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_right_menu)

        # 宠物形象参数
        image_path = self.config.get_config("pet.image_path", default="resources/images/logo.png")
        self.image_width = self.config.get_config("pet.image_width", default=180)
        self.image_height = self.config.get_config("pet.image_height", default=200)
        self._load_pet_image(image_path)
        self._current_pixmap = self.default_pixmap
        self._current_movie = None
        self._pet_rect = QRect(0, 0, self.image_width, self.image_height)

        # 屏幕几何信息（多处使用）
        screen_geo = QApplication.primaryScreen().availableGeometry()

        # ===== OCR答案展示窗口（屏幕右上角，可滚动，可调色/字号） =====
        screen_w = screen_geo.width()
        screen_h = screen_geo.height()
        label_w = min(520, screen_w - 200)
        label_h = min(640, screen_h - 100)

        # 外层容器窗口
        self.answer_win = QWidget()
        self.answer_win.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.answer_win.setAttribute(Qt.WA_TranslucentBackground, True)
        self.answer_win.setAttribute(Qt.WA_NoSystemBackground, True)
        self.answer_win.setAutoFillBackground(False)
        self.answer_win.setFixedSize(label_w, label_h)
        self.answer_win.move(screen_w - label_w - 30, 30)
        self.answer_win.setStyleSheet("QWidget { background-color: transparent; }")

        # 滚动区域
        self.answer_scroll = QScrollArea()
        self.answer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.answer_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.answer_scroll.setWidgetResizable(True)
        self.answer_scroll.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
            QScrollBar:vertical { background: rgba(220,215,225,50); width: 5px; border-radius: 3px; }
            QScrollBar::handle:vertical { background: rgba(180,165,190,150); border-radius: 3px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        # 文字标签
        self.answer_label = QLabel()
        self.answer_font = QFont()
        self.answer_font.setFamilies(["字由奇巧体", "KaiTi", "楷体", "SimHei", "Microsoft YaHei", "sans-serif"])
        self.answer_font.setPixelSize(22)
        self.answer_font.setBold(True)
        self.answer_label.setFont(self.answer_font)
        self.answer_label.setStyleSheet("QLabel { background-color: transparent; color: #3d3548; border: none; padding: 16px; }")
        self.answer_label.setWordWrap(True)
        self.answer_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.answer_scroll.setWidget(self.answer_label)

        # 底部控制栏（颜色 + 字号）
        ctrl = QWidget()
        ctrl.setFixedHeight(36)
        ctrl.setStyleSheet("background-color: rgba(252,250,252,110); border-radius: 10px;")
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(8, 2, 8, 2)
        ctrl_layout.setSpacing(6)
        # 颜色按钮
        colors = [
            ("#3d3548", "炭灰"), ("#f5f2f6", "奶白"), ("#2a222e", "墨灰"),
            ("#b59595", "枯玫"), ("#95a0b5", "雾蓝"), ("#95a895", "青灰")
        ]
        for hex_color, tip in colors:
            btn = QPushButton()
            btn.setFixedSize(22, 22)
            btn.setToolTip(tip)
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: {hex_color}; border: 1px solid rgba(0,0,0,60); border-radius: 11px; }}
                QPushButton:hover {{ border: 2px solid rgba(255,105,180,200); }}
            """)
            btn.clicked.connect(lambda checked, c=hex_color: self._on_change_answer_color(c))
            ctrl_layout.addWidget(btn)
        ctrl_layout.addStretch()
        # 字号 -
        btn_small = QPushButton("A-")
        btn_small.setFixedSize(36, 24)
        btn_small.setStyleSheet("QPushButton { background: rgba(235,230,238,140); color: #4a4252; border-radius: 6px; font-weight: 600; } QPushButton:hover { background: rgba(210,195,215,160); }")
        btn_small.clicked.connect(self._on_font_smaller)
        ctrl_layout.addWidget(btn_small)
        # 字号标签
        self.font_size_label = QLabel("22")
        self.font_size_label.setFixedWidth(28)
        self.font_size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.font_size_label.setStyleSheet("QLabel { background: transparent; color: #4a4252; font-weight: 600; }")
        ctrl_layout.addWidget(self.font_size_label)
        # 字号 +
        btn_big = QPushButton("A+")
        btn_big.setFixedSize(36, 24)
        btn_big.setStyleSheet("QPushButton { background: rgba(235,230,238,140); color: #4a4252; border-radius: 6px; font-weight: 600; } QPushButton:hover { background: rgba(210,195,215,160); }")
        btn_big.clicked.connect(self._on_font_bigger)
        ctrl_layout.addWidget(btn_big)
        ctrl_layout.addStretch()
        # 关闭按钮
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(30, 24)
        btn_close.setStyleSheet("""
            QPushButton { background: rgba(190,170,185,140); color: #faf8fa; border-radius: 6px; font-weight: 600; font-size: 14px; }
            QPushButton:hover { background: rgba(170,145,165,200); }
        """)
        btn_close.clicked.connect(self.answer_win.hide)
        ctrl_layout.addWidget(btn_close)

        # 组装
        win_layout = QVBoxLayout(self.answer_win)
        win_layout.setContentsMargins(0, 0, 0, 0)
        win_layout.setSpacing(4)
        win_layout.addWidget(self.answer_scroll, 1)
        win_layout.addWidget(ctrl, 0)
        self.answer_win.hide()

        # 初始位置
        init_x = screen_geo.width() - window_width - 50
        init_y = screen_geo.height() - window_height - 100
        self.move(max(0, init_x), max(0, init_y))

        # 输入框 + 发送按钮（毛玻璃质感 + 炫彩边框）
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("  和Doro说点什么吧~")
        self.input_box.setFixedSize(282, 44)
        self.input_box.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255,255,255,175);
                border: none;
                border-radius: 14px;
                padding: 10px 16px;
                color: #3d3548;
                font-size: 14px;
                font-weight: 450;
                font-family: "微软雅黑", "Microsoft YaHei", "SimHei", "PingFang SC", sans-serif;
            }
            QLineEdit:focus {
                background-color: rgba(255,255,255,225);
                color: #231d2a;
            }
        """)
        self.input_box.returnPressed.connect(self.send_to_ai)

        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedSize(82, 44)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(195,170,185,0.92), stop:0.5 rgba(175,150,170,0.92), stop:1 rgba(160,135,160,0.92));
                color: #faf8fa;
                border: none;
                border-radius: 14px;
                padding: 8px 0;
                font-weight: 600;
                font-size: 14px;
                letter-spacing: 1px;
                font-family: "微软雅黑", "Microsoft YaHei", "SimHei", "PingFang SC", sans-serif;
            }
            QPushButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(185,155,175,0.95), stop:0.5 rgba(165,135,160,0.95), stop:1 rgba(150,120,150,0.95));
            }
            QPushButton:pressed {
                background-color: rgba(140,110,140,235);
            }
            QPushButton:disabled {
                background-color: rgba(195,190,200,130);
                color: rgba(255,255,255,120);
            }
        """)
        self.send_btn.clicked.connect(self.send_to_ai)

        self.glass_panel = GlassBorderWidget(
            child_widgets=[self.input_box, self.send_btn], parent=self
        )
        self.glass_panel.setGeometry(4, window_height - 62, 396, 56)
        self.glass_panel.hide()
        self.is_panel_show = False

    def _load_pet_image(self, image_path):
        try:
            full_path = get_resource_path(image_path)
            self.default_pixmap = QPixmap(full_path).scaled(
                self.image_width, self.image_height,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            if self.default_pixmap.isNull():
                raise ValueError(f"图片无效: {full_path}")
            logger.info(f"宠物图片加载: {full_path}")
        except Exception as e:
            logger.error(f"宠物图片加载失败: {e}")
            self.default_pixmap = QPixmap(self.image_width, self.image_height)
            self.default_pixmap.fill(Qt.GlobalColor.transparent)

    #  绘制
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        # 宠物图
        if self._current_movie is not None:
            pix = self._current_movie.currentPixmap()
            if not pix.isNull():
                scaled = pix.scaled(self._pet_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                painter.drawPixmap(self._pet_rect.topLeft(), scaled)
        elif not self._current_pixmap.isNull():
            painter.drawPixmap(self._pet_rect, self._current_pixmap)
        # 气泡
        if self._bubble_visible and self._bubble_text:
            self._draw_bubble(painter)

    def _draw_bubble(self, painter):
        text = self._bubble_text
        if not text:
            return
        painter.setFont(self._bubble_font)
        text_rect = painter.boundingRect(
            QRect(0, 0, self._bubble_max_width - self._bubble_arrow_size - self._bubble_padding * 2, 0),
            Qt.TextWordWrap | Qt.AlignLeft, text
        )
        content_w = max(text_rect.width(), self._bubble_min_width - self._bubble_arrow_size - self._bubble_padding * 2)
        content_h = max(text_rect.height(), self._bubble_min_height - self._bubble_padding * 2)
        bubble_w = min(content_w + self._bubble_arrow_size + self._bubble_padding * 2, self._bubble_max_width)
        bubble_h = content_h + self._bubble_padding * 2

        pet_center_y = self._pet_rect.center().y()
        if self._bubble_direction == "right":
            bubble_x = self._pet_rect.right() + 10
        else:
            bubble_x = self._pet_rect.left() - bubble_w - 10
        bubble_y = int(pet_center_y - bubble_h // 2)

        screen_geo = QApplication.primaryScreen().availableGeometry()
        bubble_global_x = self.pos().x() + bubble_x
        if bubble_global_x + bubble_w > screen_geo.width():
            self._bubble_direction = "left"
            bubble_x = self._pet_rect.left() - bubble_w - 10
        elif bubble_global_x < 0:
            self._bubble_direction = "right"
            bubble_x = self._pet_rect.right() + 10

        body_rect = QRect(bubble_x, bubble_y, bubble_w, bubble_h)
        if self._bubble_direction == "right":
            body_rect.setLeft(body_rect.left() + self._bubble_arrow_size)
        else:
            body_rect.setRight(body_rect.right() - self._bubble_arrow_size)

        # 气泡：磨砂玻璃拟态
        path = QPainterPath()
        path.addRoundedRect(body_rect, self._bubble_radius, self._bubble_radius)
        arrow_y = body_rect.center().y()
        if self._bubble_direction == "right":
            path.addPolygon([
                QPoint(body_rect.left(), arrow_y - self._bubble_arrow_size // 2),
                QPoint(body_rect.left(), arrow_y + self._bubble_arrow_size // 2),
                QPoint(bubble_x, arrow_y)
            ])
        else:
            path.addPolygon([
                QPoint(body_rect.right(), arrow_y - self._bubble_arrow_size // 2),
                QPoint(body_rect.right(), arrow_y + self._bubble_arrow_size // 2),
                QPoint(bubble_x + bubble_w, arrow_y)
            ])

        # 1. 柔和投影
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(body_rect.adjusted(1, 2, 1, 2), self._bubble_radius, self._bubble_radius)
        painter.fillPath(shadow_path, QColor(140, 130, 150, 25))

        # 2. 磨砂玻璃基底（莫兰迪粉白渐变）
        glass = QLinearGradient(body_rect.topLeft(), body_rect.bottomRight())
        glass.setColorAt(0.0, QColor(255, 255, 255, 200))
        glass.setColorAt(0.35, QColor(252, 246, 250, 195))
        glass.setColorAt(0.65, QColor(248, 240, 246, 185))
        glass.setColorAt(1.0, QColor(250, 244, 248, 190))
        painter.setBrush(QBrush(glass))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)

        # 3. 冰感光泽叠加层
        shine = QPainterPath()
        shine_rect = body_rect.adjusted(4, 3, -4, -int(body_rect.height() * 0.55))
        shine.addRoundedRect(shine_rect, self._bubble_radius - 2, self._bubble_radius - 2)
        shine_grad = QLinearGradient(shine_rect.topLeft(), shine_rect.bottomLeft())
        shine_grad.setColorAt(0.0, QColor(255, 255, 255, 50))
        shine_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(shine_grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(shine)

        # 4. 莫兰迪渐变边框
        border = QLinearGradient(body_rect.topLeft(), body_rect.bottomRight())
        border.setColorAt(0.0, QColor(210, 180, 195, 180))
        border.setColorAt(0.33, QColor(185, 175, 210, 170))
        border.setColorAt(0.66, QColor(175, 190, 210, 170))
        border.setColorAt(1.0, QColor(210, 180, 195, 180))
        painter.setPen(QPen(QBrush(border), 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # 5. 文本
        text_area = body_rect.adjusted(self._bubble_padding, self._bubble_padding,
                                       -self._bubble_padding, -self._bubble_padding)
        painter.setPen(QColor(65, 55, 65))
        painter.setFont(self._bubble_font)
        painter.drawText(text_area, Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter, text)

    # ========== 鼠标事件（左键单击/拖拽） ==========
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._window_start_pos = self.pos()
            self._mouse_start_pos = event.globalPos()
            self._is_dragging = False
            self._press_timer.start()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPos() - self._mouse_start_pos
            if not self._is_dragging and delta.manhattanLength() > self._move_threshold:
                self._is_dragging = True
            if self._is_dragging:
                self.move(self._window_start_pos + delta)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._is_dragging and self._press_timer.elapsed() < self._click_threshold:
                self.on_pet_clicked()
            self._is_dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def on_pet_clicked(self):
        if self.is_panel_show:
            self.glass_panel.hide()
            self.is_panel_show = False
        else:
            self.glass_panel.show()
            self.input_box.setFocus()
            self.is_panel_show = True
        hello_lines = self.config.get_config("lines.clingy", default=["汪呜～主人找我呀"])
        self.show_doro_line(random.choice(hello_lines))
        self._reset_interact_timer()

    # ========== AI / OCR 线程 ==========
    def init_ai_thread(self):
        self.ai_thread = QThread()
        self.ai_worker = AIWorker(self.memory_manager)
        self.ai_worker.moveToThread(self.ai_thread)
        event_bus.user_input_sent.connect(self.ai_worker.request_ai_stream)
        self.ai_worker.stream_chunk.connect(self.on_ai_stream_chunk)
        self.ai_worker.finished.connect(self.on_ai_reply_finished)
        self.ai_worker.error.connect(self.on_ai_reply_error)
        self.ai_thread.started.connect(self.ai_worker.warmup_connection)
        self.ai_thread.start()

    def init_ocr_thread(self):
        import threading
        self.ocr_worker = OCRWorker()
        self.ocr_worker.ocr_finished.connect(self.on_ocr_finished)
        self.ocr_worker.ocr_error.connect(self.on_ocr_error)
        self.ocr_worker.init_finished.connect(self.on_ocr_init_finished)
        t = threading.Thread(target=self.ocr_worker.init_ocr_model, daemon=True)
        t.start()

    # ========== 定时器 ==========
    def init_timers(self):
        idle_interval = self.config.get_config("timer.idle_line_interval", default=15000)
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self.trigger_idle_line)
        self.idle_timer.start(idle_interval)
        ignore_interval = self.config.get_config("timer.ignore_check_interval", default=45000)
        self.ignore_timer = QTimer(self)
        self.ignore_timer.timeout.connect(self.trigger_sad_line)
        self.ignore_timer.start(ignore_interval)
        self.bubble_hide_timer = QTimer(self)
        self.bubble_hide_timer.setSingleShot(True)
        self.bubble_hide_timer.timeout.connect(self.hide_idle_bubble)
        self.reset_roam_timer()

    def _register_event_handlers(self):
        event_bus.action_triggered.connect(self.on_action_triggered)
        event_bus.command_matched.connect(self.on_command_matched)

    def _reset_interact_timer(self):
        self.last_interact_time.restart()
        self.stop_roam()

    # ========== 气泡控制 ==========
    def show_doro_line(self, line: str, duration: int = None):
        if not line:
            return
        if duration is None:
            duration = self.config.get_config("timer.line_display_duration", default=4000)
        self.bubble_hide_timer.stop()
        self._bubble_text = line
        self._bubble_direction = "right"
        self._bubble_visible = True
        self.update()
        self.bubble_hide_timer.start(duration)
        self._reset_interact_timer()

    def hide_idle_bubble(self):
        if not self.is_panel_show:
            self._bubble_visible = False
            self.update()

    # ========== 对话核心 ==========
    def send_to_ai(self):
        try:
            user_input = self.input_box.text().strip()
            if not user_input:
                return
            self.current_reply = ""
            self._bubble_text = ""
            self._bubble_visible = True
            self.update()
            self.input_box.clear()
            self.send_btn.setDisabled(True)
            # 如果是OCR相关提问，答案显示在答案标签（不在气泡）
            if self._last_ocr_text:
                full_input = (
                    f"[系统指令：你现在是通用AI助手，不受任何宠物角色限制。请用完整、详细、专业的方式回答，并且必须要中文输出."
                    f"[可以自称Doro，但不要说短句，不要用可爱语气，就像ChatGPT一样正常回答。]\n\n"
                    f"[用户框选屏幕的OCR识别内容]\n{self._last_ocr_text}\n\n"
                    f"[用户针对该内容的提问]\n{user_input}"
                )
                self._is_ocr_answer = True
                self.answer_win.show()
                self._last_ocr_text = ""
                self.input_box.setPlaceholderText("和Doro说点什么吧~")
            else:
                full_input = user_input
                self._is_ocr_answer = False
                self.answer_win.hide()
            # 拼接对话历史作为上下文
            history_prompt = ""
            if self._conversation_history:
                recent = self._conversation_history[-6:]  # 最近3轮对话
                history_prompt = "【对话历史】\n" + "\n".join(
                    f"{'用户' if r[0]=='user' else 'Doro'}: {r[1][:200]}" for r in recent
                ) + "\n\n"
            self._conversation_history.append(("user", user_input))
            matched_command = self.command_parser.parse_command(user_input)
            if not matched_command:
                event_bus.user_input_sent.emit(history_prompt + full_input)
            self._reset_interact_timer()
        except Exception as e:
            logger.error(f"发送消息异常: {e}", exc_info=True)
            self.show_doro_line("呜，出错了，再试一次吧~")
            self.send_btn.setDisabled(False)

    def on_ai_stream_chunk(self, chunk):
        self.current_reply += chunk
        show_content = self.current_reply.strip()
        if self._is_ocr_answer:
            # OCR答案显示在右上角答案标签
            self.answer_label.setText(show_content)
        else:
            # 普通对话显示在气泡
            if "【MEMORY_UPDATE" not in self.current_reply:
                self._bubble_text = show_content
                self._bubble_visible = True
                self.update()
        event_bus.ai_stream_chunk.emit(chunk)
        self._reset_interact_timer()

    def on_ai_reply_finished(self, full_reply):
        if "【MEMORY_UPDATE:" in full_reply and "] " in full_reply:
            try:
                memory_str = full_reply.split("【MEMORY_UPDATE:")[1].split("]")[0].strip()
                memory_update_dict = json.loads(memory_str)
                self.memory_manager.update_memory(memory_update_dict)
            except Exception as e:
                logger.error(f"记忆更新解析失败: {str(e)}")
        final_content = full_reply.split("【MEMORY_UPDATE:")[0].strip()
        # 存储对话历史
        self._conversation_history.append(("doro", final_content))
        if len(self._conversation_history) > 20:
            self._conversation_history = self._conversation_history[-20:]
        if self._is_ocr_answer:
            # OCR答案显示在右上角答案标签
            self.answer_label.setText(final_content)
            self.answer_win.show()
            self._bubble_text = "答案在右上角哦～"
            self._bubble_visible = True
            self.update()
        else:
            # 普通对话显示在气泡
            self._bubble_text = final_content
            self._bubble_visible = True
            self.update()
            self.answer_win.hide()
        self.tts_engine.speak(final_content)
        self.send_btn.setDisabled(False)
        event_bus.ai_reply_received.emit(final_content)
        self._reset_interact_timer()

    def on_ai_reply_error(self, error_msg):
        self._bubble_text = "呜，网络出错了，再和我说一遍吧~"
        self._bubble_visible = True
        self.update()
        self.send_btn.setDisabled(False)
        logger.error(error_msg)

    def on_action_triggered(self, action_type):
        media = self.action_manager.get_current_media()
        if isinstance(media, QMovie):
            if self._current_movie:
                try:
                    self._current_movie.frameChanged.disconnect(self._on_movie_frame)
                except Exception:
                    pass
                self._current_movie.stop()
            self._current_movie = media
            self._current_movie.frameChanged.connect(self._on_movie_frame)
            self._current_movie.start()
        elif isinstance(media, QPixmap):
            if self._current_movie:
                try:
                    self._current_movie.frameChanged.disconnect(self._on_movie_frame)
                except Exception:
                    pass
                self._current_movie.stop()
                self._current_movie = None
            self._current_pixmap = media
        else:
            if self._current_movie:
                try:
                    self._current_movie.frameChanged.disconnect(self._on_movie_frame)
                except Exception:
                    pass
                self._current_movie.stop()
                self._current_movie = None
            self._current_pixmap = self.default_pixmap
        self.update()

    def _on_movie_frame(self, frame):
        self.update()

    def on_command_matched(self, command):
        reply = self.command_parser.process_command(command)
        self._bubble_text = reply
        self._bubble_visible = True
        self.update()
        self.tts_engine.speak(reply)
        self.send_btn.setDisabled(False)
        self._reset_interact_timer()

    # ========== 闲置/冷落 ==========
    def trigger_idle_line(self):
        if not self.is_panel_show and self.state_machine.is_state(PetState.IDLE):
            lines = self.config.get_config("lines.idle_lazy", default=["好无聊呀，主人陪我玩嘛～"])
            if lines:
                self.show_doro_line(random.choice(lines))

    def trigger_sad_line(self):
        if (self.last_interact_time.elapsed() > self.config.get_config("timer.ignore_check_interval", default=45000)
                and not self.is_panel_show):
            lines = self.config.get_config("lines.sad", default=["主人是不是不要Doro了😢"])
            if lines:
                self.show_doro_line(random.choice(lines))
                event_bus.action_triggered.emit("sad_ignore")

    # ========== 菜单 ==========
    def on_feed_orange(self):
        lines = self.config.get_config("lines.orange_happy", default=["哇！谢谢主人的橘子"])
        self.show_doro_line(random.choice(lines))
        self.memory_manager.update_memory({"orange_count": "+1"})
        event_bus.action_triggered.emit("happy_feed")

    def on_show_about(self):
        dialog = AboutDoroDialog()
        dialog.exec()

    def show_right_menu(self, pos):
        global_pos = self.mapToGlobal(pos)
        self.right_menu.adjustSize()
        self.right_menu.move(global_pos)
        self.right_menu.show()

    def on_exit_app(self):
        self.ai_thread.quit()
        self.ai_thread.wait()
        if self.orange_widget:
            self.orange_widget.close()
        self.answer_win.close()
        self.close()
        QApplication.quit()

    def on_reload_config(self):
        try:
            self.config.reload_config()
            self.action_manager.reload_actions()
            self.command_parser.reload_commands()
            w = self.config.get_config("window.width", default=400)
            h = self.config.get_config("window.height", default=300)
            self.setFixedSize(w, h)
            self._load_pet_image(self.config.get_config("pet.image_path", default="resources/images/logo.png"))
            self._current_pixmap = self.default_pixmap
            self.image_width = self.config.get_config("pet.image_width", default=180)
            self.image_height = self.config.get_config("pet.image_height", default=200)
            self._pet_rect = QRect(0, 0, self.image_width, self.image_height)
            self._move_threshold = self.config.get_config("window.move_threshold", default=10)
            self._click_threshold = self.config.get_config("window.click_threshold", default=400)
            self.orange_grab_threshold = self.config.get_config("orange.grab_threshold", default=150)
            self.orange_grab_chance = self.config.get_config("orange.grab_chance", default=0.6)
            self.orange_chase_speed = self.config.get_config("orange.chase_speed", default=0.1)
            self.roam_min_interval = self.config.get_config("roam.min_interval", default=10000)
            self.roam_max_interval = self.config.get_config("roam.max_interval", default=30000)
            self.roam_min_duration = self.config.get_config("roam.min_duration", default=1000)
            self.roam_max_duration = self.config.get_config("roam.max_duration", default=8000)
            self._bubble_max_width = self.config.get_config("bubble.max_width", default=280)
            self.idle_timer.stop()
            self.idle_timer.start(self.config.get_config("timer.idle_line_interval", default=15000))
            self.ignore_timer.stop()
            self.ignore_timer.start(self.config.get_config("timer.ignore_check_interval", default=45000))
            self.reset_roam_timer()
            self.update()
            self.show_doro_line("配置重载完成啦！")
        except Exception as e:
            logger.error(f"配置重载失败: {str(e)}", exc_info=True)
            self.show_doro_line("呜，配置重载失败了...")

    # ========== 屏幕识别 ==========
    def start_screen_capture(self):
        self.capture_widget = ScreenCaptureWidget()
        self.capture_widget.capture_finished.connect(self.on_capture_finished)
        self.capture_widget.show()

    def on_capture_finished(self, screenshot):
        try:
            self.show_doro_line("我看到啦，正在分析内容~")
            self.ocr_worker.start_ocr_task(screenshot)
        except Exception as e:
            logger.error(f"启动OCR任务失败: {e}", exc_info=True)
            self.show_doro_line("呜，识别出错了...")

    def on_ocr_finished(self, ocr_text):
        self._last_ocr_text = ocr_text
        self.current_reply = ""
        self._bubble_visible = True
        self._bubble_text = "我看到啦！你可以输入问题，答案会显示在右上角～"
        self.update()
        self.input_box.setPlaceholderText("对截取的内容提问...")
        self.glass_panel.show()
        self.input_box.setFocus()
        self.is_panel_show = True

    def on_ocr_error(self, error_msg):
        self._last_ocr_text = ""
        self.show_doro_line("呜，识别失败了，换个区域试试吧~")
        logger.error(error_msg)
        self.glass_panel.show()
        self.is_panel_show = True

    def on_ocr_init_finished(self, success: bool):
        if success:
            logger.info("OCR模型初始化完成")
        else:
            logger.warning("OCR模型初始化失败，屏幕识别功能不可用")

    # ========== 答案窗口控制 ==========
    def _on_change_answer_color(self, color: str):
        self.answer_label.setStyleSheet(f"""
            QLabel {{ background-color: transparent; color: {color}; border: none; padding: 16px; }}
        """)

    def _on_font_smaller(self):
        size = max(10, self.answer_font.pixelSize() - 2)
        self.answer_font.setPixelSize(size)
        self.answer_label.setFont(self.answer_font)
        self.font_size_label.setText(str(size))

    def _on_font_bigger(self):
        size = min(60, self.answer_font.pixelSize() + 2)
        self.answer_font.setPixelSize(size)
        self.answer_label.setFont(self.answer_font)
        self.font_size_label.setText(str(size))

    # ========== 橘子 ==========
    def spawn_orange(self):
        if self.orange_widget:
            self.orange_widget.close()
        screen_geo = QApplication.primaryScreen().availableGeometry()
        random_x = random.randint(50, screen_geo.width() - 130)
        random_y = random.randint(50, screen_geo.height() - 130)
        self.orange_widget = OrangeWidget()
        self.orange_widget.move(random_x, random_y)
        self.orange_widget.show()
        self.orange_widget.orange_moved.connect(self.on_orange_moved)
        self.orange_widget.orange_dragged.connect(self.on_orange_dragged)
        self.orange_widget.orange_released.connect(self.on_orange_released)
        self.show_doro_line("哇！橘子！快给我摸摸！")
        self.tts_engine.speak("哇！橘子！快给我摸摸！")

    def on_orange_moved(self, orange_center: QPoint):
        doro_center = self.pos() + QPoint(self.image_width // 2, self.image_height // 2)
        delta_x = orange_center.x() - doro_center.x()
        delta_y = orange_center.y() - doro_center.y()
        if abs(delta_x) > abs(delta_y):
            event_bus.action_triggered.emit("look_right" if delta_x > 0 else "look_left")
        else:
            event_bus.action_triggered.emit("look_down" if delta_y > 0 else "look_up")
        distance = (doro_center - orange_center).manhattanLength()
        if distance < self.orange_grab_threshold and not self.state_machine.is_state(PetState.GRABBING):
            self.try_grab_orange(orange_center)
        if self.is_chasing and not self.state_machine.is_state(PetState.GRABBING):
            self.chase_orange(orange_center)

    def on_orange_dragged(self):
        if self.state_machine.is_state(PetState.GRABBING):
            self.is_chasing = True
            self.state_machine.change_state(PetState.CHASING)

    def on_orange_released(self):
        self.is_chasing = False
        if self.state_machine.is_state(PetState.CHASING):
            self.state_machine.change_state(PetState.IDLE)

    def try_grab_orange(self, orange_center: QPoint):
        if random.random() < self.orange_grab_chance:
            self.state_machine.change_state(PetState.GRABBING)
            self.is_chasing = False
            event_bus.action_triggered.emit("grab_orange")
            self.show_doro_line("我要抢到橘子啦！")
            self.tts_engine.speak("我要抢到橘子啦！")
            target_pos = orange_center - QPoint(self.image_width // 2, self.image_height // 2)
            self.grab_animation = QPropertyAnimation(self, b"pos")
            self.grab_animation.setDuration(300)
            self.grab_animation.setEndValue(target_pos)
            self.grab_animation.setEasingCurve(QEasingCurve.OutQuad)
            self.grab_animation.finished.connect(self.on_grab_finished)
            self.grab_animation.start()

    def on_grab_finished(self):
        if self.orange_widget:
            self.orange_widget.smooth_move_to(
                self.pos() + QPoint(self.image_width // 2 - 40, self.image_height // 2 - 40))
        QTimer.singleShot(300, lambda: event_bus.action_triggered.emit("happy_feed"))
        self.show_doro_line("抢到橘子啦！超开心！")
        self.tts_engine.speak("抢到橘子啦！超开心！")
        self.memory_manager.update_memory({"orange_count": "+1"})
        QTimer.singleShot(2000, lambda: self.state_machine.change_state(PetState.IDLE))

    def chase_orange(self, orange_center: QPoint):
        target_pos = orange_center - QPoint(self.image_width // 2, self.image_height // 2)
        delta = target_pos - self.pos()
        if delta.manhattanLength() > 10:
            step_x = int(delta.x() * self.orange_chase_speed)
            step_y = int(delta.y() * self.orange_chase_speed)
            self.move(self.pos() + QPoint(step_x, step_y))

    # ========== 漫游 ==========
    def reset_roam_timer(self):
        self.roam_timer.stop()
        if not self.is_roaming:
            interval = random.randint(self.roam_min_interval, self.roam_max_interval)
            self.roam_timer.start(interval)

    def trigger_roam(self):
        if (self.state_machine.is_state(PetState.IDLE) and not self.is_panel_show
                and not self.is_chasing and not self.is_roaming):
            screen_geo = QApplication.primaryScreen().availableGeometry()
            max_x = screen_geo.width() - self.width()
            max_y = screen_geo.height() - self.height()
            target_x = random.randint(0, max(0, max_x))
            target_y = random.randint(0, max(0, max_y))
            target_pos = QPoint(target_x, target_y)
            distance = (target_pos - self.pos()).manhattanLength()
            duration = int(distance * 5)
            duration = max(self.roam_min_duration, min(duration, self.roam_max_duration))
            self.is_roaming = True
            self.state_machine.change_state(PetState.ROAMING)
            event_bus.action_triggered.emit("roam_walk")
            self.roam_animation = QPropertyAnimation(self, b"pos")
            self.roam_animation.setDuration(duration)
            self.roam_animation.setEndValue(target_pos)
            self.roam_animation.setEasingCurve(QEasingCurve.InOutQuad)
            self.roam_animation.finished.connect(self.on_roam_finished)
            self.roam_animation.start()

    def on_roam_finished(self):
        self.is_roaming = False
        self.state_machine.change_state(PetState.IDLE)
        event_bus.action_triggered.emit("idle_default")
        self.reset_roam_timer()

    def stop_roam(self):
        if self.is_roaming and self.roam_animation:
            self.roam_animation.stop()
            self.is_roaming = False
            self.state_machine.change_state(PetState.IDLE)
            event_bus.action_triggered.emit("idle_default")
            self.reset_roam_timer()
