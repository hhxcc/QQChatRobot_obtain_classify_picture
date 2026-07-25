# QQ 群聊动漫图片采集分类机器人

自动监听 QQ 群消息，下载图片并用 YOLOv8 分类保存二次元图片。支持无人值守 7×24 运行。

## 架构

```
QQ群 → NapCatQQ (QQ协议) ──WS──→ NoneBot2 → YOLOv8-cls → 本地存储
              │                        │
              └── 自动快速登录          └── watchdog 心跳保活
```

## 环境要求

- Windows 10/11
- Python 3.10+
- QQ NT (9.9.26+) 已安装
- NVIDIA GPU (CUDA 12.0+) / 或 CPU (修改 .env 中 USE_GPU=false)
- QQ 小号

## 快速开始

### 1. 获取 NapCatQQ

从 [NapCatQQ Releases](https://github.com/NapNeko/NapCatQQ/releases) 下载 `NapCat.Shell.zip`（v4.18.13+），解压到 `tools/NapCatQQ/`。

```bash
# 目录结构应如下
tools/NapCatQQ/
├── launcher-user.bat
├── NapCatWinBootMain.exe
├── NapCatWinBootHook.dll
├── napcat.mjs
└── ...
```

> 电脑需已安装 QQ NT (9.9.26+)。双击 `launcher-user.bat` 可手动启动测试。

### 2. 创建配置文件

```bash
# 从模板创建
copy .env.example .env
```

编辑 `.env`，填入你的信息：

```env
SUPERUSERS=["你的QQ号"]
TARGET_GROUPS=[群号1, 群号2]
ONEBOT_ACCESS_TOKEN=你的Token
```

### 3. 配置 NapCatQQ OneBot

首次启动 NapCatQQ 后，打开 WebUI `http://127.0.0.1:6099`：

1. 扫码登录 QQ 小号
2. 网络配置 → 添加 WebSocket 客户端：
   - URL: `ws://127.0.0.1:8080/onebot/v11/ws`
   - Token: 与 `.env` 中 `ONEBOT_ACCESS_TOKEN` 一致
3. 在 `webui.json` 中设置 `autoLoginAccount` 实现自动登录

### 3. 一键启动（守护模式）

```bash
# 双击运行，自动启动 NapCatQQ + Bot，崩溃自动重启
start_bot.bat
```

- ✅ 自动检测并启动 NapCatQQ（QQ 客户端）
- ✅ 自动等待 WebSocket 连接就绪
- ✅ Bot 退出后 5 秒自动重启
- ✅ QQ 进程崩溃后自动重新拉起

> 手动启动（调试用）：`.venv\Scripts\python.exe bot.py`

## 连接架构

NapCatQQ 使用**反向 WebSocket** 模式连接到 NoneBot2：

| 组件 | 角色 | 地址 |
|------|------|------|
| NoneBot2 | WebSocket 服务端 | `ws://127.0.0.1:8080/onebot/v11/ws` |
| NapCatQQ | WebSocket 客户端 | 主动连接到上述地址 |

> NapCatQQ 的 OneBot 配置位于 `tools\NapCatQQ\config\onebot11_<QQ号>.json`

## 防掉线机制

| 层级 | 机制 | 说明 |
|------|------|------|
| WebSocket | 心跳 15s / 重连 5s | NapCatQQ OneBot 配置 |
| 应用层 | watchdog 插件 | 每 5 分钟 API 心跳检测 |
| 进程层 | 守护脚本 | `start_bot.bat` 监控 QQ.exe 和 bot.py |

## 训练动漫分类模型

预训练的 YOLOv8n-cls 是 ImageNet 1000 类模型，需训练自定义二分类：

```bash
# 1. 准备数据集
#    将动漫图放入 dataset/train/anime/
#    将真实照片放入 dataset/train/real/
#    验证集放入 dataset/val/

# 2. 开始训练
.venv\Scripts\python.exe train_model.py
```

训练完成后模型自动保存为 `models/yolov8n-cls.pt`。

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
├── data/images/              # 保存的图片 ({群号}/{日期}/)
├── src/plugins/
│   ├── watchdog.py           # 看门狗心跳保活插件
│   └── image_classifier/
│       ├── __init__.py       # 插件入口
│       ├── config.py         # 配置模型
│       ├── handler.py        # 消息处理
│       ├── downloader.py     # 图片下载
│       ├── classifier.py     # YOLO 推理
│       └── storage.py        # 文件存储
└── tools/NapCatQQ/           # NapCatQQ 客户端
    └── config/
        ├── webui.json        # WebUI 配置（含自动登录）
        ├── napcat.json       # NapCat 全局配置
        └── onebot11_*.json   # 各 QQ 号的 OneBot 连接配置
```

## 配置参考

### webui.json（NapCatQQ 自动登录）

```json
{
  "autoLoginAccount": "机器人账号",
  "host": "::",
  "port": 6099,
  "token": "自己的令牌"
}
```

### onebot11_<QQ号>.json（OneBot 连接）

```json
{
  "network": {
    "websocketClients": [{
      "enable": true,
      "url": "ws://127.0.0.1:8080/onebot/v11/ws",
      "token": "******",
      "heartInterval": 15000,
      "reconnectInterval": 5000
    }]
  }
}
```

## 常见问题

### Q: 启动后闪退？
A: 确保 `.env` 中的 `ONEBOT_ACCESS_TOKEN` 与 NapCatQQ OneBot 配置中的 token 一致。

### Q: 图片没有被分类？
A: 当前使用 ImageNet 预训练模型（启发式模式），准确率有限。需运行 `train_model.py` 训练专门的动漫二分类模型。

### Q: 长时间运行掉线？
A: 已内置三层防掉线机制：WebSocket 心跳、watchdog API 检测、守护进程自动重启。查看 NapCatQQ 日志排查具体原因。
