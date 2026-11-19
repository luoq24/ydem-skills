"""自动裁剪 NVIDIA 录屏中的游戏画面。

示例：
    python scripts/crop_game_view.py recording.mp4
    python scripts/crop_game_view.py recording.mp4 --preview ../../_temp/game_view_preview.png --dry-run
    python scripts/crop_game_view.py recording.mp4 --crop 320:120:1280:720
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from game_view_detector import (
    DetectionError,
    crop_video,
    detect_game_region,
    make_preview,
    manual_region,
    probe_video,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="自动检测并裁剪录屏中的游戏画面区域。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", help="输入视频文件")
    parser.add_argument("-o", "--output", help="输出视频路径，默认在原视频旁生成 *_game.mp4")
    parser.add_argument(
        "--crop",
        help="手动指定裁切区域，格式 X:Y:W:H；指定后跳过自动检测",
    )
    parser.add_argument(
        "--method",
        choices=("auto", "activity", "spatial"),
        default="auto",
        help="自动检测方式：activity=连续帧变化，spatial=首帧静态分析",
    )
    parser.add_argument(
        "--scan-seconds",
        type=float,
        default=20.0,
        help="扫描开头的秒数，用于跳过黑屏并寻找游戏画面",
    )
    parser.add_argument(
        "--sample-fps",
        type=float,
        default=2.0,
        help="检测时每秒抽取的帧数",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=0,
        help="在检测区域四周额外保留的像素数",
    )
    parser.add_argument("--preview", help="输出一张画有红色裁切框的预览图；临时预览图请输出到工作区根目录 _temp/")
    parser.add_argument("--dry-run", action="store_true", help="只检测并打印结果，不生成视频")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式打印检测结果")
    parser.add_argument("--crf", type=int, default=18, help="x264 视频质量，数值越小质量越高")
    parser.add_argument(
        "--preset",
        default="veryfast",
        help="x264 编码预设，例如 veryfast / medium / slow",
    )
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已存在的输出文件")
    return parser


def default_output(info, suffix: str = "_game") -> Path:
    return info.path.with_name(f"{info.path.stem}{suffix}{info.path.suffix or '.mp4'}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.scan_seconds <= 0:
            raise DetectionError("--scan-seconds 必须大于 0。")
        if args.sample_fps <= 0:
            raise DetectionError("--sample-fps 必须大于 0。")
        if args.padding < 0:
            raise DetectionError("--padding 不能为负数。")

        info = probe_video(args.input)
        if args.crop:
            try:
                region = manual_region(info, args.crop, padding=args.padding)
            except ValueError as exc:
                raise DetectionError(str(exc)) from exc
            frame_time = 0.0
            method = "manual"
            confidence = "manual"
            notes = ""
        else:
            result = detect_game_region(
                info.path,
                scan_seconds=args.scan_seconds,
                sample_fps=args.sample_fps,
                method=args.method,
                padding=args.padding,
            )
            region = result.region
            frame_time = result.frame_time
            method = result.method
            confidence = result.confidence
            notes = result.notes

        if args.preview:
            make_preview(info, region, args.preview, frame_time=frame_time)

        if args.json:
            payload = {
                "input": str(info.path),
                "video": {
                    "width": info.width,
                    "height": info.height,
                    "duration": round(info.duration, 3),
                    "fps": round(info.fps, 3),
                    "has_audio": info.has_audio,
                },
                "crop": region.to_dict(),
                "crop_filter": region.ffmpeg_filter(),
                "method": method,
                "frame_time": round(frame_time, 3),
                "confidence": confidence,
                "notes": notes,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"源视频: {info.width}x{info.height}, {info.fps:.2f} fps")
            if method != "manual":
                print(f"检测帧: {frame_time:.3f}s")
            print(
                f"裁切区域: x={region.x}, y={region.y}, "
                f"w={region.w}, h={region.h} ({region.w}x{region.h})"
            )
            print(f"检测方式: {method}，置信度: {confidence}")
            if notes:
                print(f"说明: {notes}")
            if args.preview:
                print(f"预览图: {Path(args.preview).expanduser().resolve()}")

        if args.dry_run:
            return 0

        output = Path(args.output).expanduser().resolve() if args.output else default_output(info)
        if not output.suffix:
            output = output.with_suffix(".mp4")
        if output.exists() and not args.overwrite:
            raise DetectionError(
                f"输出文件已存在：{output}\n如需覆盖，请加 --overwrite，或用 -o 指定新路径。"
            )

        final_path = crop_video(
            info,
            region,
            output,
            crf=args.crf,
            preset=args.preset,
        )
        print(f"已输出: {final_path}")
        return 0
    except DetectionError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
