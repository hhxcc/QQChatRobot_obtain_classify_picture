# QQ 群聊动漫图片采集分类机器人

自动监听 QQ 群消息，下载图片并用 YOLOv8 分类保存二次元图片。支持无人值守 7×24 运行。

## 架构

```
QQ群 → NapCatQQ (QQ协议) ──WS──→ NoneBot2 → YOLOv8-cls → 本地存储
              │                        │
              ├── 自动快速登录          ├── watchdog 心跳保活
              └── 密码回退登录          └── bot_offline 检测 + 自动重启
```

## 环境要求

- Windows 10/11
- Python 3.10+
- NVIDIA GPU (CUDA 12.0+) / 或 CPU（修改 `.env` 中 `USE_GPU=false`）
- QQ 小号

## 快速开始

### 1. 配置 NapCatQQ 自动登录

编辑 `tools\NapCatQQ\config\webui.json`：

```json
"autoLoginAccount": "你的QQ号"
```

编辑 `tools\NapCatQQ\launcher-user.bat`，添加回退密码（登录态过期时自动用密码重新登录）：


方式一
```bat
set ACCOUNT=3412571395
set NAPCAT_QUICK_PASSWORD=你的QQ密码
```
方式二
```bat
set ACCOUNT=3412571395
set NAPCAT_QUICK_PASSWORD_MD5=你的QQ密码的MD5值
```

> MD5 生成方式（PowerShell）：
> ```powershell
> [System.BitConverter]::ToString([System.Security.Cryptography.MD5]::Create().ComputeHash([System.Text.Encoding]::UTF8.GetBytes("你的密码"))).Replace("-","").ToLower()
> ```

### 2. 配置 .env

编辑 `.env` 文件：

```env
# 要监听的群号
TARGET_GROUPS=[737130031, 1079534054]
# OneBot 鉴权 Token（需与 NapCatQQ OneBot 配置一致）
ONEBOT_ACCESS_TOKEN=RR6eNjgPDlT2fFeO
# 图片保存目录（支持绝对路径如 D:\QQBot_Images）
IMAGE_SAVE_DIR=data/images
```

### 3. 一键启动（守护模式）

```bash
# 双击运行，自动启动 NapCatQQ + Bot，崩溃自动重启
start_bot.bat
```

- ✅ 自动检测并启动 NapCatQQ（QQ 客户端）
- ✅ 自动等待 WebSocket 连接就绪
- ✅ Bot 退出后 5 秒自动重启
- ✅ QQ 进程崩溃后自动重新拉起
- ✅ QQ 登录失效时自动检测并重启

> 手动启动（调试用）：`.venv\Scripts\python.exe bot.py`

## 连接架构

NapCatQQ 使用**反向 WebSocket** 模式连接到 NoneBot2：

| 组件 | 角色 | 地址 |
|------|------|------|
| NoneBot2 | WebSocket 服务端 | `ws://127.0.0.1:8080/onebot/v11/ws` |
| NapCatQQ | WebSocket 客户端 | 主动连接到上述地址 |

NapCatQQ OneBot 配置位于 `tools\NapCatQQ\config\onebot11_<QQ号>.json`

## 防掉线机制

| 层级 | 机制 | 说明 |
|------|------|------|
| QQ 登录层 | 自动快速登录 + 密码回退 | 缓存凭据失效后自动用密码登录 |
| WebSocket | 心跳 15s / 重连 5s | NapCatQQ OneBot 配置 |
| 应用层 | watchdog 插件 | 每 5 分钟 API 心跳 + `bot_offline` 事件监听 |
| 进程层 | 守护脚本 | `start_bot.bat` 监控 QQ.exe 和 bot.py |

### 自动恢复流程

```
QQ 登录失效
  ├─ NapCatQQ 尝试密码回退登录
  ├─ 失败 → 发送 bot_offline 通知
  ├─ watchdog 捕获 → 写入日志 → os._exit(1)
  └─ start_bot.bat 检测退出 → 5 秒后重启 NapCatQQ + bot.py
```

### 自测命令

在 QQ 群中发送 `.test_offline` 可模拟登录失效，验证看门狗是否能正常检测并触发重启。

