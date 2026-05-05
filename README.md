# DoroAi — AI桌面宠物 项目部署说明

---

## 一、项目简介

DoroAi 是一款基于 PySide6 的 Windows 桌面宠物应用，集成 AI 大语言模型对话、OCR 屏幕识别、TTS 语音合成等功能。宠物形象驻留在桌面，支持拖拽互动、气泡对话、橘子投喂等丰富玩法。

---

## 二、环境要求

| 项目 | 最低要求 |
|------|---------|
| 操作系统 | Windows 10 / 11 (64位) |
| Python | 3.10+ |
| 内存 | 8 GB+ |
| 磁盘 | 5 GB+ (含 AI 模型) |
| 网络 | 需访问豆包 API (公网) |

---

## 三、环境搭建步骤

### 3.1 克隆 / 下载项目

```bash
# 直接使用项目文件夹，或
git clone <https://github.com/hanli1001/DoroAi>
cd DoroAi
```

### 3.2 创建虚拟环境（推荐）

```bash
python -m venv venv

# Windows 激活
venv\Scripts\activate
```

### 3.3 安装核心依赖

```bash
pip install PySide6 requests pyyaml pillow numpy
```

### 3.4 安装语音合成依赖（可选）

```bash
pip install edge-tts pygame
```

> 不安装则 TTS 语音功能自动禁用，不影响其他功能的正常使用。

### 3.5 安装 OCR 屏幕识别依赖（可选）

```bash
pip install easyocr torch
```

> torch 约 114 MB，首次运行 easyocr 会自动下载识别模型文件（约 100 MB）。不安装则 OCR 功能不可用，其他功能正常。

### 3.6 验证安装

```bash
python -c "from ui.main_window import PetMainWindow; print('环境就绪')"
```

输出 `环境就绪` 即表示依赖安装完成。

---

## 四、API 账号配置

### 4.1 配置文件位置

```
config/settings.yaml
```

### 4.2 配置 AI 接口

编辑 `config/settings.yaml` 中的 `ai` 配置段：

```yaml
ai:
    api_url: "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
    api_key: "你的API密钥"
    model: "doubao-seed-character-251128"
    max_tokens: 2048
    temperature: 0.75
    timeout_connect: 8
    timeout_read: 40
```

| 字段 | 说明 |
|------|------|
| `api_url` | API 端点地址。默认使用豆包(Doubao) API，也可替换为 OpenAI 兼容接口 |
| `api_key` | **必填**。从豆包控制台获取的 API Key |
| `model` | 模型名称。推荐 `doubao-seed-character-251128`（角色扮演模型） |
| `max_tokens` | 单次回复最大 token 数 |
| `temperature` | 生成随机性，0-1，越大越有创意 |

### 4.3 更换其他 AI 服务商

本项目使用 OpenAI 兼容接口格式。如需切换到其他服务商（如 DeepSeek、通义千问、ChatGPT），只需修改 `api_url` 和 `api_key` 即可：

```yaml
# DeepSeek 示例
ai:
    api_url: "https://api.deepseek.com/v1/chat/completions"
    api_key: "sk-你的DeepSeek密钥"
    model: "deepseek-chat"
```

```yaml
# 阿里通义千问 示例 (需兼容 OpenAI 格式的端点)
ai:
    api_url: "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    api_key: "sk-你的通义千问密钥"
    model: "qwen-plus"
```

---

## 五、运行启动

### 5.1 正常启动

```bash
python main.py
```

### 5.2 首次启动行为

- 窗口出现在屏幕**右下角**
- 宠物显示默认形象（`resources/images/logo.png`）
- 气泡显示欢迎语"汪呜～主人好！我是Doro～"
- 右键宠物打开菜单，可进行各项操作

### 5.3 交互方式

| 操作 | 功能 |
|------|------|
| 左键点击宠物 | 显示/隐藏输入面板 |
| 左键拖拽宠物 | 移动宠物位置 |
| 右键宠物 | 打开功能菜单 |
| 输入文字 + Enter | 与 Doro 对话 |
| 右键 → 框选识别 | OCR 屏幕文字识别 |
| 右键 → 生成橘子 | 生成可拖拽的橘子 |

---

## 六、目录结构

```
DoroAi/
├── main.py                  # 应用入口
├── Doro.py                  # 独立透明窗口示例
├── config/
│   ├── settings.yaml        # 主配置文件（API、窗口、计时器等）
│   ├── actions.yaml         # 动作/动画配置
│   ├── commands.yaml        # 自定义命令配置
│   └── character.yaml       # AI 角色设定
├── core/
│   ├── action_manager.py    # 动作管理器
│   ├── command_parser.py    # 命令解析器
│   ├── event_system.py      # 全局事件总线
│   ├── ocr_worker.py        # OCR 识别引擎
│   └── pet_state.py         # 宠物状态机
├── ai/
│   ├── ai_worker.py         # AI 对话客户端
│   ├── prompt_manager.py    # Prompt 管理
│   └── memory_manager.py    # 用户记忆管理
├── ui/
│   ├── main_window.py       # 主窗口（宠物 + 气泡 + 输入面板）
│   ├── bubble_widget.py     # 气泡组件
│   ├── menu_widget.py       # 右键菜单（玻璃拟态）
│   ├── glass_widget.py      # 毛玻璃容器组件
│   ├── screen_capture.py    # 截图框选控件
│   ├── orange_widget.py     # 橘子组件
│   └── about_dialog.py      # 关于对话框
├── utils/
│   ├── config_loader.py     # YAML 配置加载器
│   ├── tts_engine.py        # TTS 语音引擎
│   ├── path_utils.py        # 路径工具
│   └── logger.py            # 日志模块
├── resources/
│   └── images/              # 宠物图片 / GIF 资源
├── user_memory.json         # 用户记忆数据
└── 项目部署说明.md           # 本文件
```

---

## 七、常见问题

### Q: 启动后桌面没有显示宠物？
A: 检查 `resources/images/logo.png` 是否存在。宠物窗口是透明的，确认没有被其他窗口遮挡，尝试按 Alt+Tab 查找。

### Q: 对话没有回复？
A: 检查 `config/settings.yaml` 中 `api_key` 是否填写正确，以及网络能否访问 API 地址。

### Q: OCR 识别不可用？
A: 确认已安装 `easyocr` 和 `torch`。首次启动会自动下载识别模型（~100MB），请耐心等待初始化完成。

### Q: 语音没有声音？
A: 确认已安装 `edge-tts` 和 `pygame`。检查系统音量是否正常。

### Q: 如何自定义宠物形象？
A: 替换 `resources/images/logo.png` 为你的图片（保持文件名），或修改 `config/settings.yaml` 中的 `pet.image_path`。

### Q: 如何修改 AI 角色性格？
A: 编辑 `config/character.yaml` 中的 `bg.background`（背景故事）和 `pr.personality`（性格设定）。

---

## 八、技术支持

- 项目配置：`config/settings.yaml`
- 角色设定：`config/character.yaml`
- 日志输出：终端控制台实时输出
- 记忆数据：`user_memory.json`
