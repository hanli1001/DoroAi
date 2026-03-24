import os
import sys
# 正确导入写法，放在path_utils.py顶部
from utils.logger import logger

def get_root_path() -> str:
    """获取项目根目录路径"""
    if getattr(sys, 'frozen', False):
        # 打包后的exe运行环境
        return os.path.dirname(sys.executable)
    else:
        # 开发环境
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_config_path(file_name: str) -> str:
    """获取配置文件路径"""
    return os.path.join(get_root_path(), "config", file_name)

def get_resource_path(relative_path: str) -> str:
    """获取资源文件绝对路径，带空值校验和异常处理"""
    # 1. 先校验入参非空
    if not relative_path:
        logger.error("传入的资源相对路径为空")
        raise ValueError("资源相对路径不能为空")

    # 2. 安全获取项目基础路径，避免返回None
    # 这里根据你的项目结构调整层级，确保能定位到项目根目录
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not base_path:
        logger.error("获取项目基础路径失败")
        raise RuntimeError("无法获取项目基础路径")

    # 3. 安全拼接路径
    full_path = os.path.join(base_path, relative_path)
    logger.info(f"资源路径解析完成: {full_path}")
    return full_path

def get_memory_path(file_name: str = "user_memory.json") -> str:
    """获取记忆文件路径"""
    return os.path.join(get_root_path(), file_name)