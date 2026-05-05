import random, json, sys
from utils.config_loader import ConfigLoader
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtGui import QPixmap, QMovie, Qt, QPainter
from PySide6.QtCore import QPoint, QElapsedTimer, QThread, QTimer, QPropertyAnimation, QEasingCurve, QRect
from utils.path_utils import get_resource_path
from utils.logger import logger
from ui.menu_widget import PetMenu
from ui.about_dialog import AboutDoroDialog
from ui.orange_widget import OrangeWidget
from ui.screen_capture import ScreenCaptureWidget
from ui.answer_overlay import AnswerOverlay
from ui.chat_panel import ChatPanel
from ui.bubble_renderer import BubbleRenderer
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
        self.char_config = ConfigLoader(config_path="config/character.yaml")

        self._mouse_start_pos = QPoint(); self._window_start_pos = QPoint()
        self._is_dragging = False
        self._move_threshold = self.config.get_config("window.move_threshold", default=10)
        self._click_threshold = self.config.get_config("window.click_threshold", default=400)
        self._press_timer = QElapsedTimer()
        self.last_interact_time = QElapsedTimer(); self.last_interact_time.start()
        self.current_reply = ""
        self._last_ocr_text = ""
        self._conversation_history = []
        self._is_ocr_answer = False

        self.memory_manager = MemoryManager()
        self.state_machine = PetStateMachine()
        self.action_manager = ActionManager(self.state_machine)
        self.command_parser = CommandParser(self.memory_manager)
        self.tts_engine = TTSEngine(self.config.get_config)

        self.orange_widget = None
        self.orange_grab_threshold = self.config.get_config("orange.grab_threshold", default=150)
        self.orange_grab_chance = self.config.get_config("orange.grab_chance", default=0.6)
        self.orange_chase_speed = self.config.get_config("orange.chase_speed", default=0.1)
        self.is_chasing = False

        self.roam_timer = QTimer(self); self.roam_timer.timeout.connect(self.trigger_roam)
        self.roam_min_interval = self.config.get_config("roam.min_interval", default=10000)
        self.roam_max_interval = self.config.get_config("roam.max_interval", default=30000)
        self.roam_min_duration = self.config.get_config("roam.min_duration", default=1000)
        self.roam_max_duration = self.config.get_config("roam.max_duration", default=8000)
        self.roam_animation = None; self.is_roaming = False

        self.bubble = BubbleRenderer(self.config.get_config)
        self.answer_overlay = AnswerOverlay()
        self.chat_panel = ChatPanel(self)
        self.chat_panel.message_sent.connect(self._on_user_message)

        # OCR 语音逐句播放状态
        self._ocr_sentences = []
        self._ocr_speak_idx = 0
        self._ocr_speaking = False
        self._ocr_paused = False
        self.answer_overlay.set_play_callback(self._ocr_play)
        self.answer_overlay.set_pause_callback(self._ocr_pause)
        self.answer_overlay.set_stop_callback(self._ocr_stop)
        self.tts_engine.tts_finished.connect(self._on_ocr_sentence_done)

        self.initUI()
        self.init_ai_thread()
        self.init_ocr_thread()
        self.init_timers()
        self._register_event_handlers()
        self.show_doro_line("汪呜～人，你好！我是Doro～")

    # ── Windows 鼠标穿透修复 ──
    def nativeEvent(self, eventType, message):
        if sys.platform != "win32":
            return super().nativeEvent(eventType, message)
        try:
            import ctypes; from PySide6.QtCore import QByteArray
            if eventType != QByteArray(b"windows_generic_MSG"):
                return super().nativeEvent(eventType, message)
            class MSG(ctypes.Structure):
                _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                            ("wParam", ctypes.c_ulonglong), ("lParam", ctypes.c_longlong),
                            ("time", ctypes.c_uint), ("pt_x", ctypes.c_long), ("pt_y", ctypes.c_long)]
            msg = ctypes.cast(message, ctypes.POINTER(MSG)).contents
            if msg.message == 0x0084: return True, 1
        except Exception: pass
        return super().nativeEvent(eventType, message)

    # ── UI 初始化 ──
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

        self.tts_enabled = self.config.get_config("tts.enabled", default=True)
        self.tts_backend = self.config.get_config("tts.backend", default="gpt_sovits")
        self.right_menu = PetMenu()
        self.right_menu.set_tts_enabled(self.tts_enabled)
        self.right_menu.set_backend(self.tts_backend)
        self.right_menu.feed_orange.connect(self.on_feed_orange)
        self.right_menu.show_about.connect(self.on_show_about)
        self.right_menu.exit_app.connect(self.on_exit_app)
        self.right_menu.reload_config.connect(self.on_reload_config)
        self.right_menu.screen_capture.connect(self.start_screen_capture)
        self.right_menu.spawn_orange.connect(self.spawn_orange)
        self.right_menu.toggle_tts.connect(self.on_toggle_tts)
        self.right_menu.toggle_backend.connect(self.on_toggle_backend)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_right_menu)

        image_path = self.config.get_config("pet.image_path", default="resources/images/logo.png")
        self.image_width = self.config.get_config("pet.image_width", default=180)
        self.image_height = self.config.get_config("pet.image_height", default=200)
        self._load_pet_image(image_path)
        self._current_pixmap = self.default_pixmap
        self._current_movie = None
        self._pet_rect = QRect(0, 0, self.image_width, self.image_height)

        screen_geo = QApplication.primaryScreen().availableGeometry()
        init_x = screen_geo.width() - window_width - 50
        init_y = screen_geo.height() - window_height - 100
        self.move(max(0, init_x), max(0, init_y))
        self.chat_panel.init_geometry(window_height)

    def _load_pet_image(self, image_path):
        try:
            full_path = get_resource_path(image_path)
            self.default_pixmap = QPixmap(full_path).scaled(
                self.image_width, self.image_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if self.default_pixmap.isNull(): raise ValueError(f"图片无效: {full_path}")
            logger.info(f"宠物图片加载: {full_path}")
        except Exception as e:
            logger.error(f"宠物图片加载失败: {e}")
            self.default_pixmap = QPixmap(self.image_width, self.image_height)
            self.default_pixmap.fill(Qt.GlobalColor.transparent)

    # ── 绘制 ──
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
        # 气泡（委托给 BubbleRenderer）
        self.bubble.draw(painter, self._pet_rect, self.pos())

    # ── 鼠标事件 ──
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._window_start_pos = self.pos(); self._mouse_start_pos = event.globalPos()
            self._is_dragging = False; self._press_timer.start(); event.accept()
        else: super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPos() - self._mouse_start_pos
            if not self._is_dragging and delta.manhattanLength() > self._move_threshold:
                self._is_dragging = True
            if self._is_dragging: self.move(self._window_start_pos + delta)
            event.accept()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._is_dragging and self._press_timer.elapsed() < self._click_threshold:
                self.on_pet_clicked()
            self._is_dragging = False; event.accept()
        else: super().mouseReleaseEvent(event)

    def on_pet_clicked(self):
        self.chat_panel.toggle()
        hello_lines = self.char_config.get_config("lines.clingy", default=["汪呜～人找我呀"])
        self.show_doro_line(random.choice(hello_lines))
        self._reset_interact_timer()

    # ── 线程 ──
    def init_ai_thread(self):
        self.ai_thread = QThread(); self.ai_worker = AIWorker(self.memory_manager)
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
        t = threading.Thread(target=self.ocr_worker.init_ocr_model, daemon=True); t.start()

    # ── 定时器 ──
    def init_timers(self):
        self.idle_timer = QTimer(self); self.idle_timer.timeout.connect(self.trigger_idle_line)
        self.idle_timer.start(self.config.get_config("timer.idle_line_interval", default=15000))
        self.ignore_timer = QTimer(self); self.ignore_timer.timeout.connect(self.trigger_sad_line)
        self.ignore_timer.start(self.config.get_config("timer.ignore_check_interval", default=45000))
        self.bubble_hide_timer = QTimer(self); self.bubble_hide_timer.setSingleShot(True)
        self.bubble_hide_timer.timeout.connect(self.hide_idle_bubble)
        self.reset_roam_timer()

    def _register_event_handlers(self):
        event_bus.action_triggered.connect(self.on_action_triggered)
        event_bus.command_matched.connect(self.on_command_matched)

    def _reset_interact_timer(self):
        self.last_interact_time.restart(); self.stop_roam()

    # ── 气泡控制 ──
    def show_doro_line(self, line: str, duration: int = None):
        if not line: return
        if duration is None: duration = self.config.get_config("timer.line_display_duration", default=4000)
        self.bubble_hide_timer.stop()
        self.bubble.set_text(line); self.bubble.direction = "right"; self.bubble.show()
        self.update(); self.bubble_hide_timer.start(duration); self._reset_interact_timer()

    def hide_idle_bubble(self):
        if not self.chat_panel.is_visible:
            self.bubble.hide(); self.update()

    # ── 对话核心 ──
    def _on_user_message(self, user_input):
        try:
            self.current_reply = ""; self.bubble.set_text(""); self.bubble.show(); self.update()
            if self._last_ocr_text:
                full_input = (
                    f"[系统指令：你现在是通用AI助手，不受任何宠物角色限制。请用完整、详细、专业的方式回答，并且必须要中文输出。"
                    f"可以自称Doro，但不要说短句，不要用可爱语气，就像ChatGPT一样正常回答。]\n\n"
                    f"[用户框选屏幕的OCR识别内容]\n{self._last_ocr_text}\n\n"
                    f"[用户针对该内容的提问]\n{user_input}"
                )
                self._is_ocr_answer = True; self.answer_overlay.show()
                self._last_ocr_text = ""; self.chat_panel.set_placeholder("和Doro说点什么吧~")
            else:
                full_input = user_input; self._is_ocr_answer = False; self.answer_overlay.hide()
            history_prompt = ""
            if self._conversation_history:
                recent = self._conversation_history[-6:]
                history_prompt = "【对话历史】\n" + "\n".join(
                    f"{'用户' if r[0]=='user' else 'Doro'}: {r[1][:200]}" for r in recent) + "\n\n"
            self._conversation_history.append(("user", user_input))
            matched_command = self.command_parser.parse_command(user_input)
            if not matched_command: event_bus.user_input_sent.emit(history_prompt + full_input)
            self._reset_interact_timer()
        except Exception as e:
            logger.error(f"发送消息异常: {e}", exc_info=True)
            self.show_doro_line("呜，出错了，再试一次吧~"); self.chat_panel.set_send_enabled(True)

    def on_ai_stream_chunk(self, chunk):
        self.current_reply += chunk
        show_content = self.current_reply.strip()
        if self._is_ocr_answer: self.answer_overlay.setText(show_content)
        elif "【MEMORY_UPDATE" not in self.current_reply:
            self.bubble.set_text(show_content); self.bubble.show(); self.update()
        event_bus.ai_stream_chunk.emit(chunk); self._reset_interact_timer()

    def on_ai_reply_finished(self, full_reply):
        if "【MEMORY_UPDATE:" in full_reply and "] " in full_reply:
            try:
                ms = full_reply.split("【MEMORY_UPDATE:")[1].split("]")[0].strip()
                self.memory_manager.update_memory(json.loads(ms))
            except Exception as e: logger.error(f"记忆更新解析失败: {e}")
        final = full_reply.split("【MEMORY_UPDATE:")[0].strip()
        self._conversation_history.append(("doro", final))
        if len(self._conversation_history) > 20: self._conversation_history = self._conversation_history[-20:]
        if self._is_ocr_answer:
            self.answer_overlay.setText(final); self.answer_overlay.show()
            self.bubble.set_text("答案在右上角哦～"); self.bubble.show(); self.update()
            self._ocr_sentences = self._ocr_split_sentences(final)
            self._ocr_speaking = True
            self._ocr_speak_idx = 0
            self._ocr_paused = False
            self.answer_overlay.reset_audio_controls()
            self._ocr_speak_next()
        else:
            self.bubble.set_text(final); self.bubble.show(); self.update(); self.answer_overlay.hide()
            self._speak(final)
        self.chat_panel.set_send_enabled(True)
        event_bus.ai_reply_received.emit(final); self._reset_interact_timer()

    def on_ai_reply_error(self, error_msg):
        self.bubble.set_text("呜，网络出错了，再和我说一遍吧~"); self.bubble.show(); self.update()
        self.chat_panel.set_send_enabled(True); logger.error(error_msg)

    def on_action_triggered(self, action_type):
        media = self.action_manager.get_current_media()
        if self._current_movie:
            try: self._current_movie.frameChanged.disconnect(self._on_movie_frame)
            except Exception: pass
            self._current_movie.stop(); self._current_movie = None
        if isinstance(media, QMovie):
            self._current_movie = media
            self._current_movie.frameChanged.connect(self._on_movie_frame); self._current_movie.start()
        elif isinstance(media, QPixmap): self._current_pixmap = media
        else: self._current_pixmap = self.default_pixmap
        self.update()

    def _on_movie_frame(self, frame): self.update()

    def on_command_matched(self, command):
        reply = self.command_parser.process_command(command)
        self.bubble.set_text(reply); self.bubble.show(); self.update()
        self._speak(reply); self.chat_panel.set_send_enabled(True); self._reset_interact_timer()

    # ── 闲置/冷落 ──
    def trigger_idle_line(self):
        if not self.chat_panel.is_visible and self.state_machine.is_state(PetState.IDLE):
            lines = self.char_config.get_config("lines.idle_lazy", default=["好无聊呀，人陪我玩嘛～"])
            if lines: self.show_doro_line(random.choice(lines))

    def trigger_sad_line(self):
        if (self.last_interact_time.elapsed() > self.config.get_config("timer.ignore_check_interval", default=45000)
                and not self.chat_panel.is_visible):
            lines = self.char_config.get_config("lines.sad", default=["人是不是不要Doro了😢"])
            if lines: self.show_doro_line(random.choice(lines)); event_bus.action_triggered.emit("sad_ignore")

    # ── 菜单 ──
    def on_feed_orange(self):
        self.show_doro_line(random.choice(self.char_config.get_config("lines.orange_happy", default=["哇！谢谢人的橘子"])))
        self.memory_manager.update_memory({"orange_count": "+1"}); event_bus.action_triggered.emit("happy_feed")

    def on_show_about(self): AboutDoroDialog().exec()

    def on_toggle_tts(self):
        self.tts_enabled = not self.tts_enabled
        self.right_menu.set_tts_enabled(self.tts_enabled)

    def on_toggle_backend(self):
        self.tts_backend = "edge_tts" if self.tts_backend == "gpt_sovits" else "gpt_sovits"
        self.right_menu.set_backend(self.tts_backend)

    # ── OCR 逐句语音播报 ──
    def _ocr_split_sentences(self, text: str):
        import re
        parts = re.split(r'([。！？；\n！!?;])', text)
        sentences = []
        buf = ""
        for p in parts:
            buf += p
            if re.match(r'[。！？；\n！!?;]', p):
                s = buf.strip()
                if s:
                    sentences.append(s)
                buf = ""
        if buf.strip():
            sentences.append(buf.strip())
        return sentences if sentences else [text]

    def _ocr_play(self):
        if self._ocr_paused:
            self._ocr_paused = False
            self._ocr_speak_next()
        else:
            self._ocr_speaking = True
            self._ocr_speak_idx = 0
            self.tts_engine.stop_tts()
            self._ocr_speak_next()

    def _ocr_pause(self):
        self._ocr_paused = True
        self.tts_engine.stop_tts()

    def _ocr_stop(self):
        self._ocr_speaking = False
        self._ocr_paused = False
        self._ocr_speak_idx = 0
        self.tts_engine.stop_tts()

    def _ocr_speak_next(self):
        if not self._ocr_speaking or self._ocr_paused:
            return
        if self._ocr_speak_idx >= len(self._ocr_sentences):
            self._ocr_speaking = False
            self._ocr_speak_idx = 0
            self.answer_overlay.reset_audio_controls()
            return
        sent = self._ocr_sentences[self._ocr_speak_idx]
        self._ocr_speak_idx += 1
        if self.tts_enabled:
            self.tts_engine.speak(sent, backend="edge_tts")

    def _on_ocr_sentence_done(self):
        if self._ocr_speaking and not self._ocr_paused:
            self._ocr_speak_next()

    def _speak(self, text: str, backend: str = None):
        if self.tts_enabled:
            self.tts_engine.speak(text, backend or self.tts_backend)

    def show_right_menu(self, pos):
        self.right_menu.set_tts_enabled(self.tts_enabled)
        self.right_menu.set_backend(self.tts_backend)
        global_pos = self.mapToGlobal(pos); self.right_menu.adjustSize()
        self.right_menu.move(global_pos); self.right_menu.show()

    def on_exit_app(self):
        self.ai_thread.quit(); self.ai_thread.wait()
        if self.orange_widget: self.orange_widget.close()
        self.answer_overlay.close(); self.tts_engine.shutdown()
        self.close(); QApplication.quit()

    def on_reload_config(self):
        try:
            self.config.reload_config(); self.action_manager.reload_actions(); self.command_parser.reload_commands()
            self.setFixedSize(self.config.get_config("window.width", default=400),
                              self.config.get_config("window.height", default=300))
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
            for attr in ['roam_min_interval','roam_max_interval','roam_min_duration','roam_max_duration']:
                setattr(self, attr, self.config.get_config(f"roam.{attr.replace('roam_','')}", default=10000))
            self.bubble.max_width = self.config.get_config("bubble.max_width", default=280)
            self.idle_timer.stop(); self.ignore_timer.stop()
            self.idle_timer.start(self.config.get_config("timer.idle_line_interval", default=15000))
            self.ignore_timer.start(self.config.get_config("timer.ignore_check_interval", default=45000))
            self.reset_roam_timer(); self.update(); self.show_doro_line("配置重载完成啦！")
        except Exception as e:
            logger.error(f"配置重载失败: {e}", exc_info=True); self.show_doro_line("呜，配置重载失败了...")

    # ── 屏幕识别 ──
    def start_screen_capture(self):
        self.capture_widget = ScreenCaptureWidget()
        self.capture_widget.capture_finished.connect(self.on_capture_finished); self.capture_widget.show()

    def on_capture_finished(self, screenshot):
        try: self.show_doro_line("我看到啦，Doro正在分析内容~"); self.ocr_worker.start_ocr_task(screenshot)
        except Exception as e: logger.error(f"启动OCR任务失败: {e}", exc_info=True); self.show_doro_line("呜，识别出错了...")

    def on_ocr_finished(self, ocr_text):
        self._last_ocr_text = ocr_text; self.current_reply = ""; self.bubble.show()
        self.bubble.set_text("Doro看到啦！你可以输入问题，答案会显示在右上角～"); self.update()
        self.chat_panel.set_placeholder("对截取的内容提问..."); self.chat_panel.show()

    def on_ocr_error(self, error_msg):
        self._last_ocr_text = ""; self.show_doro_line("呜，识别失败了，换个区域试试吧~")
        logger.error(error_msg); self.chat_panel.show()

    def on_ocr_init_finished(self, success: bool):
        if success: logger.info("OCR模型初始化完成")
        else: logger.warning("OCR模型初始化失败，屏幕识别功能不可用")

    # ── 橘子 ──
    def spawn_orange(self):
        if self.orange_widget: self.orange_widget.close()
        geo = QApplication.primaryScreen().availableGeometry()
        self.orange_widget = OrangeWidget()
        self.orange_widget.move(random.randint(50, geo.width()-130), random.randint(50, geo.height()-130))
        self.orange_widget.show()
        self.orange_widget.orange_moved.connect(self.on_orange_moved)
        self.orange_widget.orange_dragged.connect(self.on_orange_dragged)
        self.orange_widget.orange_released.connect(self.on_orange_released)
        self.show_doro_line("哇！橘子！快给Doro摸摸！"); self._speak("哇！橘子！快给我摸摸！")

    def on_orange_moved(self, oc):
        dc = self.pos() + QPoint(self.image_width//2, self.image_height//2)
        dx, dy = oc.x()-dc.x(), oc.y()-dc.y()
        event_bus.action_triggered.emit("look_right" if abs(dx)>abs(dy) and dx>0 else
            "look_left" if abs(dx)>abs(dy) else "look_down" if dy>0 else "look_up")
        if (dc-oc).manhattanLength() < self.orange_grab_threshold and not self.state_machine.is_state(PetState.GRABBING):
            self.try_grab_orange(oc)
        if self.is_chasing and not self.state_machine.is_state(PetState.GRABBING): self.chase_orange(oc)

    def on_orange_dragged(self):
        if self.state_machine.is_state(PetState.GRABBING): self.is_chasing = True; self.state_machine.change_state(PetState.CHASING)
    def on_orange_released(self):
        self.is_chasing = False
        if self.state_machine.is_state(PetState.CHASING): self.state_machine.change_state(PetState.IDLE)

    def try_grab_orange(self, oc):
        if random.random() < self.orange_grab_chance:
            self.state_machine.change_state(PetState.GRABBING); self.is_chasing = False
            event_bus.action_triggered.emit("grab_orange"); self.show_doro_line("Doro要抢到橘子啦！")
            self._speak("Doro要抢到橘子啦！"); tp = oc - QPoint(self.image_width//2, self.image_height//2)
            self.grab_animation = QPropertyAnimation(self, b"pos"); self.grab_animation.setDuration(300)
            self.grab_animation.setEndValue(tp); self.grab_animation.setEasingCurve(QEasingCurve.OutQuad)
            self.grab_animation.finished.connect(self.on_grab_finished); self.grab_animation.start()

    def on_grab_finished(self):
        if self.orange_widget: self.orange_widget.smooth_move_to(
            self.pos() + QPoint(self.image_width//2-40, self.image_height//2-40))
        QTimer.singleShot(300, lambda: event_bus.action_triggered.emit("happy_feed"))
        self.show_doro_line("Doro抢到橘子啦！超开心！"); self._speak("抢到橘子啦！超开心！")
        self.memory_manager.update_memory({"orange_count": "+1"})
        QTimer.singleShot(2000, lambda: self.state_machine.change_state(PetState.IDLE))

    def chase_orange(self, oc):
        tp = oc - QPoint(self.image_width//2, self.image_height//2); delta = tp - self.pos()
        if delta.manhattanLength() > 10:
            self.move(self.pos() + QPoint(int(delta.x()*self.orange_chase_speed), int(delta.y()*self.orange_chase_speed)))

    # ── 漫游 ──
    def reset_roam_timer(self):
        self.roam_timer.stop()
        if not self.is_roaming: self.roam_timer.start(random.randint(self.roam_min_interval, self.roam_max_interval))

    def trigger_roam(self):
        if (self.state_machine.is_state(PetState.IDLE) and not self.chat_panel.is_visible
                and not self.is_chasing and not self.is_roaming):
            geo = QApplication.primaryScreen().availableGeometry()
            tp = QPoint(random.randint(0, max(0, geo.width()-self.width())),
                        random.randint(0, max(0, geo.height()-self.height())))
            dist = (tp-self.pos()).manhattanLength(); dur = max(self.roam_min_duration, min(int(dist*5), self.roam_max_duration))
            self.is_roaming = True; self.state_machine.change_state(PetState.ROAMING); event_bus.action_triggered.emit("roam_walk")
            self.roam_animation = QPropertyAnimation(self, b"pos"); self.roam_animation.setDuration(dur)
            self.roam_animation.setEndValue(tp); self.roam_animation.setEasingCurve(QEasingCurve.InOutQuad)
            self.roam_animation.finished.connect(self.on_roam_finished); self.roam_animation.start()

    def on_roam_finished(self):
        self.is_roaming = False; self.state_machine.change_state(PetState.IDLE)
        event_bus.action_triggered.emit("idle_default"); self.reset_roam_timer()

    def stop_roam(self):
        if self.is_roaming and self.roam_animation:
            self.roam_animation.stop(); self.is_roaming = False
            self.state_machine.change_state(PetState.IDLE); event_bus.action_triggered.emit("idle_default")
            self.reset_roam_timer()
