import yaml
import os
from typing import Any, Dict
import logging

# 配置日志（可选，用于调试）
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConfigLoader:
    def __init__(self, config_path: str = "config/settings.yaml"):
        """初始化时加载配置文件"""
        self._config = None
        self.load_config(config_path)  # 调用加载方法

    def load_config(self, config_path: str):
        """从 YAML 文件加载配置，失败时回退到空配置"""
        if not os.path.exists(config_path):
            logger.warning(f"配置文件 {config_path} 不存在，使用默认空配置")
            self._config = {}
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
            logger.info(f"成功加载配置文件：{config_path}")
        except Exception as e:
            logger.error(f"加载配置文件 {config_path} 失败：{e}，使用默认空配置")
            self._config = {}

    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置项，支持多级 key（如 'a.b.c'）"""
        if not self._config:
            logger.warning("配置尚未完成加载，返回默认值")
            return default

        keys = key.split(".")
        value = self._config
        for k in keys:
            try:
                value = value[k]
            except (KeyError, TypeError):
                logger.warning(f"配置项 {key} 不存在，返回默认值")
                return default
        return value

    def get_full_config(self) -> Dict[str, Any]:
        """返回完整配置（深拷贝避免修改原配置）"""
        import copy
        return copy.deepcopy(self._config) if self._config else {}

    def reload_config(self, config_path: str = None):
        """重新加载配置文件"""
        if config_path is None:
            # 从当前配置路径重新加载（需在 __init__ 中记录路径）
            config_path = getattr(self, "_config_path", "character.yaml")
        self.load_config(config_path)
        logger.info("配置重新加载完成")