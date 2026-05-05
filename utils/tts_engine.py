import threading
import asyncio
import queue
from io import BytesIO
from PySide6.QtCore import QObject, Signal
from utils.logger import logger

class TTSEngine(QObject):
    """TTS 引擎：持久后台线程 + 异步事件循环，消除每次播放的线程创建延迟"""
    tts_finished = Signal()
    tts_error = Signal(str)

    def __init__(self):
        super().__init__()
        self._pygame = None
        self._edge_tts = None
        self._initialized = False
        self.voice = "zh-CN-XiaoxiaoNeural"
        self.rate = "+10%"
        self.volume = "+0%"
        self._is_playing = False
        self._lock = threading.Lock()
        self._loop = None
        self._thread = None
        self._ready = threading.Event()

    def _ensure_init(self):
        if self._initialized:
            return True
        try:
            import pygame
            self._pygame = pygame
            self._pygame.mixer.init()
        except Exception as e:
            logger.warning(f"Pygame初始化失败: {e}")
            return False
        try:
            import edge_tts
            self._edge_tts = edge_tts
        except ImportError:
            logger.warning("edge_tts未安装: pip install edge_tts")
            return False
        # 启动持久后台线程
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)
        self._initialized = True
        return True

    def _run_loop(self):
        """后台线程：运行持久的 asyncio 事件循环"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def speak(self, text: str):
        if not self._ensure_init():
            return
        play_text = text.split("【MEMORY_UPDATE")[0].strip()
        if not play_text:
            return
        # 在持久事件循环中调度 TTS 任务
        self._loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(self._do_tts(play_text))
        )

    async def _do_tts(self, text: str):
        if not self._edge_tts or not self._pygame:
            return
        try:
            with self._lock:
                if self._is_playing:
                    self.stop_tts()
                self._is_playing = True
            logger.info(f"TTS开始: {text[:20]}...")
            communicate = self._edge_tts.Communicate(text, self.voice, rate=self.rate, volume=self.volume)
            audio_data = BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.write(chunk["data"])
            audio_data.seek(0)
            self._pygame.mixer.music.load(audio_data, "mp3")
            self._pygame.mixer.music.play()
            while self._pygame.mixer.music.get_busy() and self._is_playing:
                await asyncio.sleep(0.1)
            logger.info("TTS播放完成")
            self.tts_finished.emit()
        except Exception as e:
            msg = f"TTS失败: {e}"
            logger.error(msg)
            self.tts_error.emit(msg)
        finally:
            with self._lock:
                self._is_playing = False

    def stop_tts(self):
        if not self._pygame:
            return
        try:
            if self._pygame.mixer.music.get_busy():
                self._pygame.mixer.music.stop()
        except Exception:
            pass
        with self._lock:
            self._is_playing = False
