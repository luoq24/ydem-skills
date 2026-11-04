"""AI 产品购买报销凭据生成器。

将付款凭证、发票 / Receipt、订阅 / 订单记录三类截图，按公司报销规范
合成一页 A4 PDF（当前内置 GPT 系列产品预设）。
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from string import Template

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = SKILL_DIR / "templates" / "voucher.html"
PDF_RENDER_SCRIPT = Path(__file__).resolve().parent / "pdf_to_image.ps1"

PAGE_WIDTH_PT = 595.32
PAGE_HEIGHT_PT = 841.92

# 当前支持的产品预设：产品标识 -> 凭据标题
PRODUCT_PRESETS = {
    "chatgpt-plus": "OpenAI-ChatGPT-Plus",
    "chatgpt-pro": "OpenAI-ChatGPT-Pro",
    "chatgpt-codex": "OpenAI-ChatGPT-Codex",
}

DEFAULT_SUBTITLE = "单页 A4"
DEFAULT_REQUIREMENT = (
    "提交要求：一份 PDF、仅一页；需含 ① 付款凭证（账单 / 扣款记录）"
    "② 订单或发票 ③ 订阅或订单记录"
)
DEFAULT_FOOTER = (
    "本凭据根据实际付款与订阅记录整理，仅用于报销审批；"
    "原始账单、发票与订阅记录由报销人留存备查。"
)

SECTION_ORDER = ("payment", "invoice", "subscription")
SECTION_LABELS = {
    "payment": "① 付款凭证（账单 / 扣款记录）",
    "invoice": "② 发票 / Receipt",
    "subscription": "③ 订阅 / 订单记录 · 账单",
}
PLACEHOLDER_HINTS = {
    "payment": "请放入付款账单 / 扣款记录截图<br>（微信、支付宝或银行卡账单）",
    "invoice": "请放入 OpenAI 发票 / Receipt 截图",
    "subscription": "请放入 ChatGPT 订阅 / 订单记录截图",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
MAX_INLINE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_EDGE = 1800

BROWSER_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


def list_presets() -> dict[str, str]:
    """返回可用的产品预设。"""
    return dict(PRODUCT_PRESETS)


def generate_voucher(
    *,
    product: str = "chatgpt-plus",
    title: str | None = None,
    subtitle: str | None = None,
    requirement: str | None = None,
    footer: str | None = None,
    payment: str | Path | None = None,
    invoice: str | Path | None = None,
    subscription: str | Path | None = None,
    output: str | Path | None = None,
    allow_missing: bool = False,
) -> Path:
    """生成一页 A4 报销凭据 PDF，返回输出路径。

    product 为产品预设（见 list_presets），也可通过 title 直接指定标题。
    三张截图任一缺失时，默认报错；allow_missing=True 会渲染占位框。
    """
    config: dict = {
        "product": product,
        "title": title,
        "subtitle": subtitle,
        "requirement": requirement,
        "footer": footer,
        "sections": {
            "payment": {"image": payment},
            "invoice": {"image": invoice},
            "subscription": {"image": subscription},
        },
        "output": output,
    }
    return _generate(config, base_dir=Path.cwd(), allow_missing=allow_missing)


def _generate(config: dict, *, base_dir: Path, allow_missing: bool) -> Path:
    title = _resolve_title(config)
    subtitle = (config.get("subtitle") or DEFAULT_SUBTITLE).strip()
    requirement = (config.get("requirement") or DEFAULT_REQUIREMENT).strip()
    footer = (config.get("footer") or DEFAULT_FOOTER).strip()

    sections = config.get("sections") or {}
    labels: list[str] = []
    boxes: list[str] = []
    for index, key in enumerate(SECTION_ORDER, start=1):
        item = sections.get(key) or {}
        label = (item.get("label") or SECTION_LABELS[key]).strip()
        fit = (item.get("fit") or "cover").lower()
        if fit not in ("cover", "contain"):
            raise ValueError(f"sections.{key}.fit 仅支持 cover / contain，收到：{fit}")
        position = (item.get("position") or "top center").strip()

        labels.append(f'<div class="label label-{index}">{html.escape(label)}</div>')
        image = item.get("image")
        if image:
            image_path = Path(image)
            if not image_path.is_absolute():
                image_path = base_dir / image_path
            if not image_path.exists():
                raise FileNotFoundError(f"找不到截图文件：{image_path}")
            uri = _image_data_uri(image_path)
            boxes.append(
                f'<div class="box box-{index} fit-{fit}">'
                f'<img src="{uri}" style="object-position:{html.escape(position)}" '
                f'alt="{html.escape(label)}"></div>'
            )
        elif allow_missing:
            boxes.append(
                f'<div class="box box-{index}">'
                f'<div class="placeholder">{PLACEHOLDER_HINTS[key]}</div></div>'
            )
        else:
            raise FileNotFoundError(
                f"缺少 {label} 截图；如只需生成草稿，请使用 --allow-missing"
            )

    html_text = Template(TEMPLATE_PATH.read_text(encoding="utf-8")).safe_substitute(
        title=html.escape(title),
        subtitle=html.escape(subtitle),
        requirement=html.escape(requirement),
        footer=html.escape(footer),
        labels="\n  ".join(labels),
        boxes="\n  ".join(boxes),
    )

    output_path = _resolve_output(config.get("output"), title, base_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="voucher_") as tmp:
        html_path = Path(tmp) / "voucher.html"
        html_path.write_text(html_text, encoding="utf-8")
        _html_to_pdf(html_path, output_path)

    _verify_pdf(output_path)
    return output_path


def _resolve_title(config: dict) -> str:
    title = (config.get("title") or "").strip()
    if title:
        return title
    product = (config.get("product") or "").strip().lower()
    if product in PRODUCT_PRESETS:
        return PRODUCT_PRESETS[product]
    if product:
        raise ValueError(
            f"未知产品预设：{product}；可用：{', '.join(PRODUCT_PRESETS)}，"
            "或直接通过 title 指定标题"
        )
    return PRODUCT_PRESETS["chatgpt-plus"]


def _resolve_output(value, title: str, base_dir: Path) -> Path:
    if value:
        path = Path(value)
        return path if path.is_absolute() else base_dir / path
    safe_title = re.sub(r'[<>:"/\\|?*]', "-", title).strip() or "AI产品"
    return base_dir / f"{safe_title}-报销凭据.pdf"


def _image_data_uri(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf_data_uri(path)
    if suffix not in IMAGE_EXTENSIONS:
        raise ValueError(
            f"不支持的截图格式：{path.suffix}（{path}），支持图片或 PDF"
        )
    raw = path.read_bytes()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix)

    if mime and suffix != ".webp" and len(raw) <= MAX_INLINE_BYTES:
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"

    return _encode_image(path)


def _pdf_data_uri(path: Path) -> str:
    """用 Windows 内置 PDF 渲染接口把第一页转为 PNG。"""
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        raise RuntimeError("将 PDF 转为图片需要 PowerShell，请确认系统可用")

    with tempfile.TemporaryDirectory(prefix="voucher_pdf_") as tmp:
        png_path = Path(tmp) / "page.png"
        command = [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PDF_RENDER_SCRIPT),
            "-PdfPath",
            str(path),
            "-OutPath",
            str(png_path),
            "-Width",
            "1600",
        ]
        result = subprocess.run(command, capture_output=True, timeout=120)
        if not png_path.exists() or png_path.stat().st_size == 0:
            detail = (result.stderr or b"").decode("utf-8", "ignore").strip()
            raise RuntimeError(
                f"PDF 渲染失败：{path.name}"
                + (f"（{detail[-300:]}）" if detail else "")
            )
        return _encode_image(png_path)


def _encode_image(path: Path) -> str:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - 缺库时给出明确提示
        raise RuntimeError(
            "图片体积较大或格式为 webp / bmp，需要 Pillow 压缩，请先安装 Pillow"
        ) from exc

    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90, optimize=True)
    data = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{data}"


def _find_browser() -> Path:
    candidates = [os.environ.get("BROWSER_PATH", "")]
    candidates.extend(BROWSER_CANDIDATES)
    for name in ("msedge", "chrome", "google-chrome"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise RuntimeError(
        "未找到可用于导出 PDF 的浏览器，请安装 Microsoft Edge / Chrome，"
        "或设置环境变量 BROWSER_PATH 指向浏览器可执行文件"
    )


def _html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    browser = _find_browser()
    profile_dir = tempfile.mkdtemp(prefix="voucher_profile_")
    command = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-pdf-header-footer",
        "--print-to-pdf-no-header",
        f"--print-to-pdf={pdf_path}",
        f"--user-data-dir={profile_dir}",
        html_path.as_uri(),
    ]
    if pdf_path.exists():
        pdf_path.unlink()
    try:
        result = subprocess.run(command, capture_output=True, timeout=180)
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)

    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        detail = (result.stderr or b"").decode("utf-8", "ignore").strip()
        raise RuntimeError(
            f"PDF 导出失败（退出码 {result.returncode}）"
            + (f"：{detail[-500:]}" if detail else "")
        )


def _verify_pdf(pdf_path: Path) -> None:
    data = pdf_path.read_bytes()
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
    if pages > 1:
        pdf_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"内容超出一页，生成了 {pages} 页；请缩短页眉 / 页脚文案或检查截图尺寸"
        )
    media = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", data)
    if media:
        width, height = float(media.group(1)), float(media.group(2))
        if abs(width - PAGE_WIDTH_PT) > 3 or abs(height - PAGE_HEIGHT_PT) > 3:
            print(
                f"警告：页面尺寸为 {width:.1f} x {height:.1f}pt，与 A4 存在偏差",
                file=sys.stderr,
            )


def _load_config(config_path: Path) -> dict:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"配置文件不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("配置文件顶层必须是对象")
    return data


def _merge_cli(config: dict, args: argparse.Namespace) -> dict:
    merged = dict(config)
    for key in ("product", "title", "subtitle", "requirement", "footer", "output"):
        value = getattr(args, key, None)
        if value:
            merged[key] = value
    sections = dict(merged.get("sections") or {})
    for key in SECTION_ORDER:
        value = getattr(args, key, None)
        if value:
            item = dict(sections.get(key) or {})
            item["image"] = value
            sections[key] = item
    merged["sections"] = sections
    return merged


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="生成 AI 产品购买报销凭据（单页 A4 PDF，当前支持 GPT 系列）"
    )
    parser.add_argument("--config", help="JSON 配置文件路径")
    parser.add_argument("--product", choices=sorted(PRODUCT_PRESETS), help="产品预设")
    parser.add_argument("--title", help="凭据标题，默认取产品预设")
    parser.add_argument("--subtitle", help="右上角副标题，默认「单页 A4」")
    parser.add_argument("--requirement", help="页眉提交要求文案")
    parser.add_argument("--footer", help="页脚说明文案")
    parser.add_argument("--payment", help="① 付款凭证截图路径")
    parser.add_argument("--invoice", help="② 发票 / Receipt 截图路径")
    parser.add_argument("--subscription", help="③ 订阅 / 订单记录截图路径")
    parser.add_argument("--output", help="输出 PDF 路径")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="缺少截图时渲染占位框（仅用于草稿）",
    )
    parser.add_argument("--list-presets", action="store_true", help="列出产品预设")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    if args.list_presets:
        for key, title in PRODUCT_PRESETS.items():
            print(f"{key}\t{title}")
        return 0

    if args.config:
        config_path = Path(args.config).expanduser().resolve()
        config = _load_config(config_path)
        base_dir = config_path.parent
    else:
        config = {}
        base_dir = Path.cwd()
    config = _merge_cli(config, args)

    try:
        output_path = _generate(
            config, base_dir=base_dir, allow_missing=args.allow_missing
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print(f"已生成：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
