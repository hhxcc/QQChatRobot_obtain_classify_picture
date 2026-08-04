# QQ 群聊聊天兼动漫图片采集分类机器人

自动监听 QQ 群消息，下载图片并用 YOLOv8 分类保存二次元图片。内置 LLM 聊天插件，支持角色扮演与看图对话，支持 7×24 无人值守运行。

## 功能

| 模块 | 说明 |
|------|------|
| 🖼️ 图片分类 | YOLOv8 自定义模型，动漫/真实 二分类 |
| 💬 LLM 聊天 | DeepSeek API 驱动，支持人格注入和知识库检索 |
| 🧠 长期记忆 | sqlite 持久化，AI 自动蒸馏群友画像/群事件，重启不丢 |
| 🔎 联网搜索 | Function Calling 按需搜索百科/网络，搜不到如实回答 |
| 👁️ 看图对话 | GLM 视觉模型 + CLIP/OCR 本地预筛，识别图片内容并按人设回应 |
| 🛡️ 防掉线 | 四层防护：自动登录 + 密码回退 + watchdog 检测 + 进程守护 |

## 架构

```
QQ群 ──→ NapCatQQ ──WS──→ NoneBot2
                              ├── image_classifier → YOLOv8 → 本地存储
                              ├── llm_chat → DeepSeek API
                              │     ├── memory → sqlite 长期记忆（AI 蒸馏群友画像/群事件）
                              │     ├── web_search → 免费搜索 (Function Calling)
                              │     └── vision → GLM 视觉 API + CLIP/OCR 本地预筛
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

### 视觉功能（看图说话）

依赖 GLM 视觉 API（图片理解）+ CLIP/OCR 本地预筛（零成本过滤）。模型通过解耦接口配置，换模型只改 `VISION_PROVIDER` / `VISION_MODEL`。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `LLM_VISION_ENABLED` | 视觉功能总开关 | `false` |
| `VISION_PROVIDER` | 视觉 Provider（`glm`） | `glm` |
| `VISION_API_KEY` | [智谱开放平台](https://open.bigmodel.cn) API Key | 空 |
| `VISION_MODEL` | 视觉模型名 | `glm-4v-flash` |
| `VISION_BASE_URL` | API 地址 | `https://open.bigmodel.cn/api/paas/v4` |
| `VISION_TIMEOUT` | 视觉 API 超时（秒） | `15` |
| `VISION_CLIP_ENABLED` | CLIP 本地预筛 | `true` |
| `VISION_CLIP_THRESHOLD` | 纯图触发阈值（0-1），越低越易触发 | `0.6` |
| `VISION_CLIP_MODEL_PATH` | CLIP 本地模型路径（不存在则在线加载） | `models/clip-vit-base-patch32` |
| `VISION_OCR_ENABLED` | OCR 提取图片文字（表情包/截图） | `true` |
| `VISION_REPLY_ON_AT` | @机器人+图必回 | `true` |
| `VISION_REPLY_ON_TEXT_IMG` | 图文混发时图片辅助理解 | `true` |
| `VISION_REPLY_ON_IMAGE_ONLY` | 纯图片消息触发（受冷却约束） | `true` |
| `VISION_CACHE_TTL` | 同图缓存秒数（省成本） | `3600` |

**群内指令**：`/vision on` | `/vision off` | `/vision status`

### 长期记忆（LLM 聊天）

自动记录群友发言到 `data/memory.db`（sqlite，重启不丢），由**独立蒸馏模型**按"消息量 + 定时兜底"两种方式把原始消息提炼成群友画像与群事件，对话时自动注入上下文，让机器人记得群友的性格与态度。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `LLM_MEMORY_ENABLED` | 长期记忆总开关 | `true` |
| `MEMORY_DB_PATH` | 记忆数据库路径 | `data/memory.db` |
| `MEMORY_PROVIDER` | 蒸馏模型 Provider（解耦，可换更便宜的模型） | `deepseek` |
| `MEMORY_BASE_URL` | 蒸馏 API 地址（留空复用 DeepSeek） | 空 |
| `MEMORY_API_KEY` | 蒸馏 API Key（留空复用 `DEEPSEEK_API_KEY`） | 空 |
| `MEMORY_MODEL` | 蒸馏模型名 | `deepseek-chat` |
| `MEMORY_DISTILL_THRESHOLD` | 每人累积多少条消息触发一次蒸馏 | `30` |
| `MEMORY_DISTILL_INTERVAL` | 定时兜底蒸馏间隔（秒） | `1800` |

### 联网搜索（LLM 聊天）

通过 Function Calling 让模型按需搜索：只要不确定就搜索，一个引擎搜不到就换另一个；搜不到就如实说"查不到/不了解/不清楚"。模型可调用 `web_search_bing` / `web_search_duckduckgo` / `web_search_baidu` 三个函数。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `LLM_WEB_SEARCH_ENABLED` | 联网搜索总开关 | `true` |
| `SEARCH_ENGINE` | 默认搜索方式：`bing` / `duckduckgo` / `baidu` | `bing` |
| `SEARCH_RESULT_COUNT` | 每个搜索函数最多返回条数 | `5` |
| `SEARCH_TIMEOUT` | 单次搜索超时（秒） | `8` |

> 说明：搜索为免费 HTML 抓取（必应中文友好）。若某个引擎反爬或超时，机器人会自动如实回复"查不到"，不会编造。

**下载 CLIP 本地模型**（约 600MB，不入库）：

```bash
# 国内镜像，断点续传
curl -L -o models/clip-vit-base-patch32/pytorch_model.bin \
  "https://hf-mirror.com/openai/clip-vit-base-patch32/resolve/main/pytorch_model.bin"
# 其余小文件：config.json / preprocessor_config.json / vocab.json / merges.txt
# tokenizer_config.json / special_tokens_map.json 同样从 hf-mirror 下载
```

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
├── models/yolov8n-cls.pt      # YOLO 预训练模型（入库）
├── models/clip-vit-base-patch32/  # CLIP 本地预筛模型（~600MB，需下载，不入库）
├── knowledge.example/         # 知识库模板
├── 人格提示词.example.txt     # 人格提示词模板
├── src/plugins/
│   ├── image_classifier/      # 图片分类插件
│   ├── llm_chat/              # LLM 聊天插件
│   │   └── vision/            # 视觉子模块（看图对话）
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

**Q: 看图功能报 429 限流？**
A: 免费视觉模型访问量大时偶发 429，已内置自动重试与熔断。可切换更稳定的模型（`.env` 的 `VISION_MODEL`），或提高 `VISION_CLIP_THRESHOLD` 减少触发频率、调大 `VISION_CACHE_TTL` 复用缓存。

**Q: 视觉识别失败会瞎猜吗？**
A: 不会。识别失败时会注入"禁止编造画面"提示，Bot 只会基于已有信息（类别/图上文字）简单回应或回复 `[SKIP]`。
