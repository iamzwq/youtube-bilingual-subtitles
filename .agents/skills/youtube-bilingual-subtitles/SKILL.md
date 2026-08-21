---
name: youtube-bilingual-subtitles
description: "制作 YouTube 双语（中文+原文）字幕视频。当用户说“制作<youtube链接>双语字幕视频”、“给这个 YouTube 视频加中文双语字幕”、“bilingual subtitles for youtube”等类似请求时使用。流程：yt-dlp 下载视频/封面/词级 json3 字幕 → 清洗断句 → AI 断句并翻译成中文 → 生成 ASS 双语字幕 → ffmpeg 烧录 1080P 视频。"
argument-hint: "<YouTube 视频链接>"
---

# YouTube 双语字幕视频

把一个 YouTube 视频制作成「中文在上、原文在下」的双语字幕视频。最终产出：烧录好字幕的 1080P mp4、双语 ASS 字幕、封面图、原始词级 json3 字幕。

## 执行纪律（省 Token）

- **只有第 3 步（翻译/断句）需要 AI 推理，其余步骤是纯执行**：不要额外验证。
  - 不分析脚本输出日志、不 `ffprobe`、不截图读图、不做像素/帧对比、不反复 `ls` 检查。
  - 脚本参数（分辨率/字体/字号/透明度/背景等）已内置，不要干预、不要解释。
  - **脚本退出码 0 / 输出 `[done]` 即视为通过**，直接进入下一步；仅当脚本打出 `[warn]/[error]` 时才介入。
  - **例外——断句回修闭环**：`build_ass.py` 若打印字幕"过长/阅读过快/以悬挂词结尾"的 `[warn]`，**必须回到第 3 步**，按硬规则重切被点名的 cue、覆盖写回 `segments.json`，再重跑 `build_ass.py`，直到不再报此类 `[warn]`。

## 前置条件

- PATH 已装 `python`、`yt-dlp`、`ffmpeg`（脚本仅用标准库，无第三方依赖）。`$PY` 指 python 命令：mac/Linux=`python3`，Windows=`python`。
- 字体「霞鹜文楷等宽 / LXGW WenKai Mono」建议已装，缺失则回退系统默认。
- 仅支持带可下载 json3 字幕的公开视频；无字幕会报错退出。

## 管线总览（脚本 ↔ AI 交替，各阶段幂等可重跑）

设脚本目录为 `SK=.agents/skills/youtube-bilingual-subtitles/scripts`，`$PY` 为 python 命令（mac/Linux=`python3`，Windows=`python`）。所有产物落在当前目录下的 `<清洗后标题>/`。

1. 下载：`$PY $SK/download.py "<URL>"`
2. 断句：`$PY $SK/segment.py "<标题>/"`
3. 翻译（由你，AI，完成，见下）
4. 生成字幕：`$PY $SK/build_ass.py "<标题>/"`
5. 烧录：`$PY $SK/burn.py "<标题>/"`

`download.py` 会在结尾打印实际的项目目录路径 `<标题>/`，后续命令直接复用该路径。

## 批量处理（多个链接）

多个链接时**逐个串行**跑完整 1–5 步：每个视频独立 `<标题>/` 目录，不并行；失败可只重跑该视频/阶段；全部结束后汇总各视频最终 mp4 路径与成功/失败状态。

## 步骤详解

### 1. 下载

运行 `download.py <URL>`：下载 ≤1080P 的 `video.mp4`、`cover.jpg`、词级 `subtitle.json3`（优先自动字幕，缺失才回退人工字幕）、`info.json`。已存在的产物跳过（`--force` 覆盖）。

### 2. 断句

运行 `segment.py <项目目录>`。它会解析 `subtitle.json3`，清洗滚动重复词，切成**细粒度原子片段（atoms，每个约几个词）**，输出 `raw_segments.json`：

```json
{ "source_mode": "word|event",
  "atoms": [
    { "i": 0, "start": 80, "end": 1599, "text": "Today's video is sponsored by Hexrays." },
    { "i": 1, "start": 1839, "end": 3679, "text": "Whether you're a cyber security analyst or somebody" },
    { "i": 2, "start": 3679, "end": 5759, "text": "who likes to program, learning how to reverse" }, ... ] }
```

`start`/`end` 为毫秒。atoms 故意切碎、**不做语义断句**；断句/拆长/合短全部由你在下一步完成。

### 3. 翻译（AI 执行——这是你的职责）

#### 3a. 先建术语表（`glossary.json`）

正式翻译前，先通读 `<标题>/info.json`（标题+简介）与 `raw_segments.json` 全文，提取会反复出现、需统一译法的**关键术语**（专有名词、人名/产品名、专业词、缩略语），产出 `<标题>/glossary.json`：

```json
{
  "terms": [
    { "src": "reverse engineering", "zh": "逆向工程" },
    { "src": "CTF", "zh": "夺旗赛（CTF）" },
    { "src": "binary", "zh": "二进制文件" }
  ]
}
```

- 只收**真正需要统一**的术语，普通词不必收；一般 10–40 条即可。
- `glossary.json` 会被缓存；已存在则直接复用，不必重建。

