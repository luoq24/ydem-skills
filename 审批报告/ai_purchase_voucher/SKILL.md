# AI 产品购买报销凭据（GPT 系列）

## 简介

将一次 AI 产品购买的**三类报销材料**，按公司规范合成**一份、仅一页 A4** 的 PDF 凭据：

| 槽位 | 内容 | 默认标题 |
| --- | --- | --- |
| ① | 付款凭证（微信 / 支付宝 / 银行账单、扣款记录） | ① 付款凭证（账单 / 扣款记录） |
| ② | 订单或发票（OpenAI Receipt / Invoice、电子发票） | ② 发票 / Receipt |
| ③ | 订阅或订单记录（ChatGPT 订阅与交易记录） | ③ 订阅 / 订单记录 · 账单 |

三类材料均支持图片（png / jpg / webp / bmp / gif）或 PDF（自动取第一页渲染为图片）。

当前内置 GPT 购买相关预设：`chatgpt-plus`、`chatgpt-pro`、`chatgpt-codex`。

版式参考：

- 采购说明页：<https://aihub.lmdgame.com/app/purchase>
- 凭据示例：<https://aihub.lmdgame.com/purchase/vouchers/OpenAI-ChatGPT-Codex.pdf>

## 目录结构

```
审批报告/ai_purchase_voucher/
├── SKILL.md
├── config.example.json
├── templates/
│   └── voucher.html
└── scripts/
    ├── generate_voucher.py
    └── pdf_to_image.ps1
```

## 环境要求

- Python 3.8+
- Microsoft Edge 或 Google Chrome（用于无头模式导出 PDF；找不到时可设置环境变量 `BROWSER_PATH`）
- PowerShell（Windows 自带，仅 PDF 材料需要，用系统内置 `Windows.Data.Pdf` 渲染，无需安装第三方库）
- Pillow（可选：仅在图片超过 2MB 或为 webp / bmp 时需要压缩，已安装）

## 使用方法

以下命令均在 `审批报告/ai_purchase_voucher/` 目录下执行。

### 1. 命令行快速生成

```bash
python scripts/generate_voucher.py \
  --product chatgpt-pro \
  --payment images/payment.png \
  --invoice images/invoice.png \
  --subscription images/subscription.png \
  --output OpenAI-ChatGPT-Pro-报销凭据.pdf
```

省略 `--output` 时，默认输出为 `{标题}-报销凭据.pdf`。

先补齐付款截图、缺发票时，可生成带占位框的草稿（**不可直接提交**）：

```bash
python scripts/generate_voucher.py --product chatgpt-pro \
  --payment images/payment.png --allow-missing
```

查看可用产品预设：

```bash
python scripts/generate_voucher.py --list-presets
```

### 2. 使用 JSON 配置（推荐，可自定义标题与文案）

复制 `config.example.json` 后修改，再执行：

```bash
python scripts/generate_voucher.py --config purchase.json
```

配置字段：

| 字段 | 说明 |
| --- | --- |
| `product` | 产品预设，`chatgpt-plus` / `chatgpt-pro` / `chatgpt-codex` |
| `title` | 左上角标题，默认取预设标题，如 `OpenAI-ChatGPT-Plus` |
| `subtitle` | 右上角副标题，默认「单页 A4」 |
| `requirement` | 页眉提交要求文案 |
| `footer` | 页脚说明文案 |
| `sections.payment` | ① 付款凭证：`image` 截图路径，另有 `label`、`fit`、`position` |
| `sections.invoice` | ② 发票 / Receipt |
| `sections.subscription` | ③ 订阅 / 订单记录 |
| `output` | 输出 PDF 路径 |

截图字段说明：

- `image`：材料路径，支持图片或 PDF（PDF 取第一页），相对路径以**配置文件所在目录**为基准
- `fit`：`cover`（默认，铺满裁切）或 `contain`（完整显示，留白）
- `position`：`cover` 裁切时的对齐位置，默认 `top center`，可改为 `center`、`top left` 等
- `label`：该槽位标题，可覆盖默认文案

图片信息不全时，`fit` 建议改为 `contain`，避免裁掉金额、单号等关键信息。

### 3. 作为模块调用

```python
from scripts.generate_voucher import generate_voucher, list_presets

print(list_presets())

output = generate_voucher(
    product="chatgpt-codex",
    payment="images/payment.png",
    invoice="images/invoice.png",
    subscription="images/subscription.png",
    output="OpenAI-ChatGPT-Codex-报销凭据.pdf",
)
print(output)
```

`generate_voucher()` 支持 `title`、`subtitle`、`requirement`、`footer`、`allow_missing` 等参数，返回输出 PDF 的 `Path`。

## 版式参数

固定单页 A4（595.32 × 841.92 pt），三块截图槽位：

| 槽位 | 位置（左上角） | 尺寸 |
| --- | --- | --- |
| ① 左栏 | 34, 82 pt | 161.74 × 351.18 pt |
| ② 右上 | 205.74, 82 pt | 355.58 × 274.70 pt |
| ③ 右下 | 205.74, 410.70 pt | 355.58 × 177.57 pt |

生成后会自动校验页数与页面尺寸；内容超出一页会直接报错，不会输出多页文件。

## 注意事项

1. **必须使用真实材料**：截图须来自实际付款账单、OpenAI 发票与订阅记录，不要自行编造或修改金额、单号、日期。
2. **一页限制**：页眉 / 页脚文案过长会增加页数并触发报错，请保持简短。
3. **截图比例**：`cover` 会按槽位比例裁切；信息贴边的截图请改用 `contain`。PDF 发票比例通常较宽，建议用 `contain`，避免裁掉二维码或金额列。
4. **PDF 只取第一页**：多页发票请先拆分，或仅保留含金额与发票号的那一页。
5. **占位框仅用于草稿**：`--allow-missing` 生成的占位 PDF 不能作为报销材料提交。
6. **PDF 导出依赖浏览器**：若提示找不到浏览器，安装 Edge / Chrome，或设置 `BROWSER_PATH` 指向可执行文件。
7. **运行目录**：命令行请在本 skill 目录下执行，保证 `templates/voucher.html` 能被正确找到。
