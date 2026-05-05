import socket
import requests
from requests.adapters import HTTPAdapter
import json
from PySide6.QtCore import QObject, Signal
from utils.config_loader import ConfigLoader
from utils.logger import logger
from ai.prompt_manager import PromptManager
from ai.memory_manager import MemoryManager

class AIWorker(QObject):
    stream_chunk = Signal(str)
    finished = Signal(str)
    error = Signal(str)
    warmup_finished = Signal()

    def __init__(self, memory_manager: MemoryManager):
        super().__init__()
        self.config = ConfigLoader(config_path="config/settings.yaml")
        self.memory_manager = memory_manager
        self.prompt_manager = PromptManager(memory_manager)
        self.url = self.config.get_config("ai.api_url")
        self.headers = {
            "Authorization": f"Bearer {self.config.get_config('ai.api_key')}",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }
        self.model = self.config.get_config("ai.model")
        self.timeout_config = (
            self.config.get_config("ai.timeout_connect", 8),
            self.config.get_config("ai.timeout_read", 40)
        )
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.session.mount("https://", FixedHTTPAdapter())
        self.session.mount("http://", FixedHTTPAdapter())
        self._is_running = False


    def stop_request(self):
        self._is_running = False
        logger.info("AI worker stopped")

    def warmup_connection(self):
        try:
            warmup_data = {
                "model": self.model,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5,
                "stream": False
            }
            self.session.post(self.url, json=warmup_data, timeout=10)
            self.warmup_finished.emit()
            logger.info("API 预热完成")
        except Exception as e:
            logger.warning(f"预热失败（不影响正常对话）: {e}")

    def request_ai_stream(self, user_input: str):
        full_reply = ""
        self._is_running = True
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
            logger.info(f"发送 AI 请求: {user_input[:50]}...")
            response = self.session.post(
                self.url,
                json=data,
                timeout=self.timeout_config,
                stream=True
            )
            response.raise_for_status()
            response.encoding="utf-8"
            for line in response.iter_lines(decode_unicode=True):
                if not self._is_running:
                    response.close()
                    break
                if not line:
                    continue
                if line.startswith("data:"):
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        chunk_json = json.loads(chunk)
                        content = chunk_json["choices"][0]["delta"].get("content", "")
                        if content:
                            full_reply += content
                            self.stream_chunk.emit(content)
                    except Exception:
                        continue
            logger.info("AI 请求完成")
            self.finished.emit(full_reply)
        except Exception as e:
            error_msg = f"AI 请求失败: {e}"
            logger.error(error_msg)
            self.error.emit(error_msg)

class FixedHTTPAdapter(HTTPAdapter):
    """修正适配器"""
    def init_poolmanager(self, *args, **kwargs):
        kwargs.setdefault("socket_options", [])
        kwargs["socket_options"].extend([
            (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1),
            (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
        ])
        super().init_poolmanager(*args, **kwargs)