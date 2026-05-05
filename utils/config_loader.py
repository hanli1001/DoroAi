import yaml
import os
from typing import Any, Dict
from utils.logger import logger

class ConfigLoader:
    def __init__(self, config_path: str = "config/settings.yaml"):
        """初始化时加载配置文件，保存实例配置路径"""
        self._config: Dict[str, Any] = {}
        self._config_path = config_path  # 保存实例配置路径，用于重载
        self.load_config(config_path)

    def load_config(self, config_path: str):
        """从 YAML 文件加载配置，全路径异常兜底"""
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

    def get_config(self, key: str, default: Any = None, index: int = None) -> Any:
        """
        通用配置获取方法，支持多层嵌套key、列表索引取值
        :param key: 配置项路径，用.分隔，如 "ai.api_url"、"lines.idle_lazy"
        :param default: 配置不存在时返回的默认值
        :param index: 可选，当配置项为列表时，返回对应索引的元素
        :return: 配置项值
        """
        if not self._config:
            logger.warning("配置尚未完成加载，返回默认值")
            return default

        # 逐层解析嵌套key
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                logger.warning(f"配置项 {key} 中 {k} 不存在，返回默认值 {default}")
                return default

        # 处理列表索引
        if index is not None and isinstance(value, list):
            if 0 <= index < len(value):
                value = value[index]
            else:
                logger.warning(f"配置项 {key} 索引 {index} 越界，返回默认值 {default}")
                return default

        return value

    def get_full_config(self) -> Dict[str, Any]:
        """返回完整配置深拷贝，避免外部修改内部数据"""
        import copy
        return copy.deepcopy(self._config) if self._config else {}

    def reload_config(self, config_path: str = None):
        """重新加载配置文件，默认使用实例化时的路径"""
        reload_path = config_path if config_path else self._config_path
        self.load_config(reload_path)
        logger.info(f"配置文件 {reload_path} 重新加载完成")