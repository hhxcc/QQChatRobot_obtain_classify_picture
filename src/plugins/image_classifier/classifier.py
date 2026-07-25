"""YOLOv8 动漫图片分类器

支持两种模式:
1. 自定义训练模型 (2类: anime/real) — 直接判断
2. ImageNet 预训练模型 (1000类) — 使用启发式规则判断

训练自定义模型: python train_model.py
"""

import io
from pathlib import Path
from typing import Optional, Tuple

import torch
from PIL import Image
from ultralytics import YOLO
from nonebot import logger

from .config import Config


# 全局模型实例
_model: Optional[YOLO] = None
_device: Optional[torch.device] = None
_is_custom_model: bool = False  # 是否为自定义训练的动漫二分类模型

# ImageNet 中与"动漫/绘画/卡通"弱相关的类别 (用于启发式判断)
_ANIME_RELATED_CLASSES = {
    "comic book", "cartoon", "mask", "jigsaw puzzle",
    "website", "menu", "envelope", "shield",
}


async def init_classifier(config: Config) -> None:
    """初始化YOLOv8分类模型"""
    global _model, _device, _is_custom_model

    _device = torch.device("cuda" if config.use_gpu and torch.cuda.is_available() else "cpu")
    logger.info(f"YOLO 使用设备: {_device}")

    model_path = Path(config.yolo_model_path)

    if model_path.exists():
        logger.info(f"加载本地模型: {model_path}")
        _model = YOLO(str(model_path))
    else:
        logger.info("本地模型不存在，下载预训练 YOLOv8n-cls...")
        _model = YOLO("yolov8n-cls.pt")

    _model.to(_device)

    # 检测模型类型: 是自定义二分类(2类) 还是 ImageNet预训练(1000类)
    try:
        num_classes = len(_model.names)
        _is_custom_model = (num_classes == 2)
        logger.info(
            f"模型已加载: {num_classes} 类, "
            f"类型: {'自定义动漫二分类' if _is_custom_model else 'ImageNet预训练(启发式模式)'}"
        )
    except Exception:
        _is_custom_model = False
        logger.warning("无法检测模型类别数，使用启发式模式")

    logger.info("YOLO 分类器初始化完成")


async def classify_image(img_bytes: bytes, config: Config) -> Tuple[bool, float]:
    """判断图片是否为二次元风格
    
    Returns:
        (is_anime, confidence)
    """
    if _model is None:
        raise RuntimeError("分类器未初始化")

    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    results = _model(img, verbose=False)
    probs = results[0].probs

    if probs is None:
        logger.warning("YOLO 未返回分类概率")
        return False, 0.0

    if _is_custom_model:
        # === 自定义二分类模型: YOLO 字母序 → class 0 = anime, class 1 = real ===
        anime_conf = probs.data[0].item()  # class 0 = anime
        real_conf = probs.data[1].item()   # class 1 = real
        is_anime = anime_conf >= config.anime_threshold
        verdict = "🎨 二次元" if is_anime else "📷 真实照片"
        logger.info(f"分类结果: {verdict} | anime={anime_conf:.2%} real={real_conf:.2%}")
    else:
        # === ImageNet 预训练模型: 启发式判断 ===
        top5_names = [_model.names[int(i)] for i in probs.top5]
        top5_confs = probs.top5conf.tolist()

        # 策略: 如果 top-1 类别与绘画/卡通相关，判定为动漫
        anime_related_hits = sum(
            1 for name in top5_names
            if any(keyword in name.lower() for keyword in ["cartoon", "comic", "animated"])
        )
        top1_conf = top5_confs[0]

        if anime_related_hits > 0:
            anime_conf = max(top5_confs[i] for i, name in enumerate(top5_names)
                           if any(k in name.lower() for k in ["cartoon", "comic", "animated"]))
            is_anime = anime_conf >= config.anime_threshold
        else:
            # 没有命中关键词 → 保守判定为非动漫
            anime_conf = 0.0
            is_anime = False

        logger.info(
            f"分类结果 (ImageNet): Top-1={top5_names[0]}({top5_confs[0]:.2%}) → {'🎨 二次元' if is_anime else '📷 真实照片'}"
        )

    return is_anime, anime_conf


def get_model_info() -> dict:
    """获取模型信息"""
    if _model is None:
        return {"status": "未加载"}
    return {
        "status": "已加载",
        "device": str(_device),
        "num_classes": len(_model.names),
        "is_custom": _is_custom_model,
    }
