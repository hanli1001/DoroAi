import re
import time
from PySide6.QtCore import QObject
from utils.config_loader import ConfigLoader
from utils.logger import logger
from core.event_system import event_bus
from ai.memory_manager import MemoryManager


class CommandParser(QObject):
    def __init__(self, memory_manager: MemoryManager):
        super().__init__()
        self.config = ConfigLoader()
        self.memory_manager = memory_manager
        self.commands_config = self.config.get_config("commands.commands", [])
        self.command_cooldown = {}  # 命令冷却记录
        self._register_event_handlers()
        logger.info("命令解析器初始化完成")

    def _register_event_handlers(self):
        """注册事件处理器"""
        event_bus.user_input_sent.connect(self.parse_command)

    def parse_command(self, user_input: str):
        """解析用户输入，匹配自定义命令"""
        input_text = user_input.strip().lower()

        for command in self.commands_config:
            keywords = [k.lower() for k in command["keywords"]]
            # 匹配关键词
            for keyword in keywords:
                if keyword in input_text:
                    # 检查冷却
                    command_name = command["name"]
                    cooldown = command.get("cooldown", 0)
                    if cooldown > 0:
                        last_time = self.command_cooldown.get(command_name, 0)
                        if time.time() * 1000 - last_time < cooldown:
                            logger.debug(f"命令[{command_name}]冷却中，跳过触发")
                            continue
                        self.command_cooldown[command_name] = time.time() * 1000

                    # 匹配到命令，发送信号
                    logger.info(f"匹配到自定义命令: {command_name}")
                    event_bus.command_matched.emit(command)
                    return command

        return None

    def process_command(self, command: dict) -> str:
        """处理命令，返回AI回复"""
        # 更新记忆
        if "memory_update" in command and command["memory_update"]:
            self.memory_manager.update_memory(command["memory_update"])

        # 处理回复中的占位符
        reply = command["ai_reply"]
        # 匹配{xxx}格式的占位符
        placeholders = re.findall(r"\{(\w+)\}", reply)
        for placeholder in placeholders:
            value = self.memory_manager.get(placeholder, "")
            reply = reply.replace(f"{{{placeholder}}}", str(value))

        # 触发对应动作
        if "action_id" in command and command["action_id"]:
            event_bus.action_triggered.emit(command["action_id"])

        return reply

    def reload_commands(self):
        """热重载命令配置"""
        self.commands_config = self.config.get_config("commands.commands", [])
        logger.info("命令配置热重载完成")