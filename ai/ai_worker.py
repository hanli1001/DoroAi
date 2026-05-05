import socket
import requests
from requests.adapters import HTTPAdapter
import json
import re
import urllib.request
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

    # ── 工具调用 ──

    _WEATHER_KW = ['天气', '气温', '温度', '下雨', '下雪', '刮风', '几度', '多少度',
                    '热不热', '冷不冷', '晴天', '阴天', '多云', '闷热', '凉快',
                    '穿什么', '带伞', '雨伞', '防晒', '紫外线']
    _CITY_PATTERN = re.compile(
        r'(北京|上海|广州|深圳|杭州|成都|重庆|武汉|西安|南京|天津|苏州|长沙|郑州|东莞|青岛|沈阳|宁波|昆明|大连|厦门|合肥|佛山|福州|哈尔滨|济南|温州|长春|石家庄|常州|泉州|南宁|贵阳|南昌|太原|烟台|嘉兴|南通|金华|珠海|惠州|徐州|海口|乌鲁木齐|拉萨|呼和浩特|银川|西宁|兰州|台北|香港|澳门)'
    )

    def _fetch_weather(self, city: str) -> str:
        """获取指定城市天气"""
        try:
            req = urllib.request.Request(
                f"https://wttr.in/{urllib.request.quote(city)}?format=j1&lang=zh",
                headers={"User-Agent": "DoroAi/1.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                cur = data["current_condition"][0]
                temp = cur["temp_C"]
                desc = cur["weatherDesc"][0]["value"]
                humidity = cur["humidity"]
                feels_like = cur["FeelsLikeC"]
                wind = cur["winddir16Point"] + " " + cur["windspeedKmph"] + "km/h"
                return f"{city}当前天气：{desc}，温度{temp}°C（体感{feels_like}°C），湿度{humidity}%，风向风速{wind}。"
        except Exception as e:
            logger.warning(f"天气查询失败({city}): {e}")
            return ""

    def _detect_tool_calls(self, user_input: str) -> str:
        """检测用户输入中的工具调用需求，返回上下文注入文本"""
        ctx_parts = []

        # 天气查询
        if any(kw in user_input for kw in self._WEATHER_KW):
            match = self._CITY_PATTERN.search(user_input)
            city = match.group(1) if match else None
            weather = self._fetch_weather(city) if city else ""
            if weather:
                ctx_parts.append(f"[天气工具] {weather}")

        return "\n".join(ctx_parts) if ctx_parts else ""

    # ── 核心请求 ──

    def request_ai_stream(self, user_input: str):
        full_reply = ""
        self._is_running = True
        try:
            system_prompt = self.prompt_manager.get_full_prompt()

            # 检测并执行工具调用
            tool_context = self._detect_tool_calls(user_input)

            # 构建 messages
            messages = [
                {"role": "system", "content": system_prompt},
            ]
            if tool_context:
                messages.append({
                    "role": "system",
                    "content": f"[工具执行结果]\n{tool_context}\n（你已获取到实时数据，请直接基于这些数据回答用户。）"
                })
            messages.append({"role": "user", "content": user_input})

            data = {
                "model": self.model,
                "messages": messages,
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
            response.encoding = "utf-8"
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