#### 3b. 断句 + 翻译（产出 `segments.json`）【非常重要，务必严格按下述要求执行】

读取 `raw_segments.json`、`info.json` 与上一步的 `glossary.json`，把细碎 atoms 重新组织成一条条字幕（cue），产出 `<标题>/segments.json`。**你只决定“断句”和“翻译”：英文原文行由脚本按 atom 逐词重建，你无需输出英文**：

```json
{
  "segments": [
    { "atoms": [24, 25], "translation": "flag 能给我们积分，而积分让我很有成就感。" },
    { "atoms": [26, 27], "translation": "那么，我们下载这个文件，看看会惹上什么麻烦。" },
    { "atoms": [28, 29], "translation": "那么，什么是逆向工程呢？" }
  ]
}
```

> 英文行由脚本按 atom 逐词拼接，你无需输出。上例 `[24,25]`/`[26,27]` 各是一句独立话各自成 cue，`[28,29]` 把碎片 `right?`（≤3 词）并入前句。自动字幕有时小写无标点，属正常。

要求：

- **用 atom 区间表示时间，不要自己算时间**：每个 cue 的 `atoms` 写 `[起始索引, 结束索引]`（含两端的连续区间）。脚本按 `atoms[起始].start` 到 `atoms[结束].end` 推导时间。若区间只含一个 atom，写 `[i, i]`。
- **完整覆盖、不重叠、不遗漏**：所有 cue 的 atom 区间必须首尾相接地覆盖全部 atoms（前一个 cue 的结束索引 + 1 = 下一个 cue 的起始索引）。
- **语义断句（核心，硬规则，必须严格执行）**：
  - 一个 cue 只放**一个短句或一个子句**；**绝不把两句完整的话、或两个独立子句塞进同一个 cue**。
  - **停顿即断（最高优先级，不是"建议"而是"默认必断"）**：只要出现下列边界，就**必须**在该处断成两个 cue——不需要先凑够词数：
    1. 句末标点（`. ! ?` / `。！？`）之后；
    2. 句中停顿：逗号、分号、冒号之后；
    3. 并列/从属连词（and / but / or / so / because / when / while / if / which / that）**之前**。
  - **唯一免断例外**：若在某个边界断开后，**某一侧片段 ≤3 个词**（依 atom 英文词数判断），才可以不在此处断、把它并入相邻片段。除此之外，遇到上述边界一律断。
  - **不要拆碎短语**：cue **不要以这些词结尾**（冠词 a/an/the、介词 of/in/on/at/to/for/with/from、连词 and/but/or/so、关系词 that/which/who）；也**不要以介词/冠词开头**（除非它是整句第一个词）。此规则优先于"停顿即断"：若某个边界会产生悬挂词，则顺延到下一个合适边界。
  - **长度**：不设"凑够多少词才断"的下限；自然子句多短就多短。**硬上限 12 词 / 单条 ≤5 秒**，任何 cue 超过必须继续拆分。
- **翻译**：`translation` 为地道中文，保留专有名词/数字。中文译文也随 cue **一句一断**：一个 cue 只对应一个短子句的译文，不要在一个 cue 的译文里出现多个句号。
- **术语一致**：翻译时严格套用 `glossary.json` 里的固定译法；遇到表中术语一律用表中的中文。
- **分批处理 + 跨批上下文**：每批约 30–50 个 cue 读入、翻译、增量写回；每批开始时带上 `glossary.json` 和**上一批最后 1–2 条 cue** 作为上下文，保证批与批之间术语与语气连贯。
- **写回前自检（强制）**：每批写回 `segments.json` 前，逐条检查——① 是否有 cue 含多个完整句或多个独立子句；② 是否有 cue 超过 12 词或对应时长 >5 秒；③ 是否有 cue 以悬挂词结尾。发现任一项立即按上面的硬规则拆分/调整后再写回。
- **非语音内容**（如 `[Music]`、`[Applause]`、`♪`）：`translation` 留空字符串。
- 严格输出上述 JSON 结构，UTF-8，无多余注释。

`segments.json` 会被缓存：若只想改样式/重烧录，不必重做翻译。

### 4. 生成 ASS 字幕

运行 `build_ass.py <项目目录>`，读取 `segments.json` + `raw_segments.json` 生成 `subtitle.ass`：中文 `fs60` 在上、原文 `fs36` 在下，黑底半透明，底部居中。样式细节见 [ass-style.md](./references/ass-style.md)。

### 5. 烧录

运行 `burn.py <项目目录>`：烧录字幕、缩放到 1080P（只降不升）、按平台自动选加速编码器（CQ 质量模式）。`--dry-run` 可先看命令。产物：`<标题> [视频ID].mp4`。

## 最终产物（`<标题>/`）

- `<标题> [视频ID].mp4`：烧录双语字幕的视频
- `subtitle.ass`：双语字幕
- `cover.jpg`：封面图
- `subtitle.json3`：原始词级字幕

## 参考

- ASS 样式细节见 [ass-style.md](./references/ass-style.md)
- 断句/原子化设计取舍见 [segmentation-design.md](./references/segmentation-design.md)
