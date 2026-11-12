"""检测录屏中的游戏画面区域，并调用 ffmpeg 完成裁切。

依赖：Python 3.10+、numpy、ffmpeg / ffprobe。
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

SAMPLE_WIDTH = 480
SAMPLE_HEIGHT = 270
COMMON_ASPECT_RATIOS = (
    16 / 9,
    16 / 10,
    4 / 3,
    3 / 2,
    21 / 9,
    5 / 4,
    2.0,
    1.0,
)


class DetectionError(RuntimeError):
    """视频探测或区域检测失败。"""


@dataclass
class VideoInfo:
    path: Path
    width: int
    height: int
    duration: float
    fps: float
    has_audio: bool


@dataclass
class CropRegion:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}

    def ffmpeg_filter(self) -> str:
        return f"crop={self.w}:{self.h}:{self.x}:{self.y}"


@dataclass
class DetectionResult:
    info: VideoInfo
    region: CropRegion
    method: str
    frame_time: float
    confidence: str
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "input": str(self.info.path),
            "video": {
                "width": self.info.width,
                "height": self.info.height,
                "duration": round(self.info.duration, 3),
                "fps": round(self.info.fps, 3),
                "has_audio": self.info.has_audio,
            },
            "crop": self.region.to_dict(),
            "crop_filter": self.region.ffmpeg_filter(),
            "method": self.method,
            "frame_time": round(self.frame_time, 3),
            "confidence": self.confidence,
            "notes": self.notes,
        }


def _require_tools() -> None:
    if not FFMPEG:
        raise DetectionError("未找到 ffmpeg，请先安装并加入 PATH。")
    if not FFPROBE:
        raise DetectionError("未找到 ffprobe，请先安装 ffmpeg 并加入 PATH。")


def _parse_fraction(value: Optional[str], default: float) -> float:
    if not value:
        return default
    try:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            return float(numerator) / float(denominator)
        return float(value)
    except (ValueError, ZeroDivisionError):
        return default


def probe_video(path: str | Path) -> VideoInfo:
    """读取视频尺寸、时长、帧率和音轨信息。"""
    _require_tools()
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise DetectionError(f"输入视频不存在：{source}")

    command = [
        FFPROBE,
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,width,height,avg_frame_rate,r_frame_rate,duration",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(source),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if completed.returncode != 0:
        raise DetectionError(f"ffprobe 读取失败：{completed.stderr.strip()}")
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise DetectionError(f"无法解析 ffprobe 输出：{exc}") from exc

    video_stream = None
    has_audio = False
    for stream in payload.get("streams", []):
        codec_type = stream.get("codec_type")
        if codec_type == "video" and video_stream is None:
            video_stream = stream
        elif codec_type == "audio":
            has_audio = True

    if not video_stream:
        raise DetectionError("输入文件中没有视频流。")

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise DetectionError("无法获取视频分辨率。")

    fps = _parse_fraction(
        video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate"),
        30.0,
    )
    if fps <= 0 or math.isnan(fps):
        fps = 30.0

    duration = _to_float(video_stream.get("duration")) or _to_float(
        payload.get("format", {}).get("duration")
    )
    if duration <= 0:
        duration = 0.0

    return VideoInfo(
        path=source,
        width=width,
        height=height,
        duration=duration,
        fps=fps,
        has_audio=has_audio,
    )


def _to_float(value) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _read_frames(
    path: Path,
    *,
    start: float,
    duration: float,
    fps: float,
    width: int = SAMPLE_WIDTH,
    height: int = SAMPLE_HEIGHT,
) -> np.ndarray:
    """把指定时间段解码为 rgb24 原始帧，返回 (N, height, width, 3)。"""
    _require_tools()
    frame_bytes = width * height * 3
    command = [
        FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, start):.3f}",
        "-i",
        str(path),
    ]
    if duration > 0:
        command.extend(["-t", f"{duration:.3f}"])
    command.extend(
        [
            "-vf",
            f"fps={fps},scale={width}:{height}:flags=area",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        ]
    )
    completed = subprocess.run(command, capture_output=True)
    if completed.returncode != 0 and not completed.stdout:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise DetectionError(f"ffmpeg 解码失败：{stderr}")

    usable = len(completed.stdout) // frame_bytes
    if usable == 0:
        return np.empty((0, height, width, 3), dtype=np.uint8)
    data = completed.stdout[: usable * frame_bytes]
    return np.frombuffer(data, dtype=np.uint8).reshape(usable, height, width, 3)


def _read_single_frame(path: Path, time: float, width: int, height: int) -> np.ndarray:
    """按源视频分辨率读取指定时间的一帧 rgb24 图像。"""
    _require_tools()
    frame_bytes = width * height * 3
    command = [
        FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-noautorotate",
        "-ss",
        f"{max(0.0, time):.6f}",
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-pix_fmt",
        "rgb24",
        "-f",
        "rawvideo",
        "-",
    ]
    completed = subprocess.run(command, capture_output=True)
    if completed.returncode != 0 or len(completed.stdout) < frame_bytes:
        raise DetectionError("读取全分辨率帧失败。")
    data = completed.stdout[:frame_bytes]
    return np.frombuffer(data, dtype=np.uint8).reshape(height, width, 3)


def _gray(frames: np.ndarray) -> np.ndarray:
    rgb = frames.astype(np.float32)
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def _box_sum(array: np.ndarray, radius: int) -> np.ndarray:
    """用积分图计算 (2r+1)^2 窗口和，边界按 edge 复制。"""
    if radius <= 0:
        return array.astype(np.float32)
    pad = radius
    padded = np.pad(array.astype(np.float32), pad, mode="edge")
    size = 2 * radius + 1
    integral = np.pad(padded, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    return (
        integral[size:, size:]
        - integral[:-size, size:]
        - integral[size:, :-size]
        + integral[:-size, :-size]
    )


def _box_mean(array: np.ndarray, radius: int) -> np.ndarray:
    size = 2 * radius + 1
    return _box_sum(array, radius) / float(size * size)


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    return _box_sum(mask, radius) > 0


def _largest_component(mask: np.ndarray) -> tuple[int, CropRegion]:
    """返回最大连通域的像素数和包围盒；使用四连通，避免额外依赖。"""
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    best_count = 0
    best_bbox = CropRegion(0, 0, 0, 0)
    offsets = ((1, 0), (-1, 0), (0, 1), (0, -1))

    for start_y, start_x in zip(*np.nonzero(mask)):
        if visited[start_y, start_x]:
            continue
        visited[start_y, start_x] = True
        stack = [(int(start_y), int(start_x))]
        count = 0
        min_x = max_x = int(start_x)
        min_y = max_y = int(start_y)
        while stack:
            y, x = stack.pop()
            count += 1
            if x < min_x:
                min_x = x
            elif x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            elif y > max_y:
                max_y = y
            for dy, dx in offsets:
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width:
                    if mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
        if count > best_count:
            best_count = count
            best_bbox = CropRegion(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)

    return best_count, best_bbox


def _to_source_region(
    region: CropRegion,
    info: VideoInfo,
    *,
    padding: int,
    even: bool = True,
) -> CropRegion:
    """把 480×270 采样坐标映射回源视频坐标，并做边界、偶数对齐。"""
    scale_x = info.width / SAMPLE_WIDTH
    scale_y = info.height / SAMPLE_HEIGHT

    x0 = max(0, math.floor(region.x * scale_x) - padding)
    y0 = max(0, math.floor(region.y * scale_y) - padding)
    x1 = min(info.width, math.ceil((region.x + region.w) * scale_x) + padding)
    y1 = min(info.height, math.ceil((region.y + region.h) * scale_y) + padding)

    # 全屏游戏时，检测框常因边缘纹理不足缩进几个像素；贴近画面边缘时直接吸附。
    tolerance_x = max(2, int(round(info.width * 0.02)))
    tolerance_y = max(2, int(round(info.height * 0.02)))
    if x0 <= tolerance_x:
        x0 = 0
    if info.width - x1 <= tolerance_x:
        x1 = info.width
    if y0 <= tolerance_y:
        y0 = 0
    if info.height - y1 <= tolerance_y:
        y1 = info.height

    width = max(1, x1 - x0)
    height = max(1, y1 - y0)

    if even:
        x0 = x0 if x0 % 2 == 0 else max(0, x0 - 1)
        y0 = y0 if y0 % 2 == 0 else max(0, y0 - 1)
        width = width if width % 2 == 0 else min(info.width - x0, width + 1)
        height = height if height % 2 == 0 else min(info.height - y0, height + 1)
        if width % 2:
            width = max(2, width - 1)
        if height % 2:
            height = max(2, height - 1)

    width = min(width, info.width - x0)
    height = min(height, info.height - y0)
    return CropRegion(x=x0, y=y0, w=width, h=height)


def _valid_frame_index(frames: np.ndarray) -> Optional[int]:
    """找到第一帧非纯色、非全黑的画面。"""
    if frames.shape[0] == 0:
        return None
    gray = _gray(frames)
    flat = gray.reshape(gray.shape[0], -1)
    means = flat.mean(axis=1)
    stds = flat.std(axis=1)
    bright = (flat > 20).mean(axis=1)
    for index in range(frames.shape[0]):
        if stds[index] >= 5.0 and means[index] >= 8.0 and bright[index] >= 0.03:
            return index
    return None


def _snap_edge(strength: np.ndarray, current: int, search: int) -> int:
    """在当前位置附近吸附到最强的直线边缘；强度不足时保持原值。"""
    if strength.size == 0:
        return current
    low = max(0, current - search)
    high = min(strength.size - 1, current + search)
    if high < low:
        return current
    window = strength[low : high + 1]
    index = int(np.argmax(window))
    if float(window[index]) < 3.5:
        return current
    # gradient[i] 表示 i 与 i+1 之间的边缘；裁切边界取边缘右侧。
    return low + index + 1


def _refine_edges(
    gray: np.ndarray,
    region: CropRegion,
    *,
    refine_x: bool = True,
    refine_y: bool = True,
) -> CropRegion:
    """利用首帧的竖直/水平边缘，把检测框吸附到游戏视口边框。"""
    height, width = gray.shape
    x0 = max(0, min(width - 1, region.x))
    y0 = max(0, min(height - 1, region.y))
    x1 = max(x0 + 2, min(width, region.right))
    y1 = max(y0 + 2, min(height, region.bottom))
    search = max(4, min(16, int(round(min(x1 - x0, y1 - y0) * 0.12))))

    gx = np.abs(np.diff(gray, axis=1))
    gy = np.abs(np.diff(gray, axis=0))

    for _ in range(2):
        column_strength = gx[y0:y1, :].mean(axis=0)
        row_strength = gy[:, x0:x1].mean(axis=1)
        if refine_x:
            x0 = _snap_edge(column_strength, x0, search)
            x1 = _snap_edge(column_strength, x1, search)
        if refine_y:
            y0 = _snap_edge(row_strength, y0, search)
            y1 = _snap_edge(row_strength, y1, search)

    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return region
    return CropRegion(x0, y0, x1 - x0, y1 - y0)


def _edge_run(
    gradient: np.ndarray,
    column: int,
    start_y: int,
    end_y: int,
) -> Optional[tuple[int, int]]:
    """沿某一列寻找连续边界线段，用来补齐游戏视口上下边缘。"""
    if column < 0 or column >= gradient.shape[1]:
        return None
    values = gradient[:, column]
    span = values[start_y:end_y]
    if span.size == 0:
        return None
    threshold = max(2.5, float(np.percentile(span, 30)) * 0.2)
    center = (start_y + end_y) // 2
    max_gap = 3

    top = center
    gap = 0
    for y in range(center - 1, -1, -1):
        if values[y] >= threshold:
            top = y
            gap = 0
        else:
            gap += 1
            if gap > max_gap:
                break
    bottom = center
    gap = 0
    for y in range(center + 1, values.size):
        if values[y] >= threshold:
            bottom = y
            gap = 0
        else:
            gap += 1
            if gap > max_gap:
                break
    if bottom <= top:
        return None
    return top, bottom + 1


def _expand_by_side_edges(gray: np.ndarray, region: CropRegion) -> CropRegion:
    """借助游戏视口左右边缘的连续性，补上上下两侧的静态 UI。"""
    height, width = gray.shape
    if width < 2 or height < 4 or region.h <= 0:
        return region

    gradient = np.abs(np.diff(gray, axis=1))
    candidates = []
    for column in (region.x - 1, region.x, region.right - 1, region.right):
        run = _edge_run(gradient, column, region.y, region.bottom)
        if run:
            candidates.append(run)
    if not candidates:
        return region

    top, bottom = max(candidates, key=lambda item: item[1] - item[0])
    top = max(0, top)
    bottom = min(height, bottom)
    if bottom <= top:
        return region

    new_y0 = min(region.y, top)
    new_y1 = max(region.bottom, bottom)
    if (new_y1 - new_y0) > region.h * 1.6:
        return region
    if new_y0 == region.y and new_y1 == region.bottom:
        return region
    return CropRegion(region.x, new_y0, region.w, new_y1 - new_y0)


def _detect_by_activity(
    frames: np.ndarray,
    info: VideoInfo,
    valid_index: int,
    *,
    sample_fps: float,
    padding: int,
) -> Optional[tuple[CropRegion, float, str]]:
    """根据连续帧变化定位游戏画面。编辑器 UI 通常静止，游戏画面会持续变化。"""
    if frames.shape[0] - valid_index < 2:
        return None

    skip = int(round(sample_fps * 0.5))
    start = min(valid_index + skip, frames.shape[0] - 2)
    available = np.arange(start, frames.shape[0])
    selected = frames[start:]
    if selected.shape[0] > 30:
        offsets = np.linspace(0, selected.shape[0] - 1, 30).astype(int)
        available = available[offsets]
        selected = selected[offsets]
    if selected.shape[0] < 2:
        available = np.arange(valid_index, min(valid_index + 2, frames.shape[0]))
        selected = frames[valid_index : valid_index + 2]
    if selected.shape[0] < 2:
        return None

    diff = np.abs(np.diff(selected.astype(np.int16), axis=0)).mean(axis=-1)
    # 用时间均值而不是中位数：游戏画面即使只有局部在动，也能覆盖完整视口。
    activity = _box_mean(diff.mean(axis=0), 2)

    percentile = float(np.percentile(activity, 98))
    if percentile < 2.5:
        return None

    threshold = max(2.5, percentile * 0.15)
    mask = activity >= threshold
    if mask.mean() < 0.01:
        return None

    mask = _dilate(mask, 2)
    count, region = _largest_component(mask)
    if count <= 0 or region.w <= 0 or region.h <= 0:
        return None

    region_slice = diff[
        :, region.y : region.y + region.h, region.x : region.x + region.w
    ]
    if region_slice.size:
        pair_scores = region_slice.mean(axis=(1, 2))
        strongest_pair = int(np.argmax(pair_scores))
        frame_index = int(available[min(strongest_pair + 1, available.size - 1)])
    else:
        frame_index = int(available[-1])
    frame_time = frame_index / sample_fps
    sample_gray = _gray(frames[frame_index : frame_index + 1])[0]
    region = _refine_edges(sample_gray, region, refine_y=False)
    source_region = _to_source_region(region, info, padding=padding)

    # 上下两侧常常是静态游戏 UI，动态区域覆盖不到。用全分辨率帧沿左右边框
    # 追踪连续边线，可以更准确地补上顶部标题栏和底部按钮栏。
    try:
        full_gray = _gray(
            _read_single_frame(info.path, frame_time, info.width, info.height)[None, ...]
        )[0]
        source_region = _expand_by_side_edges(full_gray, source_region)
        source_region = _make_even(source_region, info)
    except DetectionError:
        region = _expand_by_side_edges(sample_gray, region)
        source_region = _to_source_region(region, info, padding=padding)

    area_ratio = (source_region.w * source_region.h) / float(info.width * info.height)
    aspect = source_region.w / float(source_region.h)
    if area_ratio < 0.08 or not (0.5 <= aspect <= 3.6):
        return None

    coverage = count / float(SAMPLE_WIDTH * SAMPLE_HEIGHT)
    confidence = "high" if coverage >= 0.12 else "medium"
    return source_region, frame_time, confidence


def _normalise(array: np.ndarray, percentile: float = 98.0) -> np.ndarray:
    high = float(np.percentile(array, percentile))
    if high <= 1e-6:
        high = float(array.max()) if array.max() > 0 else 1.0
    return np.clip(array / high, 0.0, 1.0)


def _content_score(frame: np.ndarray) -> np.ndarray:
    """静态画面内容丰富度：颜色、纹理、边缘、与边框背景的差异。"""
    rgb = frame.astype(np.float32)
    gray = _gray(frame[None, ...])[0]

    channel_max = rgb.max(axis=2)
    channel_min = rgb.min(axis=2)
    saturation = (channel_max - channel_min) / 255.0

    gx = np.abs(np.diff(gray, axis=1, append=gray[:, -1:])) / 255.0
    gy = np.abs(np.diff(gray, axis=0, append=gray[-1:, :])) / 255.0
    edges = np.maximum(gx, gy)
    edge_local = _box_mean(edges, 3)
    std_local = np.sqrt(
        np.maximum(0.0, _box_mean(gray * gray, 4) - _box_mean(gray, 4) ** 2)
    ) / 255.0

    border = np.zeros(gray.shape, dtype=bool)
    border_pixels = max(2, int(round(min(gray.shape) * 0.03)))
    border[:border_pixels, :] = True
    border[-border_pixels:, :] = True
    border[:, :border_pixels] = True
    border[:, -border_pixels:] = True
    background = np.median(rgb[border], axis=0)
    background_distance = np.abs(rgb - background).mean(axis=2) / 255.0

    score = (
        0.30 * _normalise(std_local)
        + 0.25 * _normalise(_box_mean(saturation, 3))
        + 0.20 * _normalise(edge_local)
        + 0.25 * _normalise(background_distance)
    )
    return _box_mean(score, 5)


def _max_rectangle(integral: np.ndarray, height: int, width: int, ratio: float):
    """在给定宽高比下搜索得分最高的矩形，返回 (得分, x, y, w, h)。"""
    best = (-1.0, 0, 0, 0, 0)
    min_h = max(12, int(round(height * 0.12)))
    max_h = height
    step = max(2, int(round(height / 60)))
    total_area = float(height * width)

    for rect_height in range(min_h, max_h + 1, step):
        rect_width = int(round(rect_height * ratio))
        if rect_width > width or rect_width < 12:
            continue
        area = rect_height * rect_width
        area_weight = (area / total_area) ** 0.28
        sums = (
            integral[rect_height:, rect_width:]
            - integral[:-rect_height, rect_width:]
            - integral[rect_height:, :-rect_width]
            + integral[:-rect_height, :-rect_width]
        )
        means = sums / area
        weighted = means * area_weight
        index = int(np.argmax(weighted))
        y, x = divmod(index, weighted.shape[1])
        value = float(weighted.flat[index])
        if value > best[0]:
            best = (value, x, y, rect_width, rect_height)
    return best


def _detect_by_spatial(
    frame: np.ndarray,
    info: VideoInfo,
    *,
    padding: int,
) -> Optional[tuple[CropRegion, str]]:
    """根据首帧内容丰富度和常见游戏比例，寻找最像游戏视口的矩形。"""
    score = _content_score(frame)
    integral = np.pad(score, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    candidates = [
        _max_rectangle(integral, score.shape[0], score.shape[1], ratio)
        for ratio in COMMON_ASPECT_RATIOS
    ]
    candidates = [item for item in candidates if item[0] >= 0]
    if not candidates:
        return None

    _, x, y, width, height = max(candidates, key=lambda item: item[0])
    region = CropRegion(x, y, width, height)
    region = _refine_edges(_gray(frame[None, ...])[0], region)
    source_region = _to_source_region(region, info, padding=padding)
    area_ratio = (source_region.w * source_region.h) / float(info.width * info.height)
    if area_ratio < 0.12:
        return None
    confidence = "medium" if area_ratio >= 0.3 else "low"
    return source_region, confidence


def _overlap_ratio(inner: CropRegion, outer: CropRegion) -> float:
    x0 = max(inner.x, outer.x)
    y0 = max(inner.y, outer.y)
    x1 = min(inner.right, outer.right)
    y1 = min(inner.bottom, outer.bottom)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    intersection = (x1 - x0) * (y1 - y0)
    return intersection / float(inner.w * inner.h)


def detect_game_region(
    path: str | Path,
    *,
    scan_seconds: float = 20.0,
    sample_fps: float = 2.0,
    method: str = "auto",
    padding: int = 0,
) -> DetectionResult:
    """检测游戏画面区域。

    method:
      - auto：优先使用动态变化，动态不明显时回退到首帧静态分析
      - activity：只用连续帧变化检测
      - spatial：只用首帧静态分析
    """
    info = probe_video(path)
    if method not in {"auto", "activity", "spatial"}:
        raise DetectionError(f"未知检测方式：{method}")

    scan_duration = info.duration if info.duration > 0 else scan_seconds
    scan_duration = min(scan_duration, max(0.5, scan_seconds))
    frames = _read_frames(info.path, start=0.0, duration=scan_duration, fps=sample_fps)
    valid_index = _valid_frame_index(frames)

    if valid_index is None:
        raise DetectionError(
            f"前 {scan_duration:.1f} 秒内没有找到有效画面（可能全黑/纯色）。"
            "可增大 --scan-seconds，或使用 --crop 手动指定区域。"
        )

    frame_time = valid_index / sample_fps
    activity_result = None
    if method in {"auto", "activity"}:
        activity_result = _detect_by_activity(
            frames,
            info,
            valid_index,
            sample_fps=sample_fps,
            padding=padding,
        )

    spatial_result = None
    if method in {"auto", "spatial"}:
        spatial_result = _detect_by_spatial(
            frames[valid_index],
            info,
            padding=padding,
        )

    if method == "activity" and not activity_result:
        raise DetectionError(
            "连续帧变化不足，无法定位游戏区域。"
            "可尝试 --method spatial，或使用 --crop 手动指定区域。"
        )
    if method == "spatial" and not spatial_result:
        raise DetectionError(
            "首帧静态分析未能定位游戏区域。"
            "可尝试 --method activity，或使用 --crop 手动指定区域。"
        )

    if activity_result and spatial_result:
        activity_region, activity_time, activity_confidence = activity_result
        spatial_region, spatial_confidence = spatial_result
        spatial_contains_activity = _overlap_ratio(activity_region, spatial_region)
        area_growth = (spatial_region.w * spatial_region.h) / float(
            activity_region.w * activity_region.h
        )
        activity_aspect = activity_region.w / float(activity_region.h)
        spatial_aspect = spatial_region.w / float(spatial_region.h)
        aspect_close = abs(math.log(spatial_aspect / activity_aspect)) <= 0.08
        spatial_is_full = (
            spatial_region.x == 0
            and spatial_region.y == 0
            and spatial_region.w >= info.width - 2
            and spatial_region.h >= info.height - 2
        )
        # 静态结果通常能覆盖完整视口（包括静态 HUD）；但只有在它与动态区域
        # 高度重合、面积和比例都没有明显跑偏时才采用，否则动态结果更可靠。
        if spatial_is_full or (
            spatial_contains_activity >= 0.85 and area_growth <= 1.5 and aspect_close
        ):
            return DetectionResult(
                info=info,
                region=spatial_region,
                method="auto(spatial+activity)",
                frame_time=frame_time,
                confidence=spatial_confidence,
                notes="静态矩形包含主要动态区域",
            )
        return DetectionResult(
            info=info,
            region=activity_region,
            method="auto(activity)",
            frame_time=activity_time,
            confidence=activity_confidence,
            notes="静态矩形与动态区域偏差较大，采用动态区域",
        )

    if activity_result:
        region, activity_time, confidence = activity_result
        return DetectionResult(
            info=info,
            region=region,
            method="activity",
            frame_time=activity_time,
            confidence=confidence,
        )

    if spatial_result:
        region, confidence = spatial_result
        return DetectionResult(
            info=info,
            region=region,
            method="spatial",
            frame_time=frame_time,
            confidence=confidence,
        )

    raise DetectionError("未能检测到游戏画面区域，请使用 --crop 手动指定。")


def parse_crop(value: str) -> tuple[int, int, int, int]:
    """解析 X:Y:W:H 格式的裁切区域。"""
    parts = value.replace("，", ",").split(":")
    if len(parts) != 4:
        raise ValueError("裁切区域格式应为 X:Y:W:H，例如 320:120:1280:720")
    try:
        x, y, width, height = (int(part.strip()) for part in parts)
    except ValueError as exc:
        raise ValueError("裁切区域必须是四个整数：X:Y:W:H") from exc
    if min(x, y, width, height) < 0 or width <= 0 or height <= 0:
        raise ValueError("裁切区域必须为非负坐标，宽高必须大于 0。")
    return x, y, width, height


def manual_region(
    info: VideoInfo,
    value: str,
    *,
    padding: int = 0,
) -> CropRegion:
    x, y, width, height = parse_crop(value)
    if x + width > info.width or y + height > info.height:
        raise DetectionError(
            f"裁切区域超出视频范围：视频为 {info.width}x{info.height}，"
            f"区域为 x={x}, y={y}, w={width}, h={height}"
        )
    region = CropRegion(x, y, width, height)
    if padding:
        x0 = max(0, x - padding)
        y0 = max(0, y - padding)
        x1 = min(info.width, x + width + padding)
        y1 = min(info.height, y + height + padding)
        region = CropRegion(x0, y0, x1 - x0, y1 - y0)
    return _make_even(region, info)


def _make_even(region: CropRegion, info: VideoInfo) -> CropRegion:
    x = region.x - region.x % 2
    y = region.y - region.y % 2
    width = min(info.width - x, region.w + (region.x - x))
    height = min(info.height - y, region.h + (region.y - y))
    width -= width % 2
    height -= height % 2
    if width < 2 or height < 2:
        raise DetectionError("裁切区域太小，无法编码为常见视频格式。")
    return CropRegion(x, y, width, height)


def make_preview(
    info: VideoInfo,
    region: CropRegion,
    output: str | Path,
    *,
    frame_time: float,
) -> Path:
    """在检测帧上画出裁切框，生成一张 PNG 预览图。"""
    _require_tools()
    target = Path(output).expanduser().resolve()
    if target == info.path:
        raise DetectionError("预览图路径不能与输入视频相同。")
    target.parent.mkdir(parents=True, exist_ok=True)
    box = f"drawbox=x={region.x}:y={region.y}:w={region.w}:h={region.h}:color=red@0.9:t=4"
    command = [
        FFMPEG,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, frame_time):.3f}",
        "-i",
        str(info.path),
        "-frames:v",
        "1",
        "-vf",
        box,
        "-y",
        str(target),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if completed.returncode != 0:
        raise DetectionError(f"生成预览图失败：{completed.stderr.strip()}")
    return target


def crop_video(
    info: VideoInfo,
    region: CropRegion,
    output: str | Path,
    *,
    crf: int = 18,
    preset: str = "veryfast",
) -> Path:
    """使用 ffmpeg 裁切并重新编码视频。"""
    _require_tools()
    target = Path(output).expanduser().resolve()
    if target == info.path:
        raise DetectionError("输出文件不能与输入文件相同。")
    target.parent.mkdir(parents=True, exist_ok=True)

    command = [
        FFMPEG,
        "-hide_banner",
        "-loglevel",
        "warning",
        "-stats",
        "-i",
        str(info.path),
        "-vf",
        region.ffmpeg_filter(),
        "-map",
        "0:v:0",
    ]
    if info.has_audio:
        command.extend(["-map", "0:a:0?", "-c:a", "aac", "-b:a", "192k"])
    command.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
        ]
    )
    if target.suffix.lower() in {".mp4", ".m4v", ".mov"}:
        command.extend(["-movflags", "+faststart"])
    command.extend(["-y", str(target)])
    completed = subprocess.run(command)
    if completed.returncode != 0:
        if target.exists():
            target.unlink(missing_ok=True)
        raise DetectionError("ffmpeg 裁切失败，请检查上方错误信息。")
    return target
