#!/usr/bin/env python3
"""用 ffmpeg 把 ASS 字幕烧录进视频，缩放到 1080P，并自动选择加速编码器。"""
import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

# 仅降不升：源高度 > 1080 才缩放；filtergraph 内逗号需转义
VIDEO_FILTER = r"scale=w=-2:h=min(1080\,ih),subtitles=subtitle.ass"

# 编码器 -> 是否走码率控制（True）。libx264 用 CRF 恒定质量
ENCODERS = {
    "h264_videotoolbox": True,
    "h264_nvenc": True,
    "h264_qsv": True,
    "h264_amf": True,
    "libx264": False,
}


def available_encoders() -> set:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                       text=True, capture_output=True)
    return {name for name in ENCODERS if name in r.stdout}


def probe_video_size(video: Path):
    """探测宽/高/帧率，失败回退 (1920, 1080, 24)。"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,r_frame_rate",
             "-of", "csv=p=0", str(video)],
            capture_output=True, check=True, text=True)
        w, h, fps = r.stdout.strip().split(",")[:3]
        num, _, den = fps.partition("/")
        rate = float(num) / (float(den) if den and float(den) else 1.0)
        return int(w), int(h), rate or 24.0
    except Exception:
        return 1920, 1080, 24.0


def encoder_args(encoder: str, bitrate: int) -> list:
    if not ENCODERS.get(encoder, False):
        return ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]
    args = ["-c:v", encoder]
    if encoder == "h264_nvenc":
        args += ["-preset", "p5"]
    args += ["-b:v", str(bitrate),
             "-maxrate", str(int(bitrate * 1.5)),
             "-bufsize", str(int(bitrate * 3))]
    return args


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

    # 目录名已是清洗后的标题；文件名追加视频 ID（YouTube ID 为安全字符）
    vid = ""
    info = proj / "info.json"
    if info.exists():
        vid = (json.loads(info.read_text(encoding="utf-8")).get("id") or "").strip()
    out_name = f"{proj.name} [{vid}].mp4" if vid else proj.name + ".mp4"

    encoder = args.encoder or choose_encoder(available_encoders())
    w, h, fps = probe_video_size(video)
    out_h = min(1080, h)
    out_w = round(w * out_h / h) if h else 1920
    bitrate = max(6_000_000, int(out_w * out_h * fps * 0.1))
    print(f"[info] 平台={platform.system()} 编码器={encoder} 目标≈{out_w}x{out_h}@{fps:.0f} 码率≈{bitrate // 1000}k")

    cmd = ["ffmpeg", "-y", "-i", "video.mp4", "-vf", VIDEO_FILTER,
           "-map", "0:v:0", "-map", "0:a:0?",
           *encoder_args(encoder, bitrate), "-pix_fmt", "yuv420p",
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
