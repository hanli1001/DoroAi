"""全局事件总线 — 模块间解耦通信的唯一通道"""
from PySide6.QtCore import QObject, Signal


class EventSystem(QObject):
    """所有模块通过此单例通信，禁止模块间直接引用"""

    # ── 宠物交互 ──
    pet_clicked = Signal()
    """左键单击宠物"""

    pet_double_clicked = Signal()
    """双击宠物（预留）"""

    pet_hovered = Signal()
    """鼠标悬停宠物（预留）"""

    pet_dragged = Signal()
    """拖拽宠物（预留）"""

    pet_right_clicked = Signal()
    """右键点击宠物（预留）"""

    # ── 对话管道 ──
    user_input_sent = Signal(str)
    """用户消息已发送 → AIWorker.request_ai_stream"""

    ai_reply_received = Signal(str)
    """AI 完整回复已收到 → 状态机切回 IDLE"""

    ai_stream_chunk = Signal(str)
    """AI 流式片段到达 → UI 逐字更新"""

    # ── 动作管道 ──
    action_triggered = Signal(str)
    """触发动作(action_id) → ActionManager._play_action + PetMainWindow 更新画面"""

    action_finished = Signal(str)
    """动作播放完成(action_id) → 状态机切回 IDLE"""

    # ── 命令管道 ──
    command_matched = Signal(dict)
    """匹配到自定义命令(command dict) → CommandParser.process_command"""

    # ── 状态管道 ──
    state_changed = Signal(str)
    """宠物状态变更(new_state) → 各模块响应"""

    user_interacted = Signal()
    """用户有任何交互 → 重置冷落计时器"""

    def disconnect_all(self):
        """断开所有信号的所有连接（用于热重载或退出清理）"""
        for name in dir(self):
            attr = getattr(self, name)
            if isinstance(attr, Signal):
                try: attr.disconnect()
                except (TypeError, RuntimeError): pass


# 全局单例 — 整个应用唯一的事件通道
event_bus = EventSystem()
