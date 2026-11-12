# 游戏画面自动裁切（Game View Cropper）

## 简介

从 NVIDIA 录屏中自动找出游戏实时画面所在的矩形区域，只保留游戏画面，生成一个新的视频文件。适用于 Unity 编辑器、IDE、浏览器等环境占据屏幕周边，游戏窗口位于中间的录屏。

处理流程：

1. 用 `ffprobe` 读取分辨率、时长、帧率、音轨。
2. 扫描视频开头（默认 20 秒），跳过黑屏、纯色帧，找到第一帧有效画面。
3. 对有效画面及其后续帧做变化分析：编辑器 UI 通常静止，游戏画面会持续变化。
4. 根据内容纹理、颜色、边缘和常见游戏宽高比做首帧静态分析，作为动态分析不充分时的兜底。
5. 把检测框吸附到画面中的直线边缘；再沿游戏视口左右边框的连续边线，补全顶部标题栏、底部按钮栏等静态游戏 UI。最后按偶数像素对齐。
6. 用 `ffmpeg` 的 `crop` 滤镜裁切，输出 H.264 + AAC 的新视频；原视频有音轨时保留音频。

## 目录结构

```
视频处理/game_view_cropper/
├── SKILL.md
└── scripts/
    ├── crop_game_view.py        # 命令行入口
    └── game_view_detector.py    # 探测、检测、预览、裁切实现
```

## 环境要求

- Python 3.10+
- `numpy`（已随环境安装；缺少时请手动安装：`pip install numpy`）
- `ffmpeg` 与 `ffprobe`，且已加入 `PATH`

脚本不会自动安装依赖。缺少 `ffmpeg` 时请先安装 ffmpeg 并确认命令行能执行 `ffmpeg -version`。

## 使用方法

以下命令均在 `视频处理/game_view_cropper/` 目录下执行。

### 1. 最简单用法

```bash
python scripts/crop_game_view.py recording.mp4
```

默认输出到原视频旁边，文件名追加 `_game`：

```
recording.mp4  ->  recording_game.mp4
```

### 2. 先看检测结果，不生成视频

```bash
python scripts/crop_game_view.py recording.mp4 --dry-run --preview preview.png
```

`--preview` 会在检测所用的画面帧上画出红色裁切框，便于确认区域是否准确。若游戏画面在录屏中途才出现，预览帧会自动取动态最明显的一帧，而不是黑屏或纯色帧。

输出示例：

```
源视频: 1920x1080, 30.00 fps
检测帧: 0.000s
裁切区域: x=320, y=120, w=1280, h=720 (1280x720)
检测方式: auto(spatial+activity)，置信度: medium
预览图: ...\preview.png
```

### 3. 指定输出路径

```bash
python scripts/crop_game_view.py recording.mp4 -o game_only.mp4
```

输出文件已存在时默认报错；确认覆盖请加 `--overwrite`。

### 4. 手动指定裁切区域

自动检测不准确时，可直接指定 `X:Y:W:H`：

```bash
python scripts/crop_game_view.py recording.mp4 --crop 320:120:1280:720
```

`X:Y` 是左上角坐标，`W:H` 是宽高，单位均为源视频像素。

### 5. 常用参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `-o, --output` | `*_game.mp4` | 输出视频路径 |
| `--crop X:Y:W:H` | 无 | 手动指定裁切区域，跳过自动检测 |
| `--method` | `auto` | `auto` / `activity`（连续帧变化）/ `spatial`（首帧静态） |
| `--scan-seconds` | `20` | 扫描开头的秒数，用于跳过黑屏和纯色帧 |
| `--sample-fps` | `2` | 检测时每秒抽取的帧数 |
| `--padding` | `0` | 检测区域四周额外保留的像素 |
| `--preview FILE` | 无 | 输出带红色裁切框的预览图 |
| `--dry-run` | 关 | 只检测并打印结果，不生成视频 |
| `--json` | 关 | 以 JSON 输出检测结果，便于程序读取 |
| `--crf` | `18` | x264 质量，越小质量越高 |
| `--preset` | `veryfast` | x264 编码预设 |
| `--overwrite` | 关 | 允许覆盖输出文件 |

## 检测方式说明

### `auto`（默认）

- 动态分析能定位时，优先使用动态区域。
- 当静态矩形完整包含动态区域、且面积没有异常膨胀时，使用静态矩形；这样能保留静态 HUD、边框等动态分析可能漏掉的部分。
- 动态分析失败（例如加载界面、静止菜单）时，自动回退到首帧静态分析。

### `activity`

只使用连续帧变化。适合正常游戏实时画面，对编辑器 UI 的抗干扰能力最好。若整段画面几乎不动，会报错并提示改用 `spatial` 或 `--crop`。

### `spatial`

只分析第一帧有效画面，适合静态游戏、菜单、加载界面。静态分析依赖游戏视口有明显边界或与编辑器背景有明显差异；若游戏画面中有大面积纯黑/纯色区域，可能被误判为背景而裁掉，建议配合 `--preview` 检查，必要时用 `--crop` 手动指定。

### 置信度

- `high`：动态区域占比较大，检测结果通常可靠。
- `medium`：动态或静态特征一般，建议预览确认。
- `low`：静态特征较弱或区域占比较小，建议预览或手动指定。

## 作为模块调用

在本 skill 目录下：

```python
from scripts.game_view_detector import (
    crop_video,
    detect_game_region,
    make_preview,
    manual_region,
    probe_video,
)

info = probe_video("recording.mp4")

result = detect_game_region("recording.mp4")
print(result.region.to_dict())
print(result.region.ffmpeg_filter())

crop_video(info, result.region, "recording_game.mp4")
```

手动区域：

```python
info = probe_video("recording.mp4")
region = manual_region(info, "320:120:1280:720")
crop_video(info, region, "game_only.mp4")
```

生成预览图：

```python
result = detect_game_region("recording.mp4")
make_preview(
    result.info,
    result.region,
    "preview.png",
    frame_time=result.frame_time,
)
```

## 输出说明

- 视频：H.264、`yuv420p`、CRF 18（默认），重新编码，无法保留 HDR / 10-bit 原格式。
- 音频：源视频有音轨时转码为 AAC 192 kbps；无音轨时不生成音频流。
- 裁切尺寸会对齐到偶数像素，避免 `yuv420p` 编码失败。
- 当检测区域贴近画面边缘（约 2% 以内）时，会自动吸附到整条边，避免全屏游戏被裁掉几个像素。

## 注意事项

1. **先预览再批量处理**：不同编辑器布局差异较大，首次使用建议加 `--dry-run --preview` 检查红色框。
2. **黑屏开头**：默认只扫描前 20 秒。若游戏画面出现得更晚，请增大 `--scan-seconds`。
3. **静态画面**：`--method activity` 对静止画面无效；改用 `auto` 或 `spatial`。
4. **区域不准时**：用预览图读出实际坐标，并通过 `--crop X:Y:W:H` 手动指定，结果最稳定。
5. **全屏游戏**：检测框接近整屏时会自动吸附为全屏，此时输出仍会重新编码，但画面不裁切。
6. **运行目录**：命令行示例默认在 skill 目录下执行；`crop_game_view.py` 与 `game_view_detector.py` 必须保持在同一目录。
