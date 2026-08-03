# QQ 群聊动漫图片采集分类机器人

自动监听 QQ 群消息，下载图片并用 YOLOv8 分类保存二次元图片。内置 LLM 聊天插件，支持 7×24 无人值守运行。

## 功能

| 模块 | 说明 |
|------|------|
| 🖼️ 图片分类 | YOLOv8 自定义模型，动漫/真实 二分类 |
| 💬 LLM 聊天 | DeepSeek API 驱动，支持人格注入和知识库检索 |
| 🛡️ 防掉线 | 四层防护：自动登录 + 密码回退 + watchdog 检测 + 进程守护 |

## 架构

```
QQ群 ──→ NapCatQQ ──WS──→ NoneBot2
                              ├── image_classifier → YOLOv8 → 本地存储
                              ├── llm_chat → DeepSeek API
                              └── watchdog → 心跳保活 + 掉线重启
```

## 环境要求

- Windows 10/11
- Python 3.10+
- QQ NT (9.9.26+) 已安装
- NVIDIA GPU (CUDA 12.0+) / CPU（`.env` 中 `USE_GPU=false`）
- QQ 小号

## 快速开始

### 1. 获取 NapCatQQ

从 [NapCatQQ Releases](https://github.com/NapNeko/NapCatQQ/releases) 下载 `NapCat.Shell.zip`，解压到 `tools/NapCatQQ/`。

```
tools/NapCatQQ/
├── launcher-user.bat    ← 启动脚本
├── NapCatWinBootMain.exe
├── napcat.mjs
└── ...
```

### 2. 创建配置

```bash
copy .env.example .env
```

编辑 `.env`，填入：

```env
SUPERUSERS=["你的QQ号"]
TARGET_GROUPS=[群号1, 群号2]
ONEBOT_ACCESS_TOKEN=自定义Token
```

### 3. 配置 NapCatQQ

首次启动后打开 WebUI `http://127.0.0.1:6099`：

1. 扫码登录 QQ 小号
2. 网络配置 → 添加 WebSocket 客户端
3. URL: `ws://127.0.0.1:8080/onebot/v11/ws`
4. Token: 与 `.env` 中 `ONEBOT_ACCESS_TOKEN` 一致
5. 在 `webui.json` 中设置 `autoLoginAccount` 实现自动登录

```json
{
  "network": {
    "websocketClients": [{
      "enable": true,
      "url": "ws://127.0.0.1:8080/onebot/v11/ws",
      "token": "与.env中的ONEBOT_ACCESS_TOKEN一致",
      "heartInterval": 15000,
      "reconnectInterval": 5000
    }]
  }
}
```

### 4. 安装依赖

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
pip install -r requirements.txt
```

### 5. 启动

```bash
start_bot.bat    # 守护模式（推荐，崩溃自动重启）
# 或
python bot.py    # 调试模式
```

## 插件配置

### 图片分类

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `TARGET_GROUPS` | 监听群号列表 | `[]` (所有群) |
| `ANIME_THRESHOLD` | 动漫判定阈值 | `0.7` |
| `USE_GPU` | GPU 推理 | `true` |
| `IMAGE_SAVE_DIR` | 保存目录 | `data/images` |

### LLM 聊天（DeepSeek）

```bash
# 初始化人格提示词
copy 人格提示词.example.txt 人格提示词.txt

# 初始化知识库（可选）
mkdir knowledge
# 参考 knowledge.example/ 目录结构
```

| 配置项 | 说明 |
|--------|------|
| `DEEPSEEK_API_KEY` | [DeepSeek API Key](https://platform.deepseek.com) |
| `LLM_SYSTEM_PROMPT_FILE` | 人格提示词文件路径 |
| `LLM_TARGET_GROUPS` | LLM 启用的群号，`[]` 关闭 |
| `LLM_TEMPERATURE` | 生成温度 0-2 |
| `LLM_COOLDOWN_BASE` | 回复冷却基准秒数 |

### 看门狗

| 层级 | 说明 |
|------|------|
| QQ 登录层 | 缓存凭据 → 密码回退 → 二维码扫码 |
| WebSocket | 心跳 15s，断开重连 5s |
| 应用层 | 每 5 分钟 API 心跳 + bot_offline 事件监听 |
| 进程层 | start_bot.bat 监控，崩溃自动重启 |

## 训练模型

```bash
# 1. 准备数据集
#    dataset/train/anime/  ← 动漫图
#    dataset/train/real/   ← 真实照片
#    dataset/val/anime/ + dataset/val/real/

# 2. 训练
python train_model.py
```

## 项目结构

```
├── bot.py                     # 入口
├── start_bot.bat              # 守护启动（推荐）
├── .env.example               # 配置模板
├── requirements.txt           # Python 依赖
├── models/yolov8n-cls.pt      # 预训练模型
├── knowledge.example/         # 知识库模板
├── 人格提示词.example.txt     # 人格提示词模板
├── src/plugins/
│   ├── image_classifier/      # 图片分类插件
│   ├── llm_chat/              # LLM 聊天插件
│   └── watchdog.py            # 看门狗插件
└── tools/NapCatQQ/            # NapCatQQ（需手动下载）
```

## 常见问题

**Q: 启动后闪退？**
A: 确保 `.env` 的 `ONEBOT_ACCESS_TOKEN` 与 NapCatQQ OneBot 配置一致。

**Q: 长时间运行掉线？**
A: 已内置四层防护。确认 `launcher-user.bat` 配置了回退密码，群内发 `.test_offline` 可测试。

**Q: 图片分类不准？**
A: 运行 `train_model.py` 用自有数据微调模型。

### Q: 图片没有被分类？
A: 需运行 `train_model.py` 训练专门的动漫二分类模型。默认的 ImageNet 预训练模型准确率有限。
