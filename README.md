# QQ 群聊聊天兼动漫图片采集分类机器人

自动监听 QQ 群消息，下载图片并用 YOLOv8 分类保存二次元图片。内置 LLM 聊天插件，支持角色扮演与看图对话，支持 7×24 无人值守运行。

## 功能

| 模块 | 说明 |
|------|------|
| 🖼️ 图片分类 | YOLOv8 自定义模型，动漫/真实 二分类 |
| 💬 LLM 聊天 | DeepSeek API 驱动，支持人格注入和知识库检索 |
| 🧠 长期记忆 | sqlite 持久化，AI 自动蒸馏群友画像/群事件，重启不丢 |
| 🔎 联网搜索 | Function Calling 按需搜索百科/网络，搜不到如实回答 |
| 👁️ 看图对话 | 本地 Ollama / 云端 GLM 视觉 + CLIP/OCR 本地预筛，按人设回应 |
| 🛡️ 防掉线 | SnowLuma 协议端(自动注入+WS 自愈) + watchdog 心跳 + 守护进程重启 |

## 架构

```
QQ群 ──→ QQ(小号) ──注入──→ SnowLuma ──WS──→ NoneBot2
                                                  ├── image_classifier → YOLOv8 → 本地存储
                                                  ├── llm_chat → DeepSeek API
                                                  │     ├── memory → sqlite 长期记忆（AI 蒸馏群友画像/群事件）
                                                  │     ├── web_search → 免费搜索 (Function Calling)
                                                  │     └── vision → Ollama 本地 / GLM 云端 + CLIP/OCR 预筛
                                                  └── watchdog → 心跳保活 + 掉线自愈
```

## 环境要求

- Windows 10/11
- Python 3.10+
- QQ NT 已安装并登录机器人小号（SnowLuma 以注入方式接入）
- NVIDIA GPU (CUDA 12.0+) / CPU（`.env` 中 `USE_GPU=false`）
- （可选）Ollama 已部署多模态模型（本地视觉，如 `qwen3.5:4B`）

## 快速开始

### 1. 获取 SnowLuma（协议端）

