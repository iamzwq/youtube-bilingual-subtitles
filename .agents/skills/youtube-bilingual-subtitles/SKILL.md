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
- 无需第三方 Python 依赖（脚本仅用标准库；断句与翻译由 LLM 完成）。
- 字体「霞鹜文楷等宽 / LXGW WenKai Mono」建议已安装；未安装时会回退系统默认字体，不影响流程。
- 可选：安装 `aria2c` 后，`download.py` 会自动用它做多线程分片 + 断点续传下载（加速）；用 `--no-aria2c` 可关闭。
- 仅支持公开可下载、且带有可下载 json3 字幕的视频；无字幕视频会报错退出。

## 管线总览（脚本 ↔ AI 交替，各阶段幂等可重跑）

设脚本目录为 `SK=.agents/skills/youtube-bilingual-subtitles/scripts`，`$PY` 为 python 命令（mac/Linux=`python3`，Windows=`python`）。所有产物落在当前目录下的 `<清洗后标题>/`。

1. 下载：`$PY $SK/download.py "<URL>"`
2. 断句：`$PY $SK/segment.py "<标题>/"`
3. 翻译（由你，AI，完成，见下）
4. 生成字幕：`$PY $SK/build_ass.py "<标题>/"`
5. 烧录：`$PY $SK/burn.py "<标题>/"`

`download.py` 会在结尾打印实际的项目目录路径 `<标题>/`，后续命令直接复用该路径。

## 批量处理（多个链接）

支持一次传入多个 YouTube 链接。**按视频顺序逐个跑完整 1–5 步**（串行，非并行）：

- 每个视频有独立的 `<标题>/` 目录，互不影响。
- 处理完一个视频再开始下一个；不要交叉并行，避免上下文与产物混淆。
- 得益于幂等，中途失败或中断后可只重跑失败的视频/阶段，已完成的视频跳过。
- 全部结束后汇总一张清单：每个视频的最终 mp4 路径 + 成功/失败状态；失败项附原因。
- 注意：烧录耗时较长，视频越多总时长越久；翻译 token 成本随视频数线性叠加。

## 步骤详解

### 1. 下载

运行 `download.py <URL>`。它会：

- 校验工具、拉取元数据（标题、简介、语言）；
- 下载 ≤1080P 的 mp4（`video.mp4`）、封面（`cover.jpg`）、词级 json3 字幕（`subtitle.json3`）、元数据（`info.json`）；
- 若找不到可下载的 json3 字幕，直接报错退出。

已存在的产物会跳过（除非加 `--force`）。

### 2. 断句

运行 `segment.py <项目目录>`。它会解析 `subtitle.json3`，清洗滚动重复词，切成**细粒度原子片段（atoms，每个约几个词）**，输出 `raw_segments.json`：

```json
{ "source_mode": "word|event",
  "atoms": [ { "i": 0, "start": 1200, "end": 2000, "text": "so today" }, { "i": 1, "start": 2000, "end": 2600, "text": "were going to" }, ... ] }
```

`start`/`end` 为毫秒。atoms 故意切得很碎、**不承担语义断句**——语义断句、标点恢复、长句拆分、短句合并全部由你在下一步完成。atoms 越碎，你切分 cue 的自由度越高。

### 3. 翻译（AI 执行——这是你的职责）

读取 `<标题>/raw_segments.json` 与 `<标题>/info.json`。以视频标题、简介为上下文，把细碎 atoms 重新组织成一条条字幕（cue），产出 `<标题>/segments.json`：

```json
{
  "segments": [
    {
      "atoms": [0, 2],
      "source": "So today, we're going to build a small app.",
      "translation": "那么今天，我们要做一个小应用。"
    },
    { "atoms": [3, 3], "source": "It won't take long.", "translation": "不会花太久。" },
    { "atoms": [4, 4], "source": "[Music]", "translation": "" }
  ]
}
```

要求：

- **用 atom 区间表示时间，不要自己算时间**：每个 cue 的 `atoms` 写 `[起始索引, 结束索引]`（含两端的连续区间）。脚本按 `atoms[起始].start` 到 `atoms[结束].end` 推导时间。若区间只含一个 atom，写 `[i, i]`。
- **完整覆盖、不重叠、不遗漏**：所有 cue 的 atom 区间必须首尾相接地覆盖全部 atoms（前一个 cue 的结束索引 + 1 = 下一个 cue 的起始索引）。
- **语义断句（核心）**：
  - 一个 cue 只放**一句完整的话**；**绝不要把两句完整的话塞进同一个 cue**。
  - **长句要拆**：一句话太长时拆成多个 cue，在从句/连词/语义停顿处切，别切在短语中间（如冠词+名词、介词+宾语不要拆开）。
  - **碎句要合**：把过短的 atom 合并成通顺的一句。
  - `source` 写恢复大小写与标点后的原文。
- **长度上限（可读性）**：单个 cue 原文尽量 ≤ ~70 字符、中文 ≤ ~28 字（约两行）；超过就再拆成多个 cue。
- **翻译**：`translation` 为地道中文，保留专有名词/数字；结合标题与简介保证术语一致。
- **分批处理**：每批约 30–50 个 cue 读入、翻译、增量写回，避免上下文过长；跨批保持术语统一。
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
