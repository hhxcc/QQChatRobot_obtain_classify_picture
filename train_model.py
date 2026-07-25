"""YOLOv8 动漫二分类模型训练脚本

使用说明:
    1. 准备数据集，目录结构如下:
       dataset/
       ├── train/
       │   ├── anime/     # 二次元图片
       │   └── real/      # 真实照片
       └── val/
           ├── anime/
           └── real/

    2. 运行: python train_model.py

数据集来源建议:
    - 二次元: Danbooru2021 子集, safebooru 等
    - 真实照片: COCO, OpenImages, 或自采集

训练完成后模型保存到 models/yolov8n-cls.pt
"""

import os
from pathlib import Path
from ultralytics import YOLO
import torch


def main():
    # ========== 配置 ==========
    DATASET_DIR = Path("dataset")  # 数据集目录
    MODEL_OUTPUT = Path("models/yolov8n-cls.pt")
    IMG_SIZE = 640
    BATCH_SIZE = 8   # RTX 5070 Laptop 8GB: 8 安全，16 可能 OOM
    EPOCHS = 50
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    # ==========================

    print(f"使用设备: {DEVICE}")
    print(f"数据集目录: {DATASET_DIR.absolute()}")

    # 检查数据集
    if not DATASET_DIR.exists():
        print(f"\n❌ 数据集目录不存在: {DATASET_DIR}")
        print("\n请先准备数据集，目录结构:")
        print("  dataset/")
        print("  ├── train/")
        print("  │   ├── anime/    # 二次元图片")
        print("  │   └── real/     # 真实照片")
        print("  └── val/")
        print("      ├── anime/")
        print("      └── real/")

        # 自动创建目录结构
        print("\n正在创建空目录结构...")
        for split in ["train", "val"]:
            for cls in ["anime", "real"]:
                (DATASET_DIR / split / cls).mkdir(parents=True, exist_ok=True)
        print("✅ 目录结构已创建，请放入图片后重新运行")
        return

    # 统计数据集
    for split in ["train", "val"]:
        for cls in ["anime", "real"]:
            p = DATASET_DIR / split / cls
            if p.exists():
                count = len(list(p.glob("*")))
                print(f"  {split}/{cls}: {count} 张")

    # 验证是否有数据
    train_anime = len(list((DATASET_DIR / "train" / "anime").glob("*")))
    train_real = len(list((DATASET_DIR / "train" / "real").glob("*")))
    if train_anime == 0 or train_real == 0:
        print("\n❌ 训练集为空，请放入图片后重试")
        return

    # ========== 开始训练 ==========
    print(f"\n{'='*50}")
    print("开始训练 YOLOv8n-cls 动漫二分类模型")
    print(f"{'='*50}")

    # 检查是否可以续训
    last_pt = Path("runs/classify/anime_classifier/weights/last.pt")
    if last_pt.exists():
        print(f"\n发现上次训练权重，续训中...")
        model = YOLO(str(last_pt))
    else:
        model = YOLO("yolov8n-cls.pt")

    # 训练
    results = model.train(
        data=str(DATASET_DIR),
        epochs=EPOCHS,
        imgsz=IMG_SIZE,
        batch=BATCH_SIZE,
        device=DEVICE,
        workers=2,          # 减少 worker 降低内存压力
        pretrained=True,
        optimizer="auto",
        lr0=0.01,
        lrf=0.01,
        momentum=0.937,
        weight_decay=0.0005,
        warmup_epochs=3,
        cos_lr=True,
        close_mosaic=10,
        name="anime_classifier",
        exist_ok=True,
        resume=last_pt.exists(),  # 自动续训
    )

    # 导出最佳模型
    best_pt = Path("runs/classify/anime_classifier/weights/best.pt")
    if best_pt.exists():
        import shutil
        shutil.copy(best_pt, MODEL_OUTPUT)
        print(f"\n✅ 模型已保存到: {MODEL_OUTPUT}")

    # 验证
    print(f"\n{'='*50}")
    print("在验证集上评估模型...")
    metrics = model.val(data=str(DATASET_DIR), split="val")
    print(f"Top-1 准确率: {metrics.top1:.2%}")
    print(f"Top-5 准确率: {metrics.top5:.2%}")


if __name__ == "__main__":
    main()
