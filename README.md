# YouTube 双语字幕视频制作 SKILL

制作 YouTube 双语（中文+原文）字幕视频的 SKILL

只需跟 agent 工具说：
“制作<youtube链接>双语字幕视频” 或 “给这个 YouTube 视频加中文双语字幕”

```text
.agents/skills/youtube-bilingual-subtitles/
├── SKILL.md                 # 编排：触发词、前置条件、5步管线、AI翻译契约
├── references/
│  └── ass-style.md         # ASS 样式逐项说明 + 底框颜色渲染器差异提示
└── scripts/
    ├── download.py          # yt-dlp 下载 video/cover/subtitle.json3/info.json
    ├── segment.py           # 解析 json3 → 清洗去重 → 细粒度 atoms → raw_segments.json
    ├── build_ass.py         # segments.json+raw → subtitle.ass
    └── burn.py              # ffmpeg 烧录 1080P + 自动选编码器
```
