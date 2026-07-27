# Transparent Background 4K

一个面向 Codex 的透明背景图片处理 Skill。它可以移除白色、近白色、浅灰色或扫描纸张背景，同时尽量保留文字、Logo、细线、抗锯齿边缘和已有透明度。

与生成式抠图不同，本项目使用确定性图像处理：不会重画品牌图形，不会改写文字，也不会凭空生成细节。

## 主要能力

- 移除纯色或近纯色浅背景
- 保留图片中已有的 alpha 透明度
- 支持透明 PNG、无损 WebP、LZW TIFF
- 支持带明确底色的 JPEG
- 使用 premultiplied alpha 安全放大透明图片
- 对低分辨率 Logo、图标和科研插图进行保守锐化
- 输出棋盘格预览、深色背景预览和 alpha mask
- 支持单图与批量处理
- 支持 macOS、Linux、Windows 和 WSL

## 画质增强

使用 `--enhance` 控制低分辨率增强：

| 模式 | 行为 |
| --- | --- |
| `off` | 默认值，不执行锐化 |
| `auto` | 实际放大倍率达到 1.5 倍时自动启用 |
| `light` | 无论是否放大都执行一次轻量锐化 |

增强仅混合完全不透明前景内部的 RGB，alpha 通道保持逐字节不变。放大超过 4 倍时会提示无法恢复真实细节。

```bash
python3 scripts/make_transparent_4k.py "input.png" \
  --target-width 3840 \
  --enhance auto \
  --preview \
  --preview-dark
```

## 输出格式

| 格式 | 透明度 | 适合场景 |
| --- | --- | --- |
| PNG | 支持 | 默认选择、PPT、通用透明素材 |
| WebP | 支持，无损 | 网页素材、需要更小体积时 |
| TIFF | 支持，LZW | 出版、设计和兼容 TIFF 的生产流程 |
| JPEG | 不支持 | 必须使用 `--matte` 指定合成底色 |

```bash
# 默认输出 PNG
python3 scripts/make_transparent_4k.py "input.jpg"

# 无损透明 WebP
python3 scripts/make_transparent_4k.py "input.jpg" --format webp

# LZW TIFF
python3 scripts/make_transparent_4k.py "input.jpg" --format tiff

# JPEG 必须明确指定底色
python3 scripts/make_transparent_4k.py "input.png" \
  --format jpeg \
  --matte white
```

`--matte` 支持 `white`、`black` 或 `R,G,B`，例如 `--matte 10,20,30`。如果 `--format` 与输出文件后缀冲突，程序会直接报错，不会猜测。

## 安装

需要 Python 3.10 或更高版本。

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

安装后重新打开 Codex，或开始一个新任务，让 Codex 重新发现 Skill。

## 在 Codex 中使用

可以直接描述需求，不需要记命令：

```text
把这张图的白色背景变透明，保持原尺寸。
```

```text
把这个低分辨率 Logo 放大到 3840 像素宽，安全增强后输出无损 WebP。
```

```text
批量处理这个文件夹里的图片，输出 TIFF，并生成深色背景预览。
```

Codex 会根据 [SKILL.md](SKILL.md) 选择背景范围、增强模式、格式和预览方式。

## 常用命令

白底 Logo 或文字中所有白色区域都需要透明：

```bash
python3 scripts/make_transparent_4k.py "logo.png" \
  --background-scope all \
  --bg white \
  --edge-matte-strength 1.0 \
  --preview \
  --preview-dark
```

批量转换为无损 WebP：

```bash
python3 scripts/batch_make_transparent_4k.py "INPUT_DIR" \
  --output-dir "OUTPUT_DIR" \
  --format webp \
  --enhance auto \
  --summary-json "OUTPUT_DIR/summary.json" \
  --summary-csv "OUTPUT_DIR/summary.csv"
```

批处理会继续处理单个失败后的其他图片。退出码 `0` 表示全部成功，`2` 表示部分成功，`1` 表示全部失败或初始化失败。

## 背景范围

- `--background-scope edge`：默认值，仅移除与画布边缘连通的背景，适合科研图、流程图和包含内部白色区域的图片。
- `--background-scope all`：移除所有匹配背景色，适合需要把字母孔洞也变透明的 Logo 或文字。
- `--bg auto`：只在图片边缘足够不透明且足够明亮时自动判断背景。
- `--bg white` 或 `--bg R,G,B`：明确指定需要移除的背景。

## 设计边界

这个 Skill 优先保证内容与透明度正确：

- 不裁剪、不重排、不删除文字
- 不进行矢量描摹
- 不使用生成式超分或联网下载模型
- 不把锐化描述为真实细节恢复
- 不建议用于头发、玻璃、烟雾或复杂自然场景
- 预览和 mask 始终使用 PNG，不能替代最终输出文件

## 验证

```bash
python3 -B -m unittest discover -s tests
```

当前版本包含 59 项测试，覆盖：

- 默认 PNG 行为
- 1.5 倍自动增强边界
- alpha 通道逐字节保持
- 透明像素 RGB 污染检查
- PNG、WebP 和 TIFF 的 RGBA 往返
- JPEG matte 约束
- 格式推断与冲突
- 批处理同名避碰和汇总字段
- macOS、Linux、Windows 和 WSL 路径兼容性

## 项目结构

```text
transparent-background-4k/
├── SKILL.md
├── README.md
├── requirements.txt
├── agents/
│   └── openai.yaml
├── scripts/
│   ├── make_transparent_4k.py
│   └── batch_make_transparent_4k.py
└── tests/
```
