import random
import json
import os
import sys
from utils.config_loader import ConfigLoader
from PySide6.QtWidgets import QLabel, QWidget, QApplication, QLineEdit, QPushButton
from PySide6.QtGui import QPixmap, QMovie, Qt
from PySide6.QtCore import QPoint, QElapsedTimer, QThread, QTimer, QObject
from utils.logger import logger
from utils.path_utils import get_resource_path
from core.event_system import event_bus
from core.pet_state import PetStateMachine
from core.action_manager import ActionManager
from core.command_parser import CommandParser
from ai.ai_worker import AIWorker
from ai.memory_manager import MemoryManager
from ui.bubble_widget import BubbleLabel
from ui.menu_widget import PetMenu
from ui.about_dialog import AboutDoroDialog


class PetMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        # 全局配置单例（最先初始化）
        self.config = ConfigLoader()

        # 初始化核心业务模块
        self.memory_manager = MemoryManager()
        self.state_machine = PetStateMachine()
        self.action_manager = ActionManager(self.state_machine)
        self.command_parser = CommandParser(self.memory_manager)

        # ====================== 拖拽核心参数（手感可直接微调） ======================
        self._is_dragging = False
        self._window_start_pos = QPoint()
        self._mouse_start_pos = QPoint()
        # 移动阈值：2=平衡跟手&防误触，1=极致跟手，3=完全防误触
        self._move_threshold = self.config.get_config("window.move_threshold", 2)
        # 点击阈值：250ms，避免拖拽误判为点击
        self._click_threshold = self.config.get_config("window.click_threshold", 250)
        self._press_timer = QElapsedTimer()

        # 界面状态管理
        self.is_panel_show = False
        self.current_reply = ""
        # 用户互动计时器
        self.last_interact_time = QElapsedTimer()
        self.last_interact_time.start()

        # 按顺序初始化所有模块
        self.initUI()
        self.init_ai_thread()
        self.init_timers()
        self._register_event_handlers()

    def initUI(self):
        # ====================== 1. 窗口基础配置 ======================
        window_width = self.config.get_config("settings.window.width", 400)
        window_height = self.config.get_config("settings.window.height", 400)
        self.setFixedSize(window_width, window_height)

        # 无边框、置顶、全透明基础配置
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setStyleSheet("QWidget {background-color: transparent;}")

        # ====================== 【根治闪烁核心】Windows分层窗口硬件加速 ======================
        if sys.platform == "win64":
            try:
                from PySide6.QtWinExtras import QtWin
                # 开启Windows分层窗口，启用GPU硬件加速渲染，彻底解决透明窗口拖动闪烁
                QtWin.setWindowExtendedStyle(
                    self,
                    QtWin.WS_EX_LAYERED | QtWin.WS_EX_TRANSPARENT
                )
                # 关闭窗口阴影，避免拖动时的重绘开销
                self.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
            except ImportError:
                logger.warning("QtWinExtras模块未找到，跳过Windows硬件加速优化")

        # ====================== 【渲染优化】关闭多余重绘，开启双缓冲防撕裂 ======================
        self.setAttribute(Qt.WA_PaintOnScreen, False)
        self.setUpdatesEnabled(True)

        # 后面的右键菜单、宠物图片、输入框等原有代码，保持不变

        # ====================== 2. 右键菜单 ======================
        self.right_menu = PetMenu(self)
        self.right_menu.feed_orange.connect(self.on_feed_orange)
        self.right_menu.show_about.connect(self.on_show_about)
        self.right_menu.exit_app.connect(self.on_exit_app)
        self.right_menu.reload_config.connect(self.on_reload_config)

        # 绑定右键菜单弹出事件
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_right_menu)

        # ====================== 3. 宠物形象控件 ======================
        self.pet_label = QLabel(self)
        self.pet_label.setStyleSheet("background-color: transparent;")

        # 从配置读取宠物图片参数
        image_path = self.config.get_config("settings.pet.image_path", "resources/images/logo.png")
        self.image_width = self.config.get_config("settings.pet.image_width", 180)
        self.image_height = self.config.get_config("settings.pet.image_height", 200)

        # 加载并设置宠物图片
        self.default_pixmap = QPixmap(get_resource_path(image_path)).scaled(
            self.image_width, self.image_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.pet_label.setPixmap(self.default_pixmap)
        self.pet_label.setGeometry(0, 0, self.image_width, self.image_height)

        # 宠物图片完全透传鼠标事件，不拦截拖拽
        self.pet_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        # ====================== 4. 气泡对话框 ======================
        self.reply_bubble = BubbleLabel(self)
        self.reply_bubble.hide()

        # ====================== 5. 输入框+发送按钮 ======================
        self.input_box = QLineEdit(self)
        self.input_box.setPlaceholderText("和Doro说点什么吧~")
        self.input_box.setFixedSize(280, 40)
        self.input_box.setStyleSheet("""
        QLineEdit {
            background-color: rgba(255, 255, 255, 0.9);
            border: 1px solid rgba(255, 182, 193, 200);
            border-radius: 10px;
            padding: 8px 10px;
            color: #333;
            font-size: 14px;
            font-family: "微软雅黑", "Microsoft YaHei", "SimHei", "黑体", "PingFang SC", sans-serif;
        }
        QLineEdit:focus {
            border: 1px solid rgba(255, 105, 180, 200);
            background-color: rgba(255, 255, 255, 1);
        }
        """)
        # 初始隐藏，默认透传鼠标事件，不拦截拖拽
        self.input_box.hide()
        self.input_box.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.input_box.returnPressed.connect(self.send_to_ai)
        self.input_box.setGeometry(10, window_height - 50, 280, 40)

        # 发送按钮
        self.send_btn = QPushButton("发送", self)
        self.send_btn.setFixedSize(80, 40)
        self.send_btn.setStyleSheet("""
        QPushButton {
            background-color: rgba(255, 182, 193, 0.9);
            color: white;
            border-radius: 10px;
            padding: 6px 0;
            font-weight: bold;
            font-size: 14px;
            font-family: "微软雅黑", "Microsoft YaHei", "SimHei", "黑体", "PingFang SC", sans-serif;
        }
        QPushButton:hover {
            background-color: rgba(255, 105, 180, 220);
        }
        QPushButton:pressed {
            background-color: rgba(255, 20, 147, 220);
        }
        QPushButton:disabled {
            background-color: rgba(200, 200, 200, 150);
        }
        """)
        # 初始隐藏，默认透传鼠标事件，不拦截拖拽
        self.send_btn.hide()
        self.send_btn.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.send_btn.clicked.connect(self.send_to_ai)
        self.send_btn.setGeometry(300, window_height - 50, 80, 40)

    # ====================== 【无闪烁丝滑拖拽核心】重写鼠标事件 ======================
    def mousePressEvent(self, event):
        """鼠标按下：记录全局起点，零延迟响应"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 记录窗口全局起始位置 + 鼠标全局起始位置，彻底避免坐标漂移
            self._window_start_pos = self.pos()
            self._mouse_start_pos = event.globalPos()
            self._is_dragging = False
            self._press_timer.start()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """鼠标移动：无闪烁窗口移动，和系统窗口完全同步"""
        if event.buttons() & Qt.MouseButton.LeftButton:
            # 计算鼠标全局偏移量
            delta = event.globalPos() - self._mouse_start_pos

            # 超过拖拽阈值，进入拖拽状态
            if not self._is_dragging:
                if delta.manhattanLength() > self._move_threshold:
                    self._is_dragging = True

            # 核心优化：直接移动窗口，不触发多余重绘，快速拖动无闪烁
            if self._is_dragging:
                target_pos = self._window_start_pos + delta
                self.move(target_pos)
                event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放：清晰区分点击和拖拽，无逻辑冲突"""
        if event.button() == Qt.MouseButton.LeftButton:
            # 只有非拖拽状态+按时长小于阈值，才触发点击宠物事件
            if not self._is_dragging and self._press_timer.elapsed() < self._click_threshold:
                self.on_pet_clicked()
            # 重置拖拽状态
            self._is_dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # ====================== 宠物点击交互逻辑 ======================
    def on_pet_clicked(self):
        """点击宠物：切换输入框显隐，同步修改事件透传状态"""
        if self.input_box.isVisible():
            # 隐藏输入框，开启事件透传，不拦截拖拽
            self.input_box.hide()
            self.send_btn.hide()
            self.input_box.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.send_btn.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.is_panel_show = False
        else:
            # 显示输入框，关闭事件透传，正常响应输入
            self.input_box.show()
            self.send_btn.show()
            self.input_box.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.send_btn.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.input_box.setFocus()
            self.is_panel_show = True
            # 点击宠物触发随机打招呼台词
            hello_lines = self.config.get_config("character.lines.hello", [
                "汪呜～主人找我呀😆",
                "怎么啦主人～",
                "Doro在这里！",
                "主人摸我啦🥰"
            ])
            self.show_doro_line(hello_lines)
        self._reset_interact_timer()

    # ====================== AI线程初始化 ======================
    def init_ai_thread(self):
        """初始化AI子线程，避免阻塞UI"""
        self.ai_thread = QThread()
        self.ai_worker = AIWorker(self.memory_manager)
        self.ai_worker.moveToThread(self.ai_thread)

        # 信号绑定
        event_bus.user_input_sent.connect(self.ai_worker.request_ai_stream)
        self.ai_worker.stream_chunk.connect(self.on_ai_stream_chunk)
        self.ai_worker.finished.connect(self.on_ai_reply_finished)
        self.ai_worker.error.connect(self.on_ai_reply_finished)

        # 配置好API后取消注释，开启AI预热
        # self.ai_thread.started.connect(self.ai_worker.warmup_connection)
        self.ai_thread.start()

    # ====================== 定时器初始化 ======================
    def init_timers(self):
        """初始化所有定时器"""
        # 闲置台词定时器
        idle_interval = self.config.get_config("timer.idle_line_interval", 15000)
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self.trigger_idle_line)
        self.idle_timer.start(idle_interval)

        # 用户冷落检测定时器
        ignore_interval = self.config.get_config("timer.ignore_check_interval", 45000)
        self.ignore_timer = QTimer(self)
        self.ignore_timer.timeout.connect(self.trigger_sad_line)
        self.ignore_timer.start(ignore_interval)

        # 气泡自动隐藏定时器
        self.bubble_hide_timer = QTimer(self)
        self.bubble_hide_timer.setSingleShot(True)
        self.bubble_hide_timer.timeout.connect(self.hide_idle_bubble)

    # ====================== 事件总线注册 ======================
    def _register_event_handlers(self):
        """注册全局事件处理器"""
        event_bus.action_triggered.connect(self.on_action_triggered)
        event_bus.command_matched.connect(self.on_command_matched)
        event_bus.user_interacted.connect(self._reset_interact_timer)

    # ====================== 工具类方法 ======================
    def _reset_interact_timer(self):
        """重置用户互动计时器"""
        self.last_interact_time.restart()

    def show_doro_line(self, line_list, duration=None):
        """显示Doro的台词气泡"""
        if duration is None:
            duration = self.config.get_config("timer.line_display_duration", 4000)
        self.bubble_hide_timer.stop()
        line = random.choice(line_list)
        self.reply_bubble.setText(line)
        self.adjust_bubble_position()
        self.reply_bubble.show()
        self.bubble_hide_timer.start(duration)
        self._reset_interact_timer()

    def trigger_idle_line(self):
        """触发闲置状态台词"""
        if not self.is_panel_show and self.send_btn.isEnabled() and self.state_machine.is_state("idle"):
            lines = self.config.get_config("character.lines.idle_lazy", [
                "好无聊呀，主人陪我玩嘛～",
                "Doro要睡着啦...",
                "什么时候主人才会理我呀"
            ])
            if lines:
                self.show_doro_line(lines)

    def trigger_sad_line(self):
        """触发用户冷落的委屈台词"""
        if self.last_interact_time.elapsed() > self.config.get_config("timer.ignore_check_interval",
                                                                      45000) and not self.is_panel_show:
            lines = self.config.get_config("character.lines.sad", [
                "主人是不是不要Doro了🥺",
                "好久没理我了...",
                "Doro好委屈"
            ])
            if lines:
                self.show_doro_line(lines)
                event_bus.action_triggered.emit("sad_ignore")

    def hide_idle_bubble(self):
        """自动隐藏闲置气泡"""
        if not self.is_panel_show and self.send_btn.isEnabled():
            self.reply_bubble.hide()

    def adjust_bubble_position(self):
        """自动调整气泡位置，适配屏幕边界"""
        self.reply_bubble.adjustSize()
        self.reply_bubble.setMinimumSize(
            self.config.get_config("bubble.min_width", 100),
            self.config.get_config("bubble.min_height", 45)
        )
        pet_rect = self.pet_label.geometry()
        pet_center_y = pet_rect.center().y()
        bubble_direction = "right"
        self.reply_bubble.set_direction(bubble_direction)
        bubble_rect = self.reply_bubble.geometry()

        # 计算气泡初始位置（宠物右侧）
        if bubble_direction == "right":
            bubble_x = pet_rect.right() + 10
            bubble_y = pet_center_y - bubble_rect.height() // 2
        else:
            bubble_x = pet_rect.left() - bubble_rect.width() - 10
            bubble_y = pet_center_y - bubble_rect.height() // 2

        # 屏幕边界检测，避免气泡超出屏幕
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        window_global_pos = self.pos()
        bubble_global_x = window_global_pos.x() + bubble_x
        bubble_global_right = bubble_global_x + bubble_rect.width()

        # 超出右边界就显示在宠物左侧
        if bubble_global_right > screen_geometry.width():
            self.reply_bubble.set_direction("left")
            bubble_x = pet_rect.left() - bubble_rect.width() - 10
        # 超出左边界就显示在宠物右侧
        elif bubble_global_x < 0:
            self.reply_bubble.set_direction("right")
            bubble_x = pet_rect.right() + 10

        self.reply_bubble.move(bubble_x, bubble_y)
        self.reply_bubble.raise_()

    # ====================== 对话功能核心方法 ======================
    def send_to_ai(self):
        """发送用户输入到AI，先解析命令再调用AI"""
        user_input = self.input_box.text().strip()
        if not user_input:
            return

        # 初始化回复内容
        self.current_reply = ""
        self.reply_bubble.setText("")
        self.adjust_bubble_position()
        self.reply_bubble.show()

        # 隐藏输入框和按钮，避免重复发送
        self.input_box.hide()
        self.send_btn.hide()
        self.input_box.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.send_btn.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.input_box.clear()
        self.send_btn.setDisabled(True)
        self.is_panel_show = False

        # 先解析自定义命令
        matched_command = self.command_parser.parse_command(user_input)
        if not matched_command:
            # 无匹配命令，发送AI请求
            event_bus.user_input_sent.emit(user_input)
            self._reset_interact_timer()

    def on_ai_stream_chunk(self, chunk):
        """处理AI流式回复，实时更新气泡"""
        self.current_reply += chunk
        # 过滤记忆更新标记，不显示给用户
        if "【MEMORY_UPDATE" in self.current_reply:
            show_content = self.current_reply.split("【MEMORY_UPDATE")[0].strip()
        else:
            show_content = self.current_reply.strip()
        self.reply_bubble.setText(show_content)
        self.adjust_bubble_position()
        event_bus.ai_stream_chunk.emit(chunk)
        self._reset_interact_timer()

    def on_ai_reply_finished(self, full_reply):
        """处理AI完整回复，解析记忆更新"""
        # 解析并执行记忆更新
        if "【MEMORY_UPDATE:" in full_reply and "】" in full_reply:
            try:
                memory_str = full_reply.split("【MEMORY_UPDATE:")[1].split("】")[0].strip()
                memory_update_dict = json.loads(memory_str)
                self.memory_manager.update_memory(memory_update_dict)
            except Exception as e:
                logger.error(f"记忆更新解析失败: {str(e)}")

        # 显示最终回复内容
        final_content = full_reply.split("【MEMORY_UPDATE:")[0].strip()
        self.reply_bubble.setText(final_content)
        self.adjust_bubble_position()
        self.reply_bubble.show()
        # 恢复发送按钮状态
        self.send_btn.setDisabled(False)
        event_bus.ai_reply_received.emit(final_content)
        self._reset_interact_timer()

    # ====================== 事件响应方法 ======================
    def on_action_triggered(self, action_type):
        """动作触发，更新宠物形象/动图"""
        media = self.action_manager.get_current_media()
        if isinstance(media, QMovie):
            self.pet_label.setMovie(media)
            media.start()
        elif isinstance(media, QPixmap):
            self.pet_label.setPixmap(media)
        else:
            self.pet_label.setPixmap(self.default_pixmap)

    def on_command_matched(self, command):
        """匹配到自定义命令，直接返回结果"""
        reply = self.command_parser.process_command(command)
        self.reply_bubble.setText(reply)
        self.adjust_bubble_position()
        self.reply_bubble.show()
        self.send_btn.setDisabled(False)
        self._reset_interact_timer()

    def on_feed_orange(self):
        """投喂橘子功能"""
        lines = self.config.get_config("character.lines.orange_happy", [
            "哇！谢谢主人的橘子🍊",
            "橘子好好吃！主人最好啦！",
            "甜甜的橘子！Doro超喜欢！"
        ])
        self.show_doro_line(lines)
        # 更新投喂记忆
        self.memory_manager.update_memory({"orange_count": "+1"})
        event_bus.action_triggered.emit("happy_feed")

    def on_show_about(self):
        """显示关于弹窗"""
        dialog = AboutDoroDialog()
        dialog.exec()

    def show_right_menu(self, pos):
        """显示右键菜单"""
        self.right_menu.exec(self.mapToGlobal(pos))

    def on_exit_app(self):
        """安全退出宠物程序"""
        self.close()
        QApplication.quit()

    def on_reload_config(self):
        """配置热重载，无需重启程序更新所有设置"""
        try:
            # 1. 重新加载所有配置文件
            self.config.reload_config()
            logger.info("配置文件重载成功")

            # 2. 热更新窗口基础设置
            window_width = self.config.get_config("settings.window.width", 400)
            window_height = self.config.get_config("settings.window.height", 400)
            self.setFixedSize(window_width, window_height)

            # 3. 热更新宠物图片
            image_path = self.config.get_config("settings.pet.image_path", "resources/images/logo.png")
            self.image_width = self.config.get_config("settings.pet.image_width", 180)
            self.image_height = self.config.get_config("settings.pet.image_height", 200)

            self.default_pixmap = QPixmap(get_resource_path(image_path)).scaled(
                self.image_width, self.image_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.pet_label.setPixmap(self.default_pixmap)
            self.pet_label.setGeometry(0, 0, self.image_width, self.image_height)

            # 4. 热更新输入框和按钮位置
            self.input_box.setGeometry(10, window_height - 50, 280, 40)
            self.send_btn.setGeometry(300, window_height - 50, 80, 40)

            # 5. 热更新拖拽手感参数
            self._move_threshold = self.config.get_config("window.move_threshold", 2)
            self._click_threshold = self.config.get_config("window.click_threshold", 250)

            # 6. 重启定时器，更新间隔参数
            self.idle_timer.stop()
            idle_interval = self.config.get_config("timer.idle_line_interval", 15000)
            self.idle_timer.start(idle_interval)

            self.ignore_timer.stop()
            ignore_interval = self.config.get_config("timer.ignore_check_interval", 45000)
            self.ignore_timer.start(ignore_interval)

            logger.info("配置热更新全部完成")

        except Exception as e:
            logger.error(f"配置重载失败: {str(e)}", exc_info=True)