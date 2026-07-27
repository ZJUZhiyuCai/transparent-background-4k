# Transparent Background 4K

一个面向 Codex 的图片抠图 Skill：把白色、近白色、浅灰色或扫描纸张背景变成透明背景，同时保留文字、Logo、细线、颜色和抗锯齿边缘，可选安全放大到 4K。适合制作 PPT 素材、科研插图、透明 Logo 和网页图片资产。

它使用确定性图像处理，而不是生成式抠图：不重画品牌图形，不改写文字，也不凭空生成细节。

## 目录

- [为什么使用它](#为什么使用它)
- [核心能力](#核心能力)
- [效果与设计原则](#效果与设计原则)
- [快速安装](#快速安装)
- [在 Codex 中使用](#在-codex-中使用)
- [常用 CLI 示例](#常用-cli-示例)
- [输出格式对比](#输出格式对比)
- [画质增强模式](#画质增强模式)
- [背景范围选择](#背景范围选择)
- [批量处理](#批量处理)
- [使用边界](#使用边界)
- [测试与验证](#测试与验证)
- [项目结构](#项目结构)

## 为什么使用它

- **内容安全**：科研插图、机制图、Logo 里的文字和细线不能被 AI 重画。本工具只做像素级背景移除和确定性锐化，前景内容保持原样。
- **透明度正确**：已有 alpha 通道逐字节保留；放大使用 premultiplied alpha，避免透明边缘出现白边或颜色渗漏。
- **结果可解释**：每次运行报告移除状态、输出格式、增强状态和放大倍率；效果可疑时打印质量警告，而不是静默输出。

## 核心能力

- 移除白色、近白色、浅灰色或扫描纸张背景
- 保留文字、Logo、细线、颜色、抗锯齿边缘和已有 alpha 通道
- 默认输出透明 PNG，也支持无损透明 WebP 和 LZW TIFF
- JPEG 不支持透明度，需用 `--matte` 指定合成底色
- `--enhance off|auto|light` 三档画质增强（透明度安全的确定性锐化）
- 可选 4K 放大（`--target-width 3840`），使用 premultiplied alpha 防止边缘渗色
- 棋盘格预览、深色背景预览和 alpha mask 输出
- 单图处理与目录批量处理，批处理带 JSON/CSV 汇总
- 支持 Python 3.10+，可在 macOS、Linux、Windows 和 WSL 上运行

## 效果与设计原则

- **只移除背景，不动前景**：不裁剪、不重排、不删除文字、不做矢量描摹。
- **增强是锐化，不是超分**：`--enhance` 是确定性的透明度安全锐化，只混合完全不透明前景内部的 RGB，alpha 通道逐字节不变。它能提升边缘清晰度，但不能恢复原图不存在的真实细节；放大超过 4 倍时会明确提示这一点。
- **拿不准时保守处理**：`--bg auto` 只在图片边缘足够不透明且足够明亮时才判断背景；边缘已透明或颜色不一致时会跳过移除，而不是猜测。
- **本地运行**：不使用生成式模型，不联网下载权重。

## 快速安装

需要 Python 3.10 或更高版本。安装到 Codex Skill 目录：

```text
${CODEX_HOME:-$HOME/.codex}/skills/transparent-background-4k
```

### macOS、Linux 和 WSL

```bash
git clone https://github.com/ZJUZhiyuCai/transparent-background-4k.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/transparent-background-4k"

python3 -m pip install -r \
  "${CODEX_HOME:-$HOME/.codex}/skills/transparent-background-4k/requirements.txt"
```

### Windows PowerShell

```powershell
$CodexRoot = if ($env:CODEX_HOME) {
    $env:CODEX_HOME
} else {
    Join-Path $env:USERPROFILE ".codex"
}

$SkillDir = Join-Path $CodexRoot "skills\transparent-background-4k"
git clone https://github.com/ZJUZhiyuCai/transparent-background-4k.git $SkillDir
py -3 -m pip install -r (Join-Path $SkillDir "requirements.txt")
```

没有安装 Windows 启动器时，把 `py -3` 换成 `python`。WSL 下请使用 macOS/Linux 命令和 WSL 路径，不要使用 PowerShell 路径。

依赖为 Pillow 和 numpy；OpenCV（`opencv-python-headless`）用于加速连通域和模糊运算，无法安装时脚本会自动回退到较慢的纯 Pillow/Python 实现。

安装后重新打开 Codex 或开始一个新任务，让 Codex 重新发现 Skill。

## 在 Codex 中使用

直接用自然语言描述需求，不需要记命令：

```text
把这张图的白色背景变透明，保持原尺寸。
```

```text
把这个低分辨率 Logo 放大到 3840 像素宽，安全增强后输出无损 WebP。
```

```text
批量处理这个文件夹里的图片，输出 TIFF，并生成深色背景预览。
```

Codex 会根据 [SKILL.md](SKILL.md) 选择背景范围、增强模式、输出格式和预览方式。

## 常用 CLI 示例

以下命令在仓库根目录运行；已按上文安装为 Skill 时，把 `scripts/...` 换成 Skill 目录下的完整路径即可。路径含空格或中文时请加引号。

最简单用法——移除浅色背景，保持原尺寸，输出 `<原名>_transparent.png`：

```bash
python3 scripts/make_transparent_4k.py "input.jpg"
```

低分辨率图放大到 4K 宽并自动增强，同时生成棋盘格和深色背景预览：

```bash
python3 scripts/make_transparent_4k.py "input.png" \
  --target-width 3840 \
  --enhance auto \
  --preview \
  --preview-dark
```

白底 Logo 或文字，字母孔洞等所有白色区域都要变透明：

```bash
python3 scripts/make_transparent_4k.py "logo.png" \
  --background-scope all \
  --bg white \
  --edge-matte-strength 1.0 \
  --preview \
  --preview-dark
```

其他常用开关：`--target-long-edge` 按长边定尺寸；`--force-resize` 允许缩小（需配合目标尺寸）；`--mask-debug` 输出 alpha mask；`--overwrite` 允许覆盖已有文件（否则自动加数字后缀）。完整参数见 `--help`。

## 输出格式对比

| 格式 | 透明度 | 适合场景 |
| --- | --- | --- |
| PNG | 支持 | 默认选择、PPT、通用透明素材 |
| WebP | 支持，无损 | 网页素材、需要更小体积时 |
| TIFF | 支持，LZW 压缩 | 出版、设计和兼容 TIFF 的生产流程 |
| JPEG | 不支持 | 必须用 `--matte` 指定合成底色 |

```bash
# 默认输出 PNG
python3 scripts/make_transparent_4k.py "input.jpg"

# 无损透明 WebP
python3 scripts/make_transparent_4k.py "input.jpg" --format webp

# LZW TIFF
python3 scripts/make_transparent_4k.py "input.jpg" --format tiff

# JPEG 必须明确指定底色：white、black 或 R,G,B
python3 scripts/make_transparent_4k.py "input.png" \
  --format jpeg \
  --matte white
```

`--matte` 接受 `white`、`black` 或 `R,G,B`（例如 `--matte 10,20,30`）。也可以只写输出文件名，由 `-o output.webp` 的后缀决定格式；如果 `--format` 与输出后缀冲突，程序会直接报错，不会猜测。预览图和 mask 始终是 PNG，不能替代最终输出。

## 画质增强模式

用 `--enhance` 控制低分辨率增强：

| 模式 | 行为 |
| --- | --- |
| `off` | 默认值，不执行锐化 |
| `auto` | 实际放大倍率达到 1.5 倍时才启用 |
| `light` | 无论是否放大都执行一次轻量锐化 |

增强只混合完全不透明前景内部的 RGB，alpha 通道逐字节保持不变，完全透明像素的 RGB 也不会被污染。放大超过 4 倍时会警告：锐化无法恢复真实细节。

## 背景范围选择

- `--background-scope edge`（默认）：只移除与画布边缘连通的背景，保留内部封闭的白色区域，适合科研插图、流程图和带白色填充的图片。
- `--background-scope all`：移除所有匹配的背景色区域，适合需要把字母孔洞也变透明的 Logo 或文字；注意它可能误删有意保留的白色前景。
- `--bg auto`（默认）：只在图片边缘足够不透明且足够明亮时自动判断背景色。
- `--bg white` 或 `--bg R,G,B`：明确指定要移除的背景色。

浅色背景残留时增大 `--bg-distance`；浅色内容被误删时减小它。更多微调参数（`--brightness-threshold`、`--protect-contrast`、`--feather`、`--edge-matte-*` 等）见 [SKILL.md](SKILL.md) 的 Tuning 一节。

## 批量处理

```bash
python3 scripts/batch_make_transparent_4k.py "INPUT_DIR" \
  --output-dir "OUTPUT_DIR" \
  --format webp \
  --enhance auto \
  --summary-json "OUTPUT_DIR/summary.json" \
  --summary-csv "OUTPUT_DIR/summary.csv"
```

批处理行为：

- 单张失败不会中断，会继续处理其余图片
- 退出码 `0` 表示全部成功，`2` 表示部分成功，`1` 表示全部失败或初始化失败
- 已生成的透明图、预览和 mask 在再次运行时自动跳过
- 同名不同后缀的输入（如 `figure.jpg` 和 `figure.png`）会得到不同的输出文件名
- JSON/CSV 汇总记录每张图的处理状态、输出格式和增强状态

## 使用边界

- 面向纯色或近纯色浅背景：插图、图表、图标、Logo、文字标签、机制图和纯底截图。
- 不建议用于头发、玻璃、烟雾、人像或复杂自然照片——这类边缘需要生成式抠图，超出本工具的确定性方法。
- 不联网、不下载模型、不做生成式超分。
- 输入尺寸默认上限 24,000,000 像素，输出上限 32,000,000 像素（`--max-input-pixels` / `--max-output-pixels` 可调，不建议随意调大）。
- 输出路径为符号链接时会被拒绝；最终文件均为原子写入，避免产生半成品。

## 测试与验证

```bash
python3 -B -m unittest discover -s tests
```

当前版本包含 59 项测试，全部通过，覆盖：

- 白色、近白色、浅灰背景移除与深色内容保护
- 已有 alpha 通道逐字节保持、半透明像素 RGB 不被改写
- 1.5 倍自动增强边界与 4 倍放大警告
- 增强不污染完全透明像素的 RGB
- PNG、WebP、TIFF 的 RGBA 无损往返
- JPEG 缺少 `--matte` 时拒绝执行
- 格式推断与 `--format`/后缀冲突检测
- 批处理同名避碰、部分失败退出码和汇总字段
- 含空格与非 ASCII 字符路径的跨平台处理
- 符号链接输出路径拒绝、输入/输出像素上限

## 项目结构

```text
transparent-background-4k/
├── SKILL.md              # Codex 使用的工作流、参数与守则
├── README.md
├── requirements.txt
├── agents/
│   └── openai.yaml       # Skill 界面元数据
├── scripts/
│   ├── make_transparent_4k.py        # 单图处理 CLI
│   └── batch_make_transparent_4k.py  # 批量处理 CLI
└── tests/                # 单元测试
```
