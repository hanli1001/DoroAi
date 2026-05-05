import threading
import tempfile
import os as _os
from PySide6.QtCore import QObject, Signal
from PIL import Image, ImageEnhance, ImageFilter
import io
import numpy as np
from utils.logger import logger

class OCRWorker(QObject):
    ocr_finished = Signal(str)
    ocr_error = Signal(str)
    init_finished = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reader = None
        self._is_init_success = False
        self._ocr_lock = threading.Lock()

    def init_ocr_model(self):
        """初始化OCR模型，在子线程调用"""
        try:
            _os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
            logger.info("开始初始化OCR模型...")
            import easyocr
            self.reader = easyocr.Reader(['ch_sim', 'en'], gpu=False, download_enabled=True)
            self._is_init_success = True
            logger.info("OCR模型初始化完成")
            self.init_finished.emit(True)
        except ImportError:
            msg = "OCR依赖缺失：pip install easyocr torch"
            logger.error(msg)
            self.init_finished.emit(False)
            self.ocr_error.emit(msg)
        except Exception as e:
            logger.error(f"OCR初始化失败: {e}", exc_info=True)
            self.init_finished.emit(False)
            self.ocr_error.emit(str(e))

    def start_ocr_task(self, pixmap):
        if not self._is_init_success or not self.reader:
            self.ocr_error.emit("OCR模型未初始化完成，请稍后重试")
            return
        try:
            fd, tmpname = tempfile.mkstemp(suffix=".png")
            _os.close(fd)
            pixmap.save(tmpname, "PNG")
            with open(tmpname, "rb") as f:
                png_bytes = f.read()
            _os.unlink(tmpname)
            logger.info(f"截图转换: {len(png_bytes)} bytes")
            t = threading.Thread(target=self._do_ocr, args=(png_bytes,), daemon=True)
            t.start()
        except Exception as e:
            logger.error(f"图片转换失败: {e}", exc_info=True)
            self.ocr_error.emit(f"图片转换失败: {e}")

    def _do_ocr(self, png_bytes):
        try:
            with self._ocr_lock:
                logger.info(f"OCR开始, 数据: {len(png_bytes)} bytes")
                image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
                w, h = image.size
                logger.info(f"图片尺寸: {w}x{h}")

                if w < 300 or h < 100:
                    scale = max(300 / w, 100 / h, 2.0)
                    image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

                gray = image.convert("L")
                gray = ImageEnhance.Contrast(gray).enhance(2.0)
                gray = gray.filter(ImageFilter.SHARPEN)
                gray_np = np.array(gray)

                result = self.reader.readtext(gray_np, detail=0, paragraph=False,
                                              text_threshold=0.4, low_text=0.25,
                                              min_size=8, width_ths=0.5)
                text = "\n".join(result) if result else ""
                if not text.strip():
                    text = "未识别到有效文字内容"
                logger.info(f"OCR完成: {text[:80]}")
                self.ocr_finished.emit(text)
        except Exception as e:
            logger.error(f"OCR失败: {e}", exc_info=True)
            self.ocr_error.emit(f"OCR识别失败: {e}")
