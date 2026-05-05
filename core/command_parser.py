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
        self.config = ConfigLoader(config_path="config/commands.yaml")
        self.memory_manager = memory_manager
        self.commands_config = self.config.get_config("commands", default=[])
        self.command_cooldown = {}
        self._register_event_handlers()
        logger.info("命令解析器初始化完成")

    def _register_event_handlers(self):
        """注册事件处理器"""
        event_bus.user_input_sent.connect(self.parse_command)

    def parse_command(self, user_input: str):
        """解析用户输入，匹配自定义命令"""
        try:
            input_text = user_input.strip().lower()
            for command in self.commands_config:
                keywords = [k.lower() for k in command.get("keywords", [])]
                for keyword in keywords:
                    if keyword in input_text:
                        command_name = command.get("name", "unknown")
                        cooldown = command.get("cooldown", 0)
                        if cooldown > 0:
                            last_time = self.command_cooldown.get(command_name, 0)
                            if time.time() * 1000 - last_time < cooldown:
                                logger.debug(f"命令[{command_name}]冷却中，跳过触发")
                                continue
                            self.command_cooldown[command_name] = time.time() * 1000
                        logger.info(f"匹配到自定义命令: {command_name}")
                        event_bus.command_matched.emit(command)
                        return command
            return None
        except Exception as e:
            logger.error(f"命令解析异常: {e}", exc_info=True)
            return None

    def process_command(self, command: dict) -> str:
        """处理命令，返回AI回复"""
        if "memory_update" in command and command["memory_update"]:
            self.memory_manager.update_memory(command["memory_update"])
        reply = command["ai_reply"]
        placeholders = re.findall(r"\{(\w+)\}", reply)
        for placeholder in placeholders:
            value = self.memory_manager.get(placeholder, "")
            reply = reply.replace(f"{{{placeholder}}}", str(value))
        if "action_id" in command and command["action_id"]:
            event_bus.action_triggered.emit(command["action_id"])
        return reply

    def reload_commands(self):
        """热重载命令配置"""
        self.config = ConfigLoader(config_path="config/commands.yaml")
        self.commands_config = self.config.get_config("commands", [])
        logger.info("命令配置热重载完成")