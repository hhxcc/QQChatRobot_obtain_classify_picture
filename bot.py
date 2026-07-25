#!/usr/bin/env python3
"""QQ群聊图片分类机器人 - 入口文件

使用方式:
    nb run
    或
    python bot.py
"""

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

# 初始化 NoneBot2
nonebot.init()

# 注册 OneBot v11 适配器
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

# 加载插件 (自动从 pyproject.toml 的 plugin_dirs 加载)
nonebot.load_plugins("src/plugins")

if __name__ == "__main__":
    nonebot.run()
