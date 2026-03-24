from PySide6.QtCore import QObject, Signal
from utils.logger import logger
from core.event_system import event_bus


class PetState:
    IDLE = "idle"  # 闲置
    INTERACT = "interact"  # 交互中
    DIALOG = "dialog"  # 对话中
    EMOTION = "emotion"  # 情绪表达中
    COMMAND = "command"  # 执行命令中


class PetStateMachine(QObject):
    state_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.current_state = PetState.IDLE
        self._register_event_handlers()

    def _register_event_handlers(self):
        """注册事件处理器"""
        event_bus.pet_clicked.connect(lambda _: self.change_state(PetState.INTERACT))
        event_bus.user_input_sent.connect(lambda _: self.change_state(PetState.DIALOG))
        event_bus.ai_reply_received.connect(lambda _: self.change_state(PetState.IDLE))
        event_bus.action_triggered.connect(lambda _: self.change_state(PetState.EMOTION))
        event_bus.command_matched.connect(lambda _: self.change_state(PetState.COMMAND))
        event_bus.action_finished.connect(self._on_action_finished)

    def change_state(self, new_state: str):
        """切换状态"""
        if self.current_state == new_state:
            return

        old_state = self.current_state
        self.current_state = new_state
        logger.info(f"宠物状态切换: {old_state} -> {new_state}")

        self.state_changed.emit(new_state)
        event_bus.state_changed.emit(new_state)

    def _on_action_finished(self, action_id: str):
        """动作完成后自动切回闲置状态"""
        if self.current_state in [PetState.EMOTION, PetState.COMMAND, PetState.INTERACT]:
            self.change_state(PetState.IDLE)

    def is_state(self, state: str) -> bool:
        """判断当前状态"""
        return self.current_state == state