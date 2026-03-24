import os
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QPixmap,QMovie
from utils.config_loader import ConfigLoader
from utils.path_utils import get_resource_path
from utils.logger import logger
from core.event_system import event_bus
from core.pet_state import PetStateMachine


class ActionManager(QObject):
    def __init__(self, state_machine: PetStateMachine):
        super().__init__()
        self.config = ConfigLoader()
        self.state_machine = state_machine
        self.actions_config = self.config.get_config("actions", {})
        self.current_action = None
        self.current_movie = None
        self.action_timer = QTimer(self)
        self.action_timer.setSingleShot(True)
        self.action_timer.timeout.connect(self._on_action_timeout)

        self._register_event_handlers()
        logger.info("动作管理器初始化完成")

    def _register_event_handlers(self):
        """注册事件处理器"""
        event_bus.action_triggered.connect(self.trigger_action_by_id)
        event_bus.pet_clicked.connect(lambda: self.trigger_action_by_trigger("left_click"))
        event_bus.pet_hovered.connect(lambda: self.trigger_action_by_trigger("mouse_hover"))

    def _load_media(self, path: str):
        """加载媒体资源（图片/GIF）"""
        full_path = get_resource_path(path)
        if not os.path.exists(full_path):
            logger.warning(f"动作资源不存在: {full_path}")
            return None

        # 判断是图片还是GIF
        if full_path.lower().endswith(".gif"):
            movie = QMovie(full_path)
            if not movie.isValid():
                logger.error(f"GIF资源无效: {full_path}")
                return None
            return movie
        else:
            pixmap = QPixmap(full_path)
            if pixmap.isNull():
                logger.error(f"图片资源无效: {full_path}")
                return None
            return pixmap

    def trigger_action_by_id(self, action_id: str):
        """通过动作ID触发动作"""
        # 查找动作
        target_action = None
        for action_group in self.actions_config.values():
            for action in action_group:
                if action["id"] == action_id:
                    target_action = action
                    break
            if target_action:
                break

        if not target_action:
            logger.warning(f"动作ID不存在: {action_id}")
            return

        self._play_action(target_action)

    def trigger_action_by_trigger(self, trigger_key: str):
        """通过触发关键词触发动作"""
        for action_group in self.actions_config.values():
            for action in action_group:
                if "trigger" in action and trigger_key in action["trigger"]:
                    self._play_action(action)
                    return

    def trigger_action_by_command(self, command_keyword: str):
        """通过命令关键词触发动作"""
        for action in self.actions_config.get("command", []):
            if command_keyword in action["command"]:
                self._play_action(action)
                return action

    def _play_action(self, action: dict):
        """播放动作"""
        action_id = action["id"]
        logger.info(f"开始播放动作: {action['name']} ({action_id})")

        # 停止当前动作
        self._stop_current_action()

        # 加载媒体资源
        media = self._load_media(action["path"])
        if not media:
            return

        self.current_action = action
        duration = action.get("duration", 3000)

        # 发送信号，通知UI更新
        if isinstance(media, QMovie):
            self.current_movie = media
            event_bus.action_triggered.emit("movie")
        else:
            event_bus.action_triggered.emit("pixmap")

        # 启动定时器，动作结束后发送完成信号
        if duration > 0:
            self.action_timer.start(duration)

    def _stop_current_action(self):
        """停止当前动作"""
        if self.current_movie:
            self.current_movie.stop()
            self.current_movie = None
        if self.action_timer.isActive():
            self.action_timer.stop()
        self.current_action = None

    def _on_action_timeout(self):
        """动作播放超时，发送完成信号"""
        if self.current_action:
            action_id = self.current_action["id"]
            logger.info(f"动作播放完成: {self.current_action['name']} ({action_id})")
            event_bus.action_finished.emit(action_id)
            self._stop_current_action()

    def get_current_media(self):
        """获取当前正在播放的媒体资源"""
        if self.current_movie:
            return self.current_movie
        elif self.current_action:
            return self._load_media(self.current_action["path"])
        else:
            # 返回默认图片
            default_path = self.config.get_config("pet.image_path")
            return QPixmap(get_resource_path(default_path))

    def reload_actions(self):
        """热重载动作配置"""
        self.actions_config = self.config.get_config("actions", {})
        logger.info("动作配置热重载完成")