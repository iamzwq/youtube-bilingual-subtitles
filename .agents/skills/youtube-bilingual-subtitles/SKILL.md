---
name: youtube-bilingual-subtitles
description: "制作 YouTube 双语（中文+原文）字幕视频。当用户说“制作<youtube链接>双语字幕视频”、“给这个 YouTube 视频加中文双语字幕”、“bilingual subtitles for youtube”等类似请求时使用。流程：yt-dlp 下载视频/封面/词级 json3 字幕 → 清洗断句 → AI 恢复标点并翻译成中文 → 生成 ASS 双语字幕 → ffmpeg 烧录 1080P 视频。"
argument-hint: "<YouTube 视频链接>"
---

# YouTube 双语字幕视频

把一个 YouTube 视频制作成「中文在上、原文在下」的双语字幕视频。最终产出：烧录好字幕的 1080P mp4、双语 ASS 字幕、封面图、原始词级 json3 字幕。

## 何时使用

- 用户提供 YouTube 链接并要求“制作双语字幕视频 / 加中文双语字幕”。

## 前置条件

- 已安装并配置 PATH：`python`、`yt-dlp`、`ffmpeg`。
  - Python 命令名跨平台不同：**macOS/Linux 用 `python3`**，**Windows 用 `python`**（下文用 `$PY` 代指，按平台替换）。
- 首次运行先安装分句依赖：`$PY -m pip install -r .agents/skills/youtube-bilingual-subtitles/requirements.txt`
- 字体「霞鹜文楷等宽 / LXGW WenKai Mono」建议已安装；未安装时会回退系统默认字体，不影响流程。
- 仅支持公开可下载、且带有可下载 json3 字幕的视频；无字幕视频会报错退出。

## 管线总览（脚本 ↔ AI 交替，各阶段幂等可重跑）

设脚本目录为 `SK=.agents/skills/youtube-bilingual-subtitles/scripts`，`$PY` 为 python 命令（mac/Linux=`python3`，Windows=`python`）。所有产物落在当前目录下的 `<清洗后标题>/`。

1. 下载：`$PY $SK/download.py "<URL>"`
2. 断句：`$PY $SK/segment.py "<标题>/"`
3. 翻译（由你，AI，完成，见下）
4. 生成字幕：`$PY $SK/build_ass.py "<标题>/"`
5. 烧录：`$PY $SK/burn.py "<标题>/"`

`download.py` 会在结尾打印实际的项目目录路径 `<标题>/`，后续命令直接复用该路径。

## 步骤详解

### 1. 下载

运行 `download.py <URL>`。它会：

- 校验工具、拉取元数据（标题、简介、语言）；
- 下载 ≤1080P 的 mp4（`video.mp4`）、封面（`cover.jpg`）、词级 json3 字幕（`subtitle.json3`）、元数据（`info.json`）；
- 若找不到可下载的 json3 字幕，直接报错退出。

已存在的产物会跳过（除非加 `--force`）。

### 2. 断句

运行 `segment.py <项目目录>`。它会解析 `subtitle.json3`，清洗滚动重复词，按停顿/时长/长度切成“原子片段（atoms）”，输出 `raw_segments.json`：

```json
{ "source_mode": "word|event",
  "atoms": [ { "i": 0, "start": 1200, "end": 2600, "text": "so today were going to" }, ... ] }
```

`start`/`end` 为毫秒。自动字幕通常无标点，atoms 是较碎的短语，交由你在下一步做语义断句。

### 3. 翻译（AI 执行——这是你的职责）

读取 `<标题>/raw_segments.json` 与 `<标题>/info.json`。以视频标题、简介为上下文，产出 `<标题>/segments.json`：

```json
{
  "segments": [
    {
      "atoms": [0, 1, 2],
      "source": "So today, we're going to build a small app.",
      "translation": "那么今天，我们要做一个小应用。"
    },
    { "atoms": [3], "source": "[Music]", "translation": "" }
  ]
}
```

要求：

- **分组而非改时间**：每个 segment 用 `atoms` 列出它包含的原子片段**索引**（连续、覆盖全部、不重叠、不遗漏）。时间戳会由脚本根据首尾 atom 自动推导，你无需计算时间。
- **恢复标点 + 语义断句**：把碎片重组成完整句子，`source` 写恢复大小写与标点后的原文；一个语义句可跨多个 atom；尽量避免过长或半截句。
- **翻译**：`translation` 为地道中文，保留专有名词/数字；结合标题与简介保证术语一致。
- **分批处理**：每批约 30–50 句读入、翻译、增量写回，避免上下文过长；跨批保持术语统一。
- **非语音内容**（如 `[Music]`、`[Applause]`、`♪`）：`translation` 留空字符串。
- 严格输出上述 JSON 结构，UTF-8，无多余注释。

`segments.json` 会被缓存：若只想改样式/重烧录，不必重做翻译。

### 4. 生成 ASS 字幕

运行 `build_ass.py <项目目录>`。它读取 `segments.json` + `raw_segments.json`，生成 `subtitle.ass`：中文 `fs60` 在上、原文 `fs36` 在下，字体霞鹜文楷等宽，黑底半透明（`BorderStyle=3, OutlineColour=&H26000000, Outline=6, Shadow=0`），`PlayResX/Y=1920x1080`，底部居中，并施加最短时长/防重叠。

### 5. 烧录

运行 `burn.py <项目目录>`。它把字幕烧进视频，缩放到 1080P（只降不升），并**自动选择加速编码器**：macOS→`h264_videotoolbox`，Windows→`h264_nvenc/qsv/amf`，否则回退 `libx264`。可加 `--dry-run` 先打印所选编码器与命令。产物：`<标题>.mp4`。

## 最终产物（`<标题>/`）

- `<标题>.mp4`：烧录双语字幕的视频
- `subtitle.ass`：双语字幕
- `cover.jpg`：封面图
- `subtitle.json3`：原始词级字幕

## 参考

- ASS 样式细节见 [ass-style.md](./references/ass-style.md)
