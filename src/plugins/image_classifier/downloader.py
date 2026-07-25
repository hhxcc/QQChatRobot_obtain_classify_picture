"""图片下载模块"""

import httpx
from nonebot import logger


async def download_image(url: str, timeout: int = 30) -> bytes:
    """从URL下载图片，返回原始字节数据
    
    Args:
        url: 图片URL
        timeout: 超时秒数
    
    Returns:
        图片字节数据
    
    Raises:
        httpx.HTTPError: 下载失败
    """
    headers = {
        "User-Agent": "QQBot-ImageClassifier/1.0",
        "Accept": "image/*",
    }

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            logger.warning(f"非图片响应: {content_type}, url={url[:80]}...")
            # 仍然尝试保存，可能是QQ内部URL

        return response.content
