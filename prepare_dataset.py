"""数据集准备脚本

功能:
1. 将 input/ 中的二次元图片整理到 dataset/train/anime/ 和 dataset/val/anime/
2. 下载 COCO 2017 验证集作为真实照片 → dataset/train/real/ 和 dataset/val/real/
3. 自动按 80/20 划分训练集和验证集

使用方法:
    python prepare_dataset.py
"""

import os
import sys
import random
import shutil
import zipfile
import urllib.request
from pathlib import Path

# ============ 配置 ============
ANIME_DIR = Path("input")                     # 你的二次元图片目录
DATASET_DIR = Path("dataset")                 # 输出数据集目录
REAL_COUNT = 2500                             # 需要的真实照片数量 (平衡数据集)
TRAIN_SPLIT = 0.8                             # 训练集比例
COCO_URL = "http://images.cocodataset.org/zips/val2017.zip"  # COCO 2017 验证集
# =============================

RANDOM_SEED = 42
random.seed(RANDOM_SEED)


def download_coco(output_dir: Path) -> bool:
    """下载 COCO 2017 验证集（5000张真实照片，~1GB）"""
    zip_path = output_dir / "val2017.zip"
    extract_path = output_dir / "val2017"

    if extract_path.exists() and len(list(extract_path.glob("*.jpg"))) > 100:
        print(f"  COCO 已存在: {extract_path} ({len(list(extract_path.glob('*.jpg')))} 张)")
        return True

    if not zip_path.exists():
        print(f"  正在下载 COCO 2017 验证集 (~1GB)...")
        print(f"  URL: {COCO_URL}")
        try:
            urllib.request.urlretrieve(COCO_URL, zip_path,
                                       lambda n, bs, size: print(
                                           f"    进度: {n*bs//1024//1024}MB / {size//1024//1024}MB",
                                           end="\r") if n % 10 == 0 else None)
            print()
        except Exception as e:
            print(f"  ❌ 下载失败: {e}")
            print("  请手动下载: http://images.cocodataset.org/zips/val2017.zip")
            print(f"  放到: {zip_path}")
            return False

    # 解压
    print(f"  正在解压...")
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(output_dir)
    print(f"  ✅ COCO 解压完成: {extract_path}")
    return True


def prepare_anime(anime_dir: Path, train_dir: Path, val_dir: Path):
    """整理二次元图片到训练/验证集"""
    anime_dir = anime_dir.resolve()
    images = []
    for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp", "*.gif"]:
        images.extend(anime_dir.glob(ext))
        images.extend(anime_dir.rglob(ext))  # 递归搜索子目录

    # 去重（按文件名）
    seen = set()
    unique_images = []
    for img in images:
        if img.name.lower() not in seen:
            seen.add(img.name.lower())
            unique_images.append(img)

    random.shuffle(unique_images)
    split_idx = int(len(unique_images) * TRAIN_SPLIT)
    train_imgs = unique_images[:split_idx]
    val_imgs = unique_images[split_idx:]

    train_dir.mkdir(parents=True, exist_ok=True)
    val_dir.mkdir(parents=True, exist_ok=True)

    for img in train_imgs:
        shutil.copy2(img, train_dir / img.name)
    for img in val_imgs:
        shutil.copy2(img, val_dir / img.name)

    print(f"  动漫图: train={len(train_imgs)} val={len(val_imgs)}")
    return len(train_imgs), len(val_imgs)


def prepare_real(coco_dir: Path, train_dir: Path, val_dir: Path, max_count: int):
    """从 COCO 中选取真实照片"""
    images = list(coco_dir.glob("*.jpg"))
    random.shuffle(images)
    images = images[:max_count]

    split_idx = int(len(images) * TRAIN_SPLIT)
    train_imgs = images[:split_idx]
    val_imgs = images[split_idx:]

    train_dir.mkdir(parents=True, exist_ok=True)
    val_dir.mkdir(parents=True, exist_ok=True)

    for img in train_imgs:
        shutil.copy2(img, train_dir / img.name)
    for img in val_imgs:
        shutil.copy2(img, val_dir / img.name)

    print(f"  真实照片: train={len(train_imgs)} val={len(val_imgs)}")
    return len(train_imgs), len(val_imgs)


def main():
    print("=" * 55)
    print("  数据集准备 - 动漫 vs 真实 二分类")
    print("=" * 55)

    # 1. 下载 COCO（真实照片源）
    print("\n[1/3] 获取真实照片数据集...")
    coco_success = download_coco(DATASET_DIR)
    if not coco_success:
        print("\n缺少 COCO 数据集，仅整理动漫图片。")
        print("请手动下载后重新运行。")
        choice = input("是否仅整理动漫图片？(y/n): ")
        if choice.lower() != 'y':
            return

    # 2. 整理动漫图片
    print("\n[2/3] 整理二次元图片...")
    if not ANIME_DIR.exists():
        print(f"  ❌ 目录不存在: {ANIME_DIR}")
        return
    a_train, a_val = prepare_anime(
        ANIME_DIR,
        DATASET_DIR / "train" / "anime",
        DATASET_DIR / "val" / "anime",
    )

    # 3. 整理真实照片
    print("\n[3/3] 整理真实照片...")
    if coco_success:
        r_train, r_val = prepare_real(
            DATASET_DIR / "val2017",
            DATASET_DIR / "train" / "real",
            DATASET_DIR / "val" / "real",
            REAL_COUNT,
        )
    else:
        r_train = r_val = 0

    # ======== 汇总 ========
    print("\n" + "=" * 55)
    print("  数据集准备完成！")
    print("=" * 55)
    print(f"""
    目录结构:
      dataset/
      ├── train/
      │   ├── anime/  {a_train} 张
      │   └── real/   {r_train} 张
      └── val/
          ├── anime/  {a_val} 张
          └── real/   {r_val} 张

    总计: {a_train + a_val + r_train + r_val} 张

    下一步: python train_model.py
    """)


if __name__ == "__main__":
    main()
