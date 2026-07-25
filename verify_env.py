"""环境验证脚本 - 检查所有依赖是否正确安装"""
import sys

def main():
    print("=" * 50)
    print("  环境验证 - QQ Chat Robot Image Classifier")
    print("=" * 50)
    
    # 1. Python 版本
    print(f"\n[1] Python 版本: {sys.version}")
    
    # 2. PyTorch + CUDA
    try:
        import torch
        print(f"[2] PyTorch: {torch.__version__}")
        print(f"    CUDA 可用: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"    GPU: {torch.cuda.get_device_name(0)}")
            print(f"    GPU 数量: {torch.cuda.device_count()}")
            print(f"    CUDA 版本: {torch.version.cuda}")
    except ImportError as e:
        print(f"[2] PyTorch: ❌ 未安装 - {e}")

    # 3. ultralytics (YOLOv8)
    try:
        import ultralytics
        print(f"[3] ultralytics (YOLOv8): {ultralytics.__version__}")
    except ImportError as e:
        print(f"[3] ultralytics: ❌ 未安装 - {e}")

    # 4. NoneBot2
    try:
        import nonebot
        print(f"[4] NoneBot2: {nonebot.__version__}")
    except ImportError as e:
        print(f"[4] NoneBot2: ❌ 未安装 - {e}")

    # 5. OneBot 适配器
    try:
        import nonebot.adapters.onebot.v11
        print(f"[5] nonebot-adapter-onebot: ✅")
    except ImportError as e:
        print(f"[5] nonebot-adapter-onebot: ❌ - {e}")

    # 6. OpenCV
    try:
        import cv2
        print(f"[6] OpenCV: {cv2.__version__}")
    except ImportError as e:
        print(f"[6] OpenCV: ❌ - {e}")

    # 7. httpx, aiohttp
    try:
        import httpx, aiohttp, aiofiles
        print(f"[7] httpx: {httpx.__version__}")
        print(f"    aiohttp: {aiohttp.__version__}")
    except ImportError as e:
        print(f"[7] HTTP客户端: ❌ - {e}")

    # 8. Pillow
    try:
        from PIL import Image
        import PIL
        print(f"[8] Pillow: {PIL.__version__}")
    except ImportError as e:
        print(f"[8] Pillow: ❌ - {e}")

    # 9. 其他核心库
    try:
        import pydantic, loguru, dotenv
        print(f"[9] pydantic: ✅, loguru: ✅, python-dotenv: ✅")
    except ImportError as e:
        print(f"[9] 核心库: ❌ - {e}")

    print("\n" + "=" * 50)
    print("  验证完成！")
    print("=" * 50)

if __name__ == "__main__":
    main()
