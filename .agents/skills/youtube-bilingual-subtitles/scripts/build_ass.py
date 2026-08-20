#!/usr/bin/env python3
"""由 segments.json + raw_segments.json 生成双语 ASS 字幕。"""
import argparse
import json
import sys
from pathlib import Path

MIN_DUR_MS = 1000     # 每条字幕最短显示时长
GAP_GUARD_MS = 10     # 相邻字幕之间保留的最小间隔
CPS_WARN = 25         # 原文每秒字符数上限（超出阅读吃力）
CN_CPS_WARN = 12      # 中文每秒字数上限
MAX_CUE_MS = 8000     # 单条字幕最长时长
DANGLING_WORDS = {    # cue 不宜以这些词结尾（会割裂短语）
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "with",
    "from", "and", "but", "or", "so", "that", "which", "who",
}

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


def validate_coverage(atoms: dict, segments: list) -> None:
    """校验 LLM 的 atom 区间是否连续覆盖全部 atoms，发现缺口/重叠/越界即告警。"""
    all_idx = set(atoms)
    seen, out_of_range = {}, set()
    for seg in segments:
        a = seg.get("atoms") or []
        if not a:
            continue
        for i in range(min(a), max(a) + 1):
            seen[i] = seen.get(i, 0) + 1
            if i not in all_idx:
                out_of_range.add(i)
    missing = sorted(all_idx - set(seen))
    overlap = sorted(i for i, c in seen.items() if c > 1)
    for label, data in (("缺失(内容会丢)", missing),
                        ("重叠", overlap),
                        ("越界索引", sorted(out_of_range))):
        if data:
            preview = ", ".join(map(str, data[:10])) + (" ..." if len(data) > 10 else "")
            print(f"[warn] atom {label}: 共 {len(data)} 个 → {preview}")


def readability_warn(rows: list) -> None:
    """对过长/阅读过快的字幕告警（路线B 由 LLM 控制长度，这里只做兵底提醒）。"""
    too_long = too_fast = dangling = 0
    for start, end, src, cn in rows:
        dur = max((end - start) / 1000, 0.1)
        if end - start > MAX_CUE_MS:
            too_long += 1
        if len(src) / dur > CPS_WARN or (cn and len(cn) / dur > CN_CPS_WARN):
            too_fast += 1
        words = src.split()
        if words and words[-1].strip(".,;:!?\"')(").lower() in DANGLING_WORDS:
            dangling += 1
    if too_long:
        print(f"[warn] {too_long} 条字幕时长 > {MAX_CUE_MS // 1000}s，建议让 LLM 拆短")
    if too_fast:
        print(f"[warn] {too_fast} 条字幕阅读速度过快（超 CPS 阈值），建议让 LLM 拆短/合并")
    if dangling:
        print(f"[warn] {dangling} 条字幕以冠词/介词/连词结尾（断句易割裂短语），建议让 LLM 调整")


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

    validate_coverage(atoms, segments)

    rows = []
    for seg in segments:
        idx = [i for i in seg.get("atoms", []) if i in atoms]
        if not idx:
            continue
        lo, hi = min(idx), max(idx)
        start, end = atoms[lo]["start"], atoms[hi]["end"]
        if end - start < MIN_DUR_MS:
            end = start + MIN_DUR_MS
        # 英文原文由脚本按 atom 逐词重建，保证与原字幕逐词一致
        src = " ".join(atoms[i]["text"] for i in range(lo, hi + 1) if i in atoms)
        rows.append([start, end, " ".join(src.split()),
                     (seg.get("translation") or "").strip()])

    rows.sort(key=lambda r: r[0])
    for i in range(len(rows) - 1):
        if rows[i][1] > rows[i + 1][0] - GAP_GUARD_MS:
            rows[i][1] = max(rows[i][0] + 1, rows[i + 1][0] - GAP_GUARD_MS)

    readability_warn(rows)

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
    burn_script = Path(__file__).with_name("burn.py")
    print(f"[done] {out} — {len(rows)} 条字幕")
    print(f'[next] 烧录（用 python3/python 运行）: "{burn_script}" "{proj}"')


if __name__ == "__main__":
    main()