## LLM 聊天功能

内置 LLM 插件，支持群聊自动回复。基于 DeepSeek API，可注入人格提示词和知识库。

```
群消息 → 场景检测 → 知识库检索 → DeepSeek API → 回复
```

### 初始化

```bash
# 1. 创建人格提示词
copy 人格提示词.example.txt 人格提示词.txt
# 编辑 人格提示词.txt 写入你的角色设定

# 2. 创建知识库 (可选)
mkdir knowledge
# 参考 knowledge.example/ 目录结构
```

### 配置 .env

```env
DEEPSEEK_API_KEY=你的APIKey
LLM_SYSTEM_PROMPT_FILE=人格提示词.txt
LLM_TARGET_GROUPS=[群号1]
```

> 将 `LLM_TARGET_GROUPS` 设为 `[]` 可关闭 LLM 聊天功能。

## 训练动漫分类模型

```bash
# 1. 准备数据集
#    动漫图 → dataset/train/anime/
#    真实照片 → dataset/train/real/
#    验证集 → dataset/val/

# 2. 开始训练
.venv\Scripts\python.exe train_model.py
```

## 项目结构

```
├── bot.py                    # 机器人入口
├── start_bot.bat             # 守护进程启动脚本（推荐）
├── .env                      # 配置文件
├── pyproject.toml            # 项目依赖与 NoneBot2 配置
├── train_model.py            # YOLO 训练脚本
├── test_classifier.py        # 分类器测试
├── download_model.py         # 模型下载工具
├── verify_env.py             # 环境验证
├── models/                   # YOLO 权重
├── data/images/              # 保存的图片（{群号}/{日期}/）
├── src/plugins/
│   ├── watchdog.py           # 看门狗：心跳保活 + 登录失效检测
│   └── image_classifier/
│       ├── __init__.py       # 插件入口
│       ├── config.py         # 配置模型
│       ├── handler.py        # 消息处理
│       ├── downloader.py     # 图片下载
│       ├── classifier.py     # YOLO 推理
│       └── storage.py        # 文件存储
└── tools/NapCatQQ/           # NapCatQQ 客户端
    ├── launcher-user.bat     # 启动脚本（含密码回退配置）
    └── config/
        ├── webui.json        # WebUI 配置（含自动登录）
        ├── napcat.json       # NapCat 全局配置
        └── onebot11_*.json   # 各 QQ 号的 OneBot 连接配置
```

## 配置参考

### launcher-user.bat（回退密码）

```bat
set ACCOUNT=3412571395
set NAPCAT_QUICK_PASSWORD_MD5=bb310a776d9a45e92a4ea250b79e2e93
```

> 登录优先级：缓存凭据 → 密码回退 → 二维码扫码

### webui.json（自动登录）

```json
{
  "autoLoginAccount": "3412571395",
  "host": "::",
  "port": 6099
}
```

### onebot11_<QQ号>.json（OneBot 连接）

```json
{
  "network": {
    "websocketClients": [{
      "enable": true,
      "url": "ws://127.0.0.1:8080/onebot/v11/ws",
      "token": "RR6eNjgPDlT2fFeO",
      "heartInterval": 15000,
      "reconnectInterval": 5000
    }]
  }
}
```

## 常见问题

### Q: 启动后闪退？
A: 确保 `.env` 中的 `ONEBOT_ACCESS_TOKEN` 与 NapCatQQ OneBot 配置中的 token 一致。

### Q: 长时间运行掉线？
A: 已内置四层防护：自动登录 + 密码回退 + watchdog 检测 + 守护进程重启。`bot_offline` 事件会被 watchdog 自动捕获并触发整条链路重启。

### Q: QQ 登录失效后没有自动恢复？
A: 确认 `launcher-user.bat` 中已配置 `ACCOUNT` 和 `NAPCAT_QUICK_PASSWORD_MD5`。可在群内发送 `.test_offline` 测试看门狗是否正常工作。

### Q: 图片没有被分类？
A: 需运行 `train_model.py` 训练专门的动漫二分类模型。默认的 ImageNet 预训练模型准确率有限。
