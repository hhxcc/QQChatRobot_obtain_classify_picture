"""YOLO 图片分类测试脚本 - 无需训练即可测试推理管线

使用预训练的 YOLOv8n-cls (ImageNet 权重) 做快速测试。
正式使用时，请用 train_model.py 训练专门的动漫二分类模型。
"""

import io
import sys
from pathlib import Path

import torch
from PIL import Image
from ultralytics import YOLO


def load_model(model_path: str = "yolov8n-cls.pt", use_gpu: bool = True):
    """加载 YOLOv8 分类模型"""
    device = "cuda" if use_gpu and torch.cuda.is_available() else "cpu"
    print(f"设备: {device}")

    if Path(model_path).exists():
        print(f"加载本地模型: {model_path}")
        model = YOLO(model_path)
    else:
        print(f"下载预训练模型: {model_path}")
        model = YOLO(model_path)

    model.to(device)
    return model


def classify_single(model, image_path: str):
    """分类单张图片"""
    img = Image.open(image_path).convert("RGB")
    results = model(img, verbose=False)

    probs = results[0].probs
    if probs is None:
        print("未获取到分类结果")
        return

    top5_idx = probs.top5
    top5_conf = probs.top5conf

    print(f"\n图片: {image_path}")
    print(f"Top-5 预测:")
    for i, (idx, conf) in enumerate(zip(top5_idx, top5_conf)):
        label = model.names[int(idx)]
        print(f"  {i+1}. {label}: {conf:.2%}")


def classify_bytes(model, img_bytes: bytes):
    """分类字节数据（模拟QQ下载的图片）"""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    results = model(img, verbose=False)

    probs = results[0].probs
    top1_idx = probs.top1
    top1_conf = probs.top1conf.item()
    label = model.names[int(top1_idx)]

    return label, top1_conf


def test_pipeline():
    """测试完整推理管线"""
    print("=" * 50)
    print("  YOLOv8 推理管线测试")
    print("=" * 50)

    # 优先使用本地模型，不存在则尝试下载
    local_model = Path("models/yolov8n-cls.pt")
    if local_model.exists():
        model = load_model(str(local_model))
    else:
        model = load_model()

    # 检查命令行参数
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        if not Path(image_path).exists():
            print(f"文件不存在: {image_path}")
            return
        classify_single(model, image_path)
    else:
        print("\n用法: python test_classifier.py <图片路径>")
        print("示例: python test_classifier.py test_anime.jpg")

        # 用一张纯色图做一次快速推理测试
        print("\n正在用测试图验证推理管线...")
        test_img = Image.new("RGB", (640, 640), color=(128, 128, 128))
        results = model(test_img, verbose=False)
        print(f"✅ 推理管线正常 (延迟: {results[0].speed['inference']:.1f}ms)")


if __name__ == "__main__":
    test_pipeline()
