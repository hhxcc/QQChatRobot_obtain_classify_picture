"""图片存储模块"""

import hashlib
from datetime import datetime
from pathlib import Path

from .config import Config


def save_image(
    img_bytes: bytes,
    group_id: int,
    file_id: str,
    confidence: float,
    config: Config,
) -> str:
    """保存分类后的二次元图片
    
    Args:
        img_bytes: 图片字节数据
        group_id: 群号
        file_id: QQ图片file_id
        confidence: 分类置信度
        config: 插件配置
    
    Returns:
        保存路径
    """
    # 按 群号/日期 组织目录
    today = datetime.now().strftime("%Y-%m-%d")
    save_dir = Path(config.image_save_dir) / str(group_id) / today
    save_dir.mkdir(parents=True, exist_ok=True)

    # 生成唯一文件名 (MD5前8位 + 置信度)
    img_hash = hashlib.md5(img_bytes).hexdigest()
    anime_pct = int(confidence * 100)
    filename = f"{img_hash[:8]}_{anime_pct}p.jpg"

    # 保存图片
    img_path = save_dir / filename
    with open(img_path, "wb") as f:
        f.write(img_bytes)

    return str(img_path)
