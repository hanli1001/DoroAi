import os
import json
from PySide6.QtCore import QObject
from utils.path_utils import get_memory_path
from utils.logger import logger
from utils.config_loader import ConfigLoader

class MemoryManager(QObject):
    def __init__(self):
        super().__init__()
        config = ConfigLoader()
        self.memory_file = get_memory_path(config.get_config("memory.memory_file", "user_memory.json"))
        self.memory_data = {
            "user_name": "",
            "user_nickname": "",
            "likes": [],
            "dislikes": [],
            "habits": [],
            "orange_count": 0,
            "custom_info": {}
        }
        self.load_memory()

    def load_memory(self):
        """加载记忆文件"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)
                    self.memory_data.update(loaded_data)
                logger.info(f"用户记忆加载成功，已投喂橘子{self.memory_data['orange_count']}个")
            except Exception as e:
                logger.error(f"记忆加载失败: {str(e)}")

    def save_memory(self):
        """保存记忆文件"""
        try:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.memory_data, f, ensure_ascii=False, indent=2)
            logger.debug("记忆保存成功")
        except Exception as e:
            logger.error(f"记忆保存失败: {str(e)}")

    def update_memory(self, update_dict: dict):
        """更新记忆"""
        for key, value in update_dict.items():
            if key in self.memory_data:
                # 处理增量更新（比如橘子计数+1）
                if isinstance(value, str) and value.startswith("+") and isinstance(self.memory_data[key], int):
                    try:
                        add_num = int(value[1:])
                        self.memory_data[key] += add_num
                    except:
                        self.memory_data[key] = value
                elif isinstance(self.memory_data[key], list) and isinstance(value, list):
                    self.memory_data[key] = list(set(self.memory_data[key] + value))
                else:
                    self.memory_data[key] = value
            else:
                self.memory_data["custom_info"][key] = value
        self.save_memory()
        logger.info(f"用户记忆已更新: {update_dict}")

    def get_memory_prompt(self) -> str:
        """生成AI用的记忆prompt"""
        memory_parts = []
        for key, value in self.memory_data.items():
            if value:
                if key == "user_name" and value:
                    memory_parts.append(f"用户的名字是{value}")
                elif key == "user_nickname" and value:
                    memory_parts.append(f"你可以称呼用户为{value}")
                elif key == "likes" and value:
                    memory_parts.append(f"用户喜欢的东西: {','.join(value)}")
                elif key == "dislikes" and value:
                    memory_parts.append(f"用户不喜欢的东西: {','.join(value)}")
                elif key == "habits" and value:
                    memory_parts.append(f"用户的习惯: {','.join(value)}")
                elif key == "orange_count" and value:
                    memory_parts.append(f"用户已经给你投喂了{value}个橘子，橘子是你最喜欢的东西")
                elif key == "custom_info" and value:
                    for k, v in value.items():
                        memory_parts.append(f"用户的{k}: {v}")
        if not memory_parts:
            return "暂无用户的已知信息"
        return "\n".join(memory_parts)

    def get(self, key: str, default=None):
        """获取记忆值"""
        return self.memory_data.get(key, self.memory_data["custom_info"].get(key, default))