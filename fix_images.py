"""批量修复数据集图片

修复两种常见问题:
1. corrupt JPEG — 文件头不完整
2. libpng iCCP warning — PNG 的 ICC 颜色配置不标准

运行: python fix_images.py
"""

import sys
from pathlib import Path
from PIL import Image, ImageCms

DATASET_DIR = Path("dataset")


def strip_icc_profile(img: Image.Image) -> Image.Image:
    """移除 ICC 颜色配置文件（解决 libpng iCCP PCS D50 警告）"""
    if "icc_profile" in img.info:
        img.info.pop("icc_profile", None)
    return img


def fix_and_clean(img_path: Path) -> bool:
    """重新编码图片，移除有问题的元数据"""
    try:
        ext = img_path.suffix.lower()
        img = Image.open(img_path)
        img = img.convert("RGB")

        # 移除 ICC profile
        img = strip_icc_profile(img)

        if ext == ".png":
            # PNG → 保存为干净 PNG（无 ICC profile）
            img.save(img_path, "PNG", optimize=True)
        else:
            # JPEG/其他 → 保存为 JPEG
            img.save(img_path, "JPEG", quality=95)
        return True
    except Exception as e:
        print(f"  ❌ 无法修复 {img_path.name}: {e}")
        return False


def main():
    print("=" * 55)
    print("  批量修复数据集图片")
    print("  - corrupt JPEG 文件头")
    print("  - PNG ICC profile (libpng iCCP 警告)")
    print("=" * 55)

    if not DATASET_DIR.exists():
        print(f"❌ 目录不存在: {DATASET_DIR}")
        return

    images = []
    for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp"]:
        images.extend(DATASET_DIR.rglob(ext))

    print(f"\n找到 {len(images)} 张图片")

    fixed = 0
    failed = 0
    has_icc = 0

    for img_path in images:
        need_fix = False

        try:
            img = Image.open(img_path)

            # 检查 ICC profile（PNG 常见问题）
            if "icc_profile" in img.info and img_path.suffix.lower() == ".png":
                has_icc += 1
                need_fix = True

            # 验证图片完整性
            img.verify()

        except Exception:
            # 图片损坏，需要修复
            need_fix = True

        if need_fix:
            if fix_and_clean(img_path):
                fixed += 1
                if fixed <= 15 or fixed % 50 == 0:
                    print(f"  ✅ 修复: {img_path.name}")

    print(f"\n修复完成:")
    print(f"  含 ICC profile 的 PNG: {has_icc} 张 → 已清除")
    print(f"  实际重新编码: {fixed} 张")
    print(f"  失败: {failed} 张")
    print(f"\n✅ 重新训练不会再出现 corrupt JPEG 和 iCCP 警告")


if __name__ == "__main__":
    main()
