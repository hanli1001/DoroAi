"""TTS 引擎 — 多后端支持（Fish Audio / GPT-SoVITS / edge_tts + 自动回退）"""
import threading
import asyncio
import queue
import os
import sys
import subprocess
import time
import tempfile
from io import BytesIO
from PySide6.QtCore import QObject, Signal
from utils.logger import logger


class TTSEngine(QObject):
    """TTS 引擎：持久后台线程 + 异步事件循环，支持多后端"""
    tts_finished = Signal()
    tts_error = Signal(str)

    def __init__(self, config_get=None):
        super().__init__()
        self._config_get = config_get or (lambda k, **kw: None)
        self._pygame = None
        self._edge_tts = None
        self._fish_session = None
        self._initialized = False
        self._is_playing = False
        self._lock = threading.Lock()
        self._loop = None
        self._thread = None
        self._ready = threading.Event()
        self._doro_audio_bytes = None
        self._doro_audio_text = None
        self._gpt_sovits_process = None
        self._gpt_sovits_ready = threading.Event()
        self._load_doro_reference()

    # ── 公共接口 ──

    def speak(self, text: str, backend: str = None):
        if not self._ensure_init():
            return
        play_text = text.split("【MEMORY_UPDATE")[0].strip()
        if not play_text:
            return
        if backend is None:
            backend = self._config_get("tts.backend", default="edge_tts")
        self._loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(self._do_tts(play_text, backend))
        )

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

    # ── 初始化 ──

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
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)
        self._initialized = True
        return True

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def _load_doro_reference(self):
        """加载 Doro 参考音频用于语音克隆"""
        try:
            ref_path = self._config_get("tts.doro_ref_audio", default="resources/sounds/doro_voice.wav")
            if ref_path and os.path.exists(ref_path):
                with open(ref_path, "rb") as f:
                    self._doro_audio_bytes = f.read()
                self._doro_audio_text = self._config_get("tts.doro_ref_text", default="")
                logger.info(f"Doro参考音频加载: {ref_path} ({len(self._doro_audio_bytes)} bytes)")
        except Exception as e:
            logger.warning(f"Doro参考音频加载失败: {e}")

    # ── 核心 TTS ──

    async def _do_tts(self, text: str, backend: str):
        if not self._pygame:
            return
        try:
            with self._lock:
                if self._is_playing:
                    self.stop_tts()
                self._is_playing = True
            logger.info(f"TTS开始 [{backend}]: {text[:30]}...")

            audio_data = None

            if backend == "fish_audio":
                audio_data = await self._fish_audio_tts(text)
            if not audio_data and backend in ("fish_audio", "gpt_sovits"):
                audio_data = await self._gpt_sovits_tts(text)
            if not audio_data:
                audio_data = await self._edge_tts_tts(text)

            if audio_data:
                self._pygame.mixer.music.load(audio_data)
                self._pygame.mixer.music.play()
                while self._pygame.mixer.music.get_busy() and self._is_playing:
                    await asyncio.sleep(0.1)
                logger.info("TTS播放完成")
                self.tts_finished.emit()
            else:
                raise Exception("所有TTS后端均失败")
        except Exception as e:
            msg = f"TTS失败: {e}"
            logger.error(msg)
            self.tts_error.emit(msg)
        finally:
            with self._lock:
                self._is_playing = False

    # ── Fish Audio 后端（语音克隆） ──

    async def _fish_audio_tts(self, text: str) -> BytesIO:
        """使用 Fish Audio API + Doro 参考音频进行语音克隆"""
        if not self._doro_audio_bytes:
            return None
        api_key = self._config_get("tts.fish_audio_api_key", default="")
        if not api_key:
            return None
        try:
            from fish_audio_sdk import Session, TTSRequest, ReferenceAudio
            if self._fish_session is None:
                self._fish_session = Session(api_key)
            references = []
            if self._doro_audio_bytes:
                ref_text = self._doro_audio_text or text[:20]
                references.append(ReferenceAudio(audio=self._doro_audio_bytes, text=ref_text))
            request = TTSRequest(
                text=text,
                references=references,
                format="mp3",
                latency="balanced",
            )
            audio_buf = BytesIO()
            async with self._fish_session.stream_tts(request) as stream:
                async for chunk in stream:
                    if hasattr(chunk, 'data') and chunk.data:
                        audio_buf.write(chunk.data)
            audio_buf.seek(0)
            if audio_buf.getbuffer().nbytes > 0:
                return audio_buf
        except Exception as e:
            logger.warning(f"Fish Audio TTS失败: {e}")
        return None

    # ── GPT-SoVITS 后端（本地语音克隆，自动启动） ──

    def _start_gpt_sovits_server(self):
        """后台启动 GPT-SoVITS API 子进程"""
        if self._gpt_sovits_process is not None:
            return  # 已经在启动中

        gpt_dir = self._config_get("tts.gpt_sovits_dir", default="gpt_sovits")
        if not os.path.isabs(gpt_dir):
            gpt_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), gpt_dir)

        api_py = os.path.join(gpt_dir, "api_v2.py")
        if not os.path.exists(api_py):
            logger.warning(f"GPT-SoVITS api_v2.py 不存在: {api_py}")
            return

        # 使用 doro_gpt_sovits 环境的 Python（GPT-SoVITS 依赖在该环境中）
        # sys.executable 示例: E:\Anaconda\envs\doro_ai\python.exe
        conda_envs = os.path.dirname(os.path.dirname(sys.executable))  # E:\Anaconda\envs
        python_exe = os.path.join(conda_envs, "doro_gpt_sovits", "python.exe")
        if not os.path.exists(python_exe):
            python_exe = sys.executable

        env = os.environ.copy()
        env["SSL_CERT_FILE"] = os.path.join(conda_envs, "doro_gpt_sovits", "Library", "ssl", "cacert.pem")
        env["PYTHONIOENCODING"] = "utf-8"

        port = self._config_get("tts.gpt_sovits_port", default="9880")

        logger.info(f"启动 GPT-SoVITS API: {api_py} (端口 {port})")

        try:
            config_path = "GPT_SoVITS/configs/tts_infer.yaml"
            self._gpt_sovits_process = subprocess.Popen(
                [python_exe, "api_v2.py", "-a", "127.0.0.1", "-p", port, "-c", config_path],
                cwd=gpt_dir, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            threading.Thread(target=self._monitor_gpt_sovits, daemon=True).start()
        except Exception as e:
            logger.warning(f"GPT-SoVITS 启动失败: {e}")
            self._gpt_sovits_process = None

    def _monitor_gpt_sovits(self):
        """等待 API 就绪"""
        port = self._config_get("tts.gpt_sovits_port", default="9880")
        url = f"http://127.0.0.1:{port}/docs"
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                import urllib.request
                urllib.request.urlopen(url, timeout=2)
                self._gpt_sovits_ready.set()
                logger.info("GPT-SoVITS API 就绪")
                return
            except Exception:
                time.sleep(2)
        logger.warning("GPT-SoVITS API 启动超时（120s）")

    async def _gpt_sovits_tts(self, text: str) -> BytesIO:
        """调用本地 GPT-SoVITS API 进行 Doro 语音克隆"""
        port = self._config_get("tts.gpt_sovits_port", default="9880")
        api_url = f"http://127.0.0.1:{port}"

        # 自动启动（首次调用时）
        if not self._gpt_sovits_ready.is_set():
            self._start_gpt_sovits_server()
            if not self._gpt_sovits_ready.wait(timeout=130):
                logger.warning("GPT-SoVITS 未就绪，回退到 edge_tts")
                return None

        try:
            import aiohttp
            ref_audio = self._config_get("tts.doro_ref_audio", default="resources/sounds/doro_voice.wav")
            if not os.path.isabs(ref_audio):
                ref_audio = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ref_audio)
            params = {
                "text": text,
                "text_lang": "zh",
                "ref_audio_path": ref_audio,
                "prompt_lang": "zh",
                "prompt_text": "",
                "top_k": 5,
                "top_p": float(self._config_get("tts.gpt_sovits_top_p", default=0.7)),
                "temperature": float(self._config_get("tts.gpt_sovits_temperature", default=0.7)),
                "speed_factor": float(self._config_get("tts.gpt_sovits_speed_factor", default=1.12)),
                "sample_steps": int(self._config_get("tts.gpt_sovits_sample_steps", default=96)),
                "media_type": "wav",
                "streaming_mode": 0,
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{api_url}/tts", params=params, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        buf = BytesIO(data)
                        buf.seek(0)
                        return buf
                    else:
                        logger.warning(f"GPT-SoVITS API error: {resp.status}")
        except Exception as e:
            logger.warning(f"GPT-SoVITS TTS失败: {e}")
        return None

    def shutdown(self):
        """停止 GPT-SoVITS 子进程"""
        if self._gpt_sovits_process:
            try:
                self._gpt_sovits_process.terminate()
                self._gpt_sovits_process.wait(timeout=5)
            except Exception:
                try:
                    self._gpt_sovits_process.kill()
                except Exception:
                    pass
            self._gpt_sovits_process = None

    # ── Edge TTS 后端（带音频后处理） ──

    def _get_edge_voice(self) -> str:
        return self._config_get("tts.voice", default="zh-CN-XiaoyiNeural")

    def _get_edge_rate(self) -> str:
        return self._config_get("tts.rate", default="+10%")

    def _get_edge_volume(self) -> str:
        return self._config_get("tts.volume", default="+0%")

    async def _edge_tts_tts(self, text: str) -> BytesIO:
        """使用 edge_tts 合成语音，可选后处理变调"""
        if not self._edge_tts:
            return None
        try:
            voice = self._get_edge_voice()
            rate = self._get_edge_rate()
            volume = self._get_edge_volume()
            communicate = self._edge_tts.Communicate(text, voice, rate=rate, volume=volume)
            audio_data = BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.write(chunk["data"])
            audio_data.seek(0)

            # 音频后处理：变调/变速以逼近 Doro 音色
            enable_doro_effect = self._config_get("tts.audio_processing.enable_doro_effect", default=True)
            if enable_doro_effect:
                audio_data = self._apply_doro_effect(audio_data)
            return audio_data
        except Exception as e:
            logger.warning(f"Edge TTS失败: {e}")
        return None

    def _apply_doro_effect(self, audio_buf: BytesIO) -> BytesIO:
        """对音频应用 Doro 风格变调（升高音调 + 微调速度），输出 WAV"""
        try:
            import librosa
            import soundfile as sf
            import numpy as np

            pitch_semitones = float(self._config_get("tts.audio_processing.pitch_shift", default=5.0))
            speed_factor = float(self._config_get("tts.audio_processing.speed_factor", default=1.08))

            audio_buf.seek(0)
            y, sr = librosa.load(audio_buf, sr=None)

            if pitch_semitones != 0:
                y = librosa.effects.pitch_shift(y=y, sr=sr, n_steps=pitch_semitones)

            if speed_factor != 1.0:
                y = librosa.effects.time_stretch(y=y, rate=speed_factor)

            out_buf = BytesIO()
            sf.write(out_buf, y, sr, format='WAV')
            out_buf.seek(0)
            return out_buf
        except Exception as e:
            logger.warning(f"Doro音效处理失败，使用原始音频: {e}")
            audio_buf.seek(0)
            return audio_buf
