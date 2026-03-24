from PySide6.QtCore import QObject, Signal

class EventSystem(QObject):
    """全局事件系统，所有模块通过事件通信，无需互相引用"""
    # 宠物交互事件
    pet_clicked = Signal()          # 左键点击宠物
    pet_double_clicked = Signal()   # 双击宠物
    pet_hovered = Signal()          # 鼠标悬停宠物
    pet_dragged = Signal()          # 拖拽宠物
    pet_right_clicked = Signal()    # 右键点击宠物

    # 对话事件
    user_input_sent = Signal(str)   # 用户发送了输入
    ai_reply_received = Signal(str) # 收到AI完整回复
    ai_stream_chunk = Signal(str)   # 收到AI流式片段

    # 动作事件
    action_triggered = Signal(str)  # 触发动作，参数为动作ID
    action_finished = Signal(str)   # 动作播放完成，参数为动作ID

    # 命令事件
    command_matched = Signal(dict)  # 匹配到自定义命令，参数为命令配置

    # 状态事件
    state_changed = Signal(str)     # 宠物状态改变，参数为新状态
    user_interacted = Signal()      # 用户有任何交互，重置冷落计时器

# 全局单例
event_bus = EventSystem()