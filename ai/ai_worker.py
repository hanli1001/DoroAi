import sys

import requests
import json
from PySide6.QtCore import QObject, Signal, QThread
from utils.config_loader import ConfigLoader
from utils.logger import logger
from ai.prompt_manager import PromptManager
from ai.memory_manager import MemoryManager


class AIWorker(QObject):
    stream_chunk = Signal(str)  # 流式内容片段
    finished = Signal(str)  # 请求完成，返回完整回复
    error = Signal(str)  # 请求出错
    warmup_finished = Signal()  # 预热完成

    def __init__(self, memory_manager: MemoryManager):
        super().__init__()
        self.config = ConfigLoader()
        self.memory_manager = memory_manager
        self.prompt_manager = PromptManager(memory_manager)
        self.config=ConfigLoader(config_path="config/settings.yaml")

        # API配置
        self.url = self.config.get_config("ai.api_url")
        #self.url="https://ark.cn-beijing.volces.com/api/v3/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.config.get_config('ai.api_key')}",
            "Content-Type": "application/json"
        }
        '''self.headers = {
            "Authorization": f"Bearer 90d84c3f-e6c0-411c-a046-fc9db871fd3e",
            "Content-Type": "application/json"
        }'''
        self.model = self.config.get_config("ai.model")
       # self.model="doubao-seed-2-0-pro-260215"
        self.timeout_config = (
            self.config.get_config("ai.timeout_connect", 8),
            self.config.get_config("ai.timeout_read", 40)
        )

        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def warmup_connection(self):
        """预热API连接"""
        try:
            warmup_data = {
                "model": self.model,
                "messages": [{"role": "user", "content": "你好"}],
                "max_tokens": 5,
                "stream": False
            }
            self.session.post(self.url, json=warmup_data, timeout=10)
            self.warmup_finished.emit()
            logger.info("API连接预热完成，首次对话提速就绪")
        except Exception as e:
            logger.warning(f"预热未完成，网络波动，不影响正常对话: {str(e)}")

    def request_ai_stream(self, user_input: str):
        """发送流式AI请求"""
        full_reply = ""
        residual_bytes = b""

        try:
            system_prompt = self.prompt_manager.get_full_prompt()
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                "stream": True,
                "max_tokens": self.config.get_config("ai.max_tokens", 2048),
                "temperature": self.config.get_config("ai.temperature", 0.75)
            }

            logger.info(f"发送AI请求: {user_input}")
            response = self.session.post(
                self.url,
                json=data,
                timeout=self.timeout_config,
                stream=True
            )
            response.raise_for_status()
            response.encoding = "utf-8"

            for chunk in response.iter_content(chunk_size=1024):
                if not chunk:
                    continue
                chunk_bytes = residual_bytes + chunk
                residual_bytes = b""
                lines = chunk_bytes.split(b"\n")

                if not chunk_bytes.endswith(b"\n"):
                    residual_bytes = lines.pop()

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        line_str = line.decode("utf-8", errors="ignore")
                    except:
                        continue
                    if not line_str.startswith("data: "):
                        continue

                    chunk_data = line_str[6:]
                    if chunk_data == "[DONE]":
                        break

                    try:
                        chunk_json = json.loads(chunk_data)
                        delta_content = chunk_json["choices"][0]["delta"].get("content", "")
                        if delta_content:
                            full_reply += delta_content
                            self.stream_chunk.emit(delta_content)
                    except Exception:
                        continue

            logger.info("AI请求完成")
            self.finished.emit(full_reply)

        except Exception as e:
            error_info = f"AI请求失败: {str(e)}"
            logger.error(error_info)
            self.error.emit("你说的话Doro听到啦~🐾 网络有点卡，等会再和你聊哦")


