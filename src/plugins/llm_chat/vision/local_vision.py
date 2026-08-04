"""本地预筛：CLIP 多标签分类 + OCR 文字提取

零成本、本地推理：
- CLIP ViT-B/32 对图片做多标签分类（宠物/美食/表情包/动漫...）
- RapidOCR 提取图片上的文字（表情包/截图核心场景）

两者均在 asyncio.to_thread 中执行（torch/onnx 为同步阻塞），不阻塞事件循环。
若依赖未安装，自动降级为不可用，不影响主流程。
"""

import asyncio
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image
from nonebot import logger

# ── CLIP 类别标签集（每类映射一组英文文本提示，prompt ensembling 提准确率）──
_CLIP_CATEGORIES = {
    "宠物": ["a cute pet cat", "a dog photo", "an adorable animal", "a pet at home"],
    "美食": ["delicious food dish", "a meal on a table", "food photography"],
    "饮品": ["a cocktail drink", "a glass of beverage", "a cup of coffee"],
    "风景": ["natural landscape scenery", "mountain and sky", "beautiful scenery"],
    "自拍": ["a selfie of a person", "a face self portrait", "a girl taking selfie"],
    "人物": ["a group of people", "a person portrait photo"],
    "日常": ["daily life photo", "casual life moment", "an indoor scene"],
    "表情包": ["funny meme image", "internet meme", "comic face expression meme"],
    "截图": ["a screenshot of chat", "web page screenshot", "game screenshot"],
    "动漫": ["anime illustration", "anime character art", "anime style drawing"],
}

# 单例（懒加载）
_clip_model = None
_clip_processor = None
_ocr_engine = None


@dataclass
class LocalMeta:
    """本地预筛结果"""

    clip_category: str = "其他"
    clip_conf: float = 0.0
    ocr_text: str = ""
    has_text: bool = False


def _load_clip(model_path: str = "models/clip-vit-base-patch32"):
    """懒加载 CLIP 模型；本地路径优先，不存在时回退在线；失败保持 None"""
    global _clip_model, _clip_processor
    if _clip_model is None:
        try:
            from transformers import CLIPModel, CLIPProcessor

            # 本地目录优先（modelscope/手动下载到本地），否则在线加载
            source = (
                model_path
                if model_path and Path(model_path).exists()
                else "openai/clip-vit-base-patch32"
            )
            _clip_model = CLIPModel.from_pretrained(source)
            _clip_processor = CLIPProcessor.from_pretrained(source)
            logger.info(f"[Vision] CLIP ViT-B/32 已加载: {source}")
        except Exception as e:
            logger.warning(f"[Vision] CLIP 加载失败（预筛类别不可用）: {e}")
            _clip_model = False  # 标记失败，避免重复尝试
    return _clip_model if _clip_model else None, _clip_processor


def _load_ocr():
    """懒加载 RapidOCR；失败（未安装依赖）则保持 None"""
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR

            _ocr_engine = RapidOCR()
            logger.info("[Vision] RapidOCR 引擎已加载")
        except Exception as e:
            logger.warning(f"[Vision] OCR 加载失败（文字提取不可用）: {e}")
            _ocr_engine = False  # 标记失败
    return _ocr_engine if _ocr_engine else None


def _clip_classify_sync(
    image_bytes: bytes, model_path: str = "models/clip-vit-base-patch32"
) -> Tuple[str, float]:
    """CLIP 多标签分类（同步，由 to_thread 包裹）"""
    model, processor = _load_clip(model_path)
    if model is None or processor is None:
        return "其他", 0.0

    import torch

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    texts = [t for labels in _CLIP_CATEGORIES.values() for t in labels]
    inputs = processor(text=texts, images=image, return_tensors="pt", padding=True)
    with torch.no_grad():
        outputs = model(**inputs)
        probs = outputs.logits_per_image.softmax(dim=1)[0]  # (n_texts,)

    # 聚合每个类别的最大概率
    idx = 0
    best_cat, best_conf = "其他", 0.0
    for cat, labels in _CLIP_CATEGORIES.items():
        conf = max(float(probs[idx + j]) for j in range(len(labels)))
        idx += len(labels)
        if conf > best_conf:
            best_cat, best_conf = cat, conf
    return best_cat, best_conf


def _ocr_sync(image_bytes: bytes) -> str:
    """OCR 提取图片文字（同步，由 to_thread 包裹）"""
    engine = _load_ocr()
    if engine is None:
        return ""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img)
        result, _ = engine(arr)
        if not result:
            return ""
        # result: [[box, text, score], ...]
        return "".join(str(item[1]) for item in result)
    except Exception as e:
        logger.debug(f"[Vision] OCR 识别失败: {e}")
        return ""


class LocalVision:
    """本地预筛器：CLIP + OCR"""

    def __init__(
        self,
        clip_enabled: bool = True,
        ocr_enabled: bool = True,
        clip_model_path: str = "models/clip-vit-base-patch32",
    ):
        self._clip_enabled = clip_enabled
        self._ocr_enabled = ocr_enabled
        self._clip_model_path = clip_model_path

    @property
    def is_ready(self) -> bool:
        return self._clip_enabled or self._ocr_enabled

    async def analyze(self, image_bytes: bytes) -> LocalMeta:
        """并行执行 CLIP 分类与 OCR"""
        tasks = []
        if self._clip_enabled:
            tasks.append(
                asyncio.to_thread(_clip_classify_sync, image_bytes, self._clip_model_path)
            )
        if self._ocr_enabled:
            tasks.append(asyncio.to_thread(_ocr_sync, image_bytes))

        clip_result: Optional[Tuple[str, float]] = None
        ocr_text: str = ""
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            if self._clip_enabled:
                r = results[0]
                if isinstance(r, Exception):
                    logger.debug(f"[Vision] CLIP 预筛异常: {r}")
                elif r is not None:
                    clip_result = r
            if self._ocr_enabled:
                r = results[-1]
                if isinstance(r, Exception):
                    logger.debug(f"[Vision] OCR 预筛异常: {r}")
                elif isinstance(r, str):
                    ocr_text = r.strip()

        cat, conf = clip_result or ("其他", 0.0)
        return LocalMeta(
            clip_category=cat,
            clip_conf=conf,
            ocr_text=ocr_text,
            has_text=bool(ocr_text),
        )
