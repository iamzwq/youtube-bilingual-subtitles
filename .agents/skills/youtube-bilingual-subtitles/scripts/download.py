#!/usr/bin/env python3
"""下载 YouTube 视频、封面、词级 json3 字幕与元数据。"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_FORMAT = (
    "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
    "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
)


def run(cmd, capture=False):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, text=True,
                          capture_output=capture)


def sanitize(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", name)
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    return name[:120] or "video"


def load_metadata(url: str) -> dict:
    r = run(["yt-dlp", "-J", "--no-download", url], capture=True)
    if r.returncode != 0:
        sys.exit(f"[error] 获取视频元数据失败:\n{r.stderr}")
    meta = json.loads(r.stdout)
    if meta.get("_type") == "playlist" or "entries" in meta:
        entries = [e for e in meta.get("entries", []) if e]
        if not entries:
            sys.exit("[error] 链接是空播放列表。请提供单个视频链接。")
        print("[warn] 链接是播放列表，只处理第一个视频。")
        meta = entries[0]
    return meta


def pick_language(meta: dict):
    subs = meta.get("subtitles") or {}
    autos = meta.get("automatic_captions") or {}
    prefer = [meta.get("language"), "en", "en-US", "en-GB", "en-orig"]
    for lang in prefer:
        if lang and (lang in subs or lang in autos):
            return lang
    for d in (subs, autos):
        if d:
            return sorted(d)[0]
    return None


def download_subtitle(url: str, lang: str, proj: Path) -> bool:
    """优先手动字幕（文本更干净），回退自动字幕（含词级时间）。"""
    target = proj / "subtitle.json3"
    for auto_flag in ("--write-subs", "--write-auto-subs"):
        for f in proj.glob("sub.*.json3"):
            f.unlink()
        run(["yt-dlp", auto_flag, "--sub-langs", lang, "--sub-format",
             "json3", "--skip-download", "-o", str(proj / "sub.%(ext)s"), url])
        found = sorted(proj.glob("sub.*.json3"))
        if found:
            found[0].replace(target)
            for extra in found[1:]:
                extra.unlink()
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--output-root", default=".")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    for tool in ("yt-dlp", "ffmpeg"):
        if not shutil.which(tool):
            sys.exit(f"[error] 未在 PATH 中找到 {tool}")
    print("[preflight] yt-dlp", run(["yt-dlp", "--version"], capture=True).stdout.strip())

    meta = load_metadata(args.url)
    title = meta.get("title") or meta.get("id") or "video"
    proj = Path(args.output_root) / sanitize(title)
    proj.mkdir(parents=True, exist_ok=True)

    lang = pick_language(meta)
    if not lang:
        sys.exit("[error] 该视频没有任何可用字幕，无法制作双语字幕。")
    print(f"[info] 选用字幕语言: {lang}")

    info = {
        "title": title,
        "description": meta.get("description") or "",
        "id": meta.get("id"),
        "webpage_url": meta.get("webpage_url") or args.url,
        "language": lang,
        "duration": meta.get("duration"),
        "uploader": meta.get("uploader"),
    }
    (proj / "info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")

    sub = proj / "subtitle.json3"
    if sub.exists() and not args.force:
        print("[skip] subtitle.json3 已存在")
    elif not download_subtitle(args.url, lang, proj):
        sys.exit("[error] 未找到可下载的 json3 字幕，无法继续（不支持无字幕视频）。")

    video = proj / "video.mp4"
    if video.exists() and not args.force:
        print("[skip] video.mp4 已存在")
    else:
        run(["yt-dlp", "-f", VIDEO_FORMAT, "--merge-output-format", "mp4",
             "-o", str(proj / "video.%(ext)s"), args.url])
        if not video.exists():
            picked = next((p for p in proj.glob("video.*")), None)
            if picked:
                picked.replace(video)
        if not video.exists():
            sys.exit("[error] 视频下载失败。")

    cover = proj / "cover.jpg"
    if cover.exists() and not args.force:
        print("[skip] cover.jpg 已存在")
    else:
        run(["yt-dlp", "--write-thumbnail", "--skip-download",
             "--convert-thumbnails", "jpg",
             "-o", str(proj / "cover.%(ext)s"), args.url])
        if not cover.exists():
            picked = next((p for p in proj.glob("cover.*")
                           if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")), None)
            if picked:
                picked.replace(cover)

    print(f"\n[done] 项目目录: {proj}")
    print(f"[next] python segment.py \"{proj}\"")


if __name__ == "__main__":
    main()
