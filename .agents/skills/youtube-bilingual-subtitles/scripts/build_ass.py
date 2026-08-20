#!/usr/bin/env python3
"""由 segments.json + raw_segments.json 生成双语 ASS 字幕。"""
import argparse
import json
import sys
from pathlib import Path

MIN_DUR_MS = 1000     # 每条字幕最短显示时长
GAP_GUARD_MS = 10     # 相邻字幕之间保留的最小间隔

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CN,霞鹜文楷等宽,60,&H00FFFFFF,&H000000FF,&H26000000,&H00000000,0,0,0,0,100,100,0,0,3,6,0,2,80,80,131,1
Style: EN,霞鹜文楷等宽,36,&H00FFFFFF,&H000000FF,&H26000000,&H00000000,0,0,0,0,100,100,0,0,3,6,0,2,80,80,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ts(ms: int) -> str:
    ms = max(0, int(ms))
    cs = (ms + 5) // 10
    s, cs = divmod(cs, 100)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def esc(text: str) -> str:
    return (text.replace("{", "｛").replace("}", "｝")
                .replace("\\", "＼").replace("\r", "").replace("\n", " ").strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    args = ap.parse_args()

    proj = Path(args.project)
    seg_file = proj / "segments.json"
    raw_file = proj / "raw_segments.json"
    for f in (seg_file, raw_file):
        if not f.exists():
            sys.exit(f"[error] 未找到 {f}")

    atoms = {a["i"]: a for a in json.loads(raw_file.read_text(encoding="utf-8"))["atoms"]}
    segments = json.loads(seg_file.read_text(encoding="utf-8"))["segments"]

    rows = []
    for seg in segments:
        idx = [i for i in seg.get("atoms", []) if i in atoms]
        if not idx:
            continue
        start = min(atoms[i]["start"] for i in idx)
        end = max(atoms[i]["end"] for i in idx)
        if end - start < MIN_DUR_MS:
            end = start + MIN_DUR_MS
        rows.append([start, end, (seg.get("source") or "").strip(),
                     (seg.get("translation") or "").strip()])

    rows.sort(key=lambda r: r[0])
    for i in range(len(rows) - 1):
        if rows[i][1] > rows[i + 1][0] - GAP_GUARD_MS:
            rows[i][1] = max(rows[i][0] + 1, rows[i + 1][0] - GAP_GUARD_MS)

    lines = [ASS_HEADER]
    for start, end, src, cn in rows:
        st, en = ts(start), ts(end)
        # 中文与原文各用独立事件/样式，底部堆叠留间隙，避免两个半透明黑框重叠变深
        if cn:
            lines.append(f"Dialogue: 0,{st},{en},CN,,0,0,0,,{esc(cn)}")
        if src:
            lines.append(f"Dialogue: 0,{st},{en},EN,,0,0,0,,{esc(src)}")

    out = proj / "subtitle.ass"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[done] {out} — {len(rows)} 条字幕")
    print(f"[next] python burn.py \"{proj}\"")


if __name__ == "__main__":
    main()
