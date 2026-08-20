#!/usr/bin/env python3
"""用 ffmpeg 把 ASS 字幕烧录进视频，缩放到 1080P，并自动选择加速编码器。"""
import argparse
import platform
import subprocess
import sys
from pathlib import Path

# 仅降不升：源高度 > 1080 才缩放；filtergraph 内逗号需转义
VIDEO_FILTER = r"scale=w=-2:h=min(1080\,ih),subtitles=subtitle.ass"

ENCODER_ARGS = {
    "h264_videotoolbox": ["-c:v", "h264_videotoolbox", "-b:v", "6M"],
    "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p5", "-b:v", "6M"],
    "h264_qsv": ["-c:v", "h264_qsv", "-b:v", "6M"],
    "h264_amf": ["-c:v", "h264_amf", "-b:v", "6M"],
    "libx264": ["-c:v", "libx264", "-preset", "medium", "-crf", "20"],
}


def available_encoders() -> set:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                       text=True, capture_output=True)
    return {name for name in ENCODER_ARGS if name in r.stdout}


def choose_encoder(avail: set) -> str:
    system = platform.system()
    order = []
    if system == "Darwin":
        order = ["h264_videotoolbox"]
    elif system == "Windows":
        order = ["h264_nvenc", "h264_qsv", "h264_amf"]
    else:
        order = ["h264_nvenc", "h264_qsv"]
    for enc in order:
        if enc in avail:
            return enc
    return "libx264"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--encoder", help="强制指定编码器")
    ap.add_argument("--dry-run", action="store_true", help="只打印编码器与命令")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    proj = Path(args.project).resolve()
    video = proj / "video.mp4"
    ass = proj / "subtitle.ass"
    for f in (video, ass):
        if not f.exists():
            sys.exit(f"[error] 未找到 {f}")

    # 目录名已是清洗后的标题，直接复用作输出文件名，避免非法字符
    out_name = proj.name + ".mp4"

    encoder = args.encoder or choose_encoder(available_encoders())
    print(f"[info] 平台={platform.system()} 选用编码器={encoder}")

    cmd = ["ffmpeg", "-y", "-i", "video.mp4", "-vf", VIDEO_FILTER,
           *ENCODER_ARGS[encoder], "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_name]

    print("[cmd]", " ".join(cmd))
    if args.dry_run:
        return

    if (proj / out_name).exists() and not args.force:
        print(f"[skip] {out_name} 已存在（--force 覆盖）")
        return

    # 以项目目录为 cwd，用相对文件名规避 Windows 下 subtitles 滤镜的路径转义问题
    r = subprocess.run(cmd, cwd=str(proj))
    if r.returncode != 0:
        sys.exit("[error] ffmpeg 烧录失败。")
    print(f"[done] {proj / out_name}")


if __name__ == "__main__":
    main()
