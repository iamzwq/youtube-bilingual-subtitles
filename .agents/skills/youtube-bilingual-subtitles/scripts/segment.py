#!/usr/bin/env python3
"""解析 json3 字幕，清洗并切成细粒度原子(atoms)；语义断句/合并/拆分交由 LLM 完成。"""
import argparse
import json
import re
import sys
from pathlib import Path

GAP_MS = 400          # 词间停顿超过该值则切分
MAX_WORDS = 8         # 单个 atom 最大词数
MAX_CHARS = 45        # 单个 atom 最大字符数
MAX_DUR_MS = 3000     # 单个 atom 最大时长
SENT_END = (".", "!", "?", "。", "！", "？", "…")


def load_events(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("events", []) or []


def has_word_timing(events: list) -> bool:
    for ev in events:
        for s in ev.get("segs", []) or []:
            if "tOffsetMs" in s and (s.get("utf8", "").strip()):
                return True
    return False


def collect_words(events: list):
    tokens = []
    for ev in events:
        segs = ev.get("segs")
        if not segs:
            continue
        base = ev.get("tStartMs", 0)
        for s in segs:
            text = s.get("utf8", "")
            if not text or text == "\n":
                continue
            tokens.append((base + s.get("tOffsetMs", 0), text))
    seen, uniq = set(), []
    for ms, text in tokens:
        key = (ms, text)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((ms, text))
    uniq.sort(key=lambda x: x[0])
    return uniq


def atoms_from_words(words) -> list:
    atoms, cur = [], []

    def flush():
        if not cur:
            return
        text = re.sub(r"\s+", " ", "".join(t for _, t in cur)).strip()
        if text:
            atoms.append({"start": cur[0][0], "_last": cur[-1][0], "text": text})

    for ms, text in words:
        if cur:
            cur_text = "".join(t for _, t in cur)
            if (ms - cur[-1][0] > GAP_MS or len(cur) >= MAX_WORDS
                    or len(cur_text) >= MAX_CHARS
                    or ms - cur[0][0] >= MAX_DUR_MS
                    or cur_text.rstrip().endswith(SENT_END)):
                flush()
                cur = []
        cur.append((ms, text))
    flush()

    for i, a in enumerate(atoms):
        nxt = atoms[i + 1]["start"] if i + 1 < len(atoms) else None
        est = a["start"] + max(1000, len(a["text"]) * 75)
        a["end"] = min(nxt, est) if nxt else est
        if a["end"] <= a["start"]:
            a["end"] = a["start"] + 800
        del a["_last"]
    return atoms


def chunk_text(text: str) -> list:
    """按最大词数/字符数把一段文本切成细粒度块，便于 LLM 自由断句。"""
    chunks, cur = [], []
    for w in text.split():
        cur.append(w)
        cur_text = " ".join(cur)
        if (len(cur) >= MAX_WORDS or len(cur_text) >= MAX_CHARS
                or cur_text.rstrip().endswith(SENT_END)):
            chunks.append(cur_text)
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    return chunks or [text]


def atoms_from_events(events: list) -> list:
    atoms = []
    for ev in events:
        segs = ev.get("segs")
        if not segs:
            continue
        text = re.sub(r"\s+", " ", "".join(s.get("utf8", "") for s in segs)).strip()
        if not text:
            continue
        start = ev.get("tStartMs", 0)
        dur = ev.get("dDurationMs") or max(1200, len(text) * 75)
        end = start + dur
        chunks = chunk_text(text)
        total = sum(len(c) for c in chunks) or 1
        acc, cursor = 0, start
        for k, c in enumerate(chunks):
            acc += len(c)
            boundary = end if k == len(chunks) - 1 else start + round((end - start) * acc / total)
            atoms.append({"start": cursor, "end": max(cursor + 200, boundary), "text": c})
            cursor = boundary
    return atoms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project", help="项目目录 <标题>/")
    args = ap.parse_args()

    proj = Path(args.project)
    sub = proj / "subtitle.json3"
    if not sub.exists():
        sys.exit(f"[error] 未找到 {sub}")

    events = load_events(sub)
    if not events:
        sys.exit("[error] json3 字幕为空。")

    if has_word_timing(events):
        mode = "word"
        atoms = atoms_from_words(collect_words(events))
    else:
        mode = "event"
        atoms = atoms_from_events(events)

    for i, a in enumerate(atoms):
        a["i"] = i
    atoms = [{"i": a["i"], "start": a["start"], "end": a["end"], "text": a["text"]}
             for a in atoms]

    out = proj / "raw_segments.json"
    out.write_text(json.dumps({"source_mode": mode, "atoms": atoms},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {out} — mode={mode}, atoms={len(atoms)}")
    print("[next] AI 读取 raw_segments.json + info.json，产出 segments.json")


if __name__ == "__main__":
    main()