从 [SnowLuma Releases](https://github.com/SnowLuma/SnowLuma/releases) 下载 Windows x64 **完整发行包**（如 `SnowLuma-v1.14.15-win-x64.zip`，内置 Node.js 运行时），解压到 `tools/SnowLuma/`。

```
tools/SnowLuma/
├── launcher.bat    ← 启动脚本
├── node.exe        ← 内置 Node 运行时
├── index.mjs       ← 主程序
├── native/         ← 原生组件（含 QQ 注入 hook）
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

### 3. 配置 SnowLuma

启动后打开 WebUI `http://localhost:5099`（首次初始账号 `admin`，密码见启动日志）：

1. 同意 EULA/隐私 → 修改初始密码（一次性，关闭程序后无法找回）
2. 登录**机器人小号**的 QQ(NT) 进程
3. 「进程注入」页 → 探测登录 → 加载该 QQ（若以 `SNOWLUMA_HOOK_AUTOLOAD=1` 启动则会**自动注入**新发现的 QQ）
4. 「节点配置」→「WS 客户端」→ 新建：
   - URL: `ws://127.0.0.1:8080/onebot/v11/ws`
   - 授权 Token: 与 `.env` 的 `ONEBOT_ACCESS_TOKEN` 一致
   - 消息格式: 数组 · 角色: Universal · 启用

SnowLuma 作为 **WS 客户端**主动连接本机 NoneBot(8080)。配置按账号存于 `tools/SnowLuma/config/onebot_<QQ>.json`。

### 4. 安装依赖

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
pip install -r requirements.txt
```

### 5. 启动

```bash
start_bot.bat    # 守护模式（推荐）：检测/拉起 QQ → 启动 SnowLuma(自动注入) → 守护 bot.py
# 或
python bot.py    # 调试模式（需 SnowLuma 已手动启动）
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
| `LLM_TIMEOUT` | 单次 LLM 请求超时（秒，默认 30），应对不稳定网络 |
| `LLM_MAX_RETRIES` | 网络/超时类异常自动重试次数（默认 2） |

### 视觉功能（看图说话）

视觉模型通过解耦接口配置，换模型只改 `VISION_PROVIDER` / `VISION_MODEL` / `VISION_BASE_URL`：
- **`glm`（默认，云端）**：智谱 `glm-4v-flash`，免费、通用、不占本地显存；
- **`ollama`（本地）**：Ollama 多模态模型（如 `qwen3.5:4B`），细节/图上文字/分类更好、离线、免 API Key，需本机已部署 Ollama。

两种模式均叠加 CLIP/OCR 本地预筛（零成本过滤）。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `LLM_VISION_ENABLED` | 视觉功能总开关 | `false` |
| `VISION_PROVIDER` | 视觉 Provider（`glm` \| `ollama`） | `glm` |
| `VISION_API_KEY` | 云端 Key（智谱开放平台）；本地 ollama 留空 | 空 |
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

**切本地 Ollama 视觉示例**（`.env`）：

```env
VISION_PROVIDER=ollama
VISION_MODEL=qwen3.5:4B               # 需先 ollama pull
VISION_BASE_URL=http://localhost:11434 # 远程 Ollama 填其地址
VISION_API_KEY=                         # 本地无需 Key
VISION_TIMEOUT=120                      # 本地冷启动较慢
```

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
| `SEARCH_CACHE_TTL` | 搜索缓存秒数，同类问题短时间不重复搜 | `300` |

> 说明：搜索为免费 HTML 抓取（必应中文友好）。若某个引擎反爬或超时，机器人会自动如实回复"查不到"，不会编造。LLM 请求自带超时 + 自动重试，可扛过校园网等不稳定网络的偶发抖动。

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
| 协议端 | SnowLuma 注入 QQ；`SNOWLUMA_HOOK_AUTOLOAD=1` 自动注入新发现的 QQ 进程 |
| WebSocket | SnowLuma 作为 WS 客户端连 NoneBot(8080)，自带传输层心跳与断线自动重连 |
| 应用层 | 每 3 分钟 API 心跳 + bot_offline 事件监听（登录失效 → 退出由守护重启） |
| 进程层 | start_bot.bat：拉起 QQ / 启动 SnowLuma / 守护 bot.py，崩溃自动重启 |

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
└── tools/SnowLuma/            # SnowLuma 协议端（手动下载解压，不入库）
```

## 常见问题

**Q: 启动后闪退？**
A: 确保 `.env` 的 `ONEBOT_ACCESS_TOKEN` 与 SnowLuma「WS 客户端」节点中的授权 Token 一致，且 SnowLuma 已注入登录机器人小号的 QQ。

**Q: 长时间运行掉线？**
A: SnowLuma 内置 WS 心跳与自动重连；若 QQ 被踢下线，重新登录该 QQ 后 SnowLuma 会自动重新注入。群内发 `.test_offline` 可自测 bot 重启链路。

**Q: 图片分类不准？**
A: 运行 `train_model.py` 用自有数据微调模型。

### Q: 图片没有被分类？
A: 需运行 `train_model.py` 训练专门的动漫二分类模型。默认的 ImageNet 预训练模型准确率有限。

**Q: 看图功能报 429 限流？**
A: 云端免费视觉模型偶发 429，已内置自动重试与熔断。可改用本地 Ollama 视觉（`VISION_PROVIDER=ollama`）彻底规避限流，或提高 `VISION_CLIP_THRESHOLD`、调大 `VISION_CACHE_TTL`。

**Q: 视觉识别失败会瞎猜吗？**
A: 不会。识别失败时会注入"禁止编造画面"提示，Bot 只会基于已有信息（类别/图上文字）简单回应或回复 `[SKIP]`。
