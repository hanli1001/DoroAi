# utils/logger.py 完整可直接用代码
import logging

# 全局单例logger实例，其他文件直接导入即可用
logger = logging.getLogger("DoroAi")
logger.setLevel(logging.DEBUG)

# 避免重复添加handler导致日志重复打印
if not logger.handlers:
    # 控制台输出配置
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    # 日志格式
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

__all__ = ["logger"]