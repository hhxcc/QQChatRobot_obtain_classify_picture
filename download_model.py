"""通过镜像下载 YOLOv8 模型权重

由于网络限制无法直连 GitHub，尝试多个镜像源下载。
"""

import sys
from pathlib import Path

# 模型下载 URL 列表（按优先级）
MODEL_URLS = [
    # 直接下载
    "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n-cls.pt",
    # ghproxy 镜像
    "https://ghproxy.net/https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n-cls.pt",
    # gh-proxy 镜像
    "https://gh-proxy.com/https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n-cls.pt",
    # gh.ddlc 镜像
    "https://gh.ddlc.top/https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n-cls.pt",
]

SAVE_PATH = Path("models/yolov8n-cls.pt")


def download_with_mirror(url: str) -> bool:
    """尝试从指定 URL 下载模型"""
    import urllib.request
    import urllib.error

    print(f"  尝试: {url[:60]}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            if len(data) < 100000:  # 模型至少 100KB
                print(f"    ❌ 文件太小 ({len(data)} bytes)，可能是错误页面")
                return False
            SAVE_PATH.write_bytes(data)
            print(f"    ✅ 下载成功! ({len(data) / 1024 / 1024:.1f} MB)")
            return True
    except urllib.error.URLError as e:
        print(f"    ❌ 失败: {e.reason}")
        return False
    except Exception as e:
        print(f"    ❌ 失败: {e}")
        return False


def main():
    print("下载 YOLOv8n-cls 模型权重...")
    print(f"保存路径: {SAVE_PATH}\n")

    for url in MODEL_URLS:
        if download_with_mirror(url):
            print(f"\n✅ 模型已保存到: {SAVE_PATH}")
            return 0

    print("\n❌ 所有镜像均下载失败")
    print("\n请手动下载模型:")
    print("  1. 使用 VPN/代理访问:")
    print("     https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n-cls.pt")
    print("  2. 将下载的文件放到: models/yolov8n-cls.pt")
    return 1


if __name__ == "__main__":
    sys.exit(main())
