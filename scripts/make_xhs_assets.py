"""Compose the 1242x1656 Xiaohongshu cards from the real app screenshots.

Usage:
    .venv\\Scripts\\python.exe scripts/make_xhs_assets.py

Reads docs/screenshots/{filtered,batch-hi,settings-hi}.png and the two
xhs-geometry-*.json files written by capture_xhs_shots.py, then writes
docs/social/xiaohongshu/01..07.png.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"
OUT = ROOT / "docs" / "social" / "xiaohongshu"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1242, 1656
M = 92
CARD_W = W - M * 2
DPI_SCALE = 1.25  # widgets were captured at 125% Windows scaling
FONT_DIR = Path("C:/Windows/Fonts")

INK = (15, 37, 48)
BODY = (69, 94, 108)
MUTED = (133, 152, 163)
ACCENT = (43, 124, 166)
ACCENT_DEEP = (29, 94, 128)
ACCENT_SOFT = (219, 236, 245)
ACCENT_TINT = (240, 248, 252)
HAIR = (214, 229, 237)
WHITE = (255, 255, 255)
WARM = (255, 244, 232)
GREEN_TINT = (232, 246, 238)
GREEN = (46, 122, 92)


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def f_bd(size: int) -> ImageFont.FreeTypeFont:
    return font("msyhbd.ttc", size)


def f_rg(size: int) -> ImageFont.FreeTypeFont:
    return font("msyh.ttc", size)


def f_mono(size: int) -> ImageFont.FreeTypeFont:
    return font("consola.ttf", size)


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def background() -> Image.Image:
    img = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = min(1.0, (y / H) ** 0.85)
        draw.line([(0, y), (W, y)], fill=lerp((255, 255, 255), (232, 243, 249), t))

    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    for y in range(0, H, 36):
        for x in range(0, W, 36):
            gd.ellipse((x, y, x + 2, y + 2), fill=(120, 165, 188, 40))
    img = Image.alpha_composite(img.convert("RGBA"), grid)

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse((-260, -300, 620, 520), fill=(126, 187, 219, 66))
    gdraw.ellipse((W - 260, H - 520, W + 300, H - 40), fill=(150, 205, 226, 52))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    return Image.alpha_composite(img, glow)


def shadowed(canvas: Image.Image, box, radius=20, blur=26, offset=16, alpha=60):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = box
    d.rounded_rectangle((x0, y0 + offset, x1, y1 + offset), radius,
                        fill=(17, 49, 66, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    return Image.alpha_composite(canvas, layer)


def paste_window(canvas: Image.Image, im: Image.Image, x: int, y: int, width: int,
                 radius: int = 18) -> tuple[Image.Image, int]:
    ratio = width / im.width
    height = round(im.height * ratio)
    im = im.resize((width, height), Image.LANCZOS)
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius, fill=255)
    canvas = shadowed(canvas, (x, y, x + width, y + height), radius, 28, 18, 70)
    canvas.paste(im, (x, y), mask)
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((x, y, x + width - 1, y + height - 1), radius,
                        outline=(226, 237, 242, 255), width=1)
    return canvas, y + height


def wrap(draw, text: str, fnt, max_w: int) -> list[str]:
    lines, current = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(current)
            current = ""
            continue
        trial = current + ch
        if draw.textlength(trial, font=fnt) > max_w and current:
            lines.append(current)
            current = ch
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def paragraph(draw, x, y, text, fnt, fill, max_w, line_h):
    for line in wrap(draw, text, fnt, max_w):
        draw.text((x, y), line, font=fnt, fill=fill)
        y += line_h
    return y


def kicker(draw, x, y, text, color=ACCENT):
    draw.rounded_rectangle((x, y + 6, x + 8, y + 30), 4, fill=color)
    draw.text((x + 22, y), text, font=f_bd(28), fill=color)


def brand(canvas):
    d = ImageDraw.Draw(canvas)
    x, y = M, 92
    d.rounded_rectangle((x, y, x + 56, y + 56), 16, fill=ACCENT)
    d.ellipse((x + 15, y + 15, x + 41, y + 41), outline=WHITE, width=4)
    d.polygon([(x + 25, y + 24), (x + 36, y + 28), (x + 25, y + 32)], fill=WHITE)

    name_font = f_bd(34)
    d.text((x + 76, y + 6), "Media Filter", font=name_font, fill=INK)
    name_w = d.textlength("Media Filter", font=name_font)

    label = "开源 · 免费"
    fnt = f_bd(22)
    tw = d.textlength(label, font=fnt)
    bx = x + 76 + name_w + 18
    d.rounded_rectangle((bx, y + 10, bx + tw + 28, y + 44), 17, fill=ACCENT_SOFT)
    d.text((bx + 14, y + 14), label, font=fnt, fill=ACCENT_DEEP)
    return canvas


def footer(canvas, page: int, total: int = 7):
    d = ImageDraw.Draw(canvas)
    d.line((M, 1556, W - M, 1556), fill=HAIR, width=2)
    d.text((M, 1578), "Media Filter · Windows 免安装", font=f_rg(24), fill=MUTED)
    right = f"{page:02d} / {total:02d}"
    tw = d.textlength(right, font=f_mono(26))
    d.text((W - M - tw, 1577), right, font=f_mono(26), fill=MUTED)
    return canvas


def chip(draw, x, y, text, fnt, fill, fg, h=46, pad=20, outline=None):
    tw = draw.textlength(text, font=fnt)
    draw.rounded_rectangle((x, y, x + tw + pad * 2, y + h), h // 2, fill=fill,
                           outline=outline, width=2 if outline else 1)
    draw.text((x + pad, y + (h - fnt.size) // 2 - 2), text, font=fnt, fill=fg)
    return x + tw + pad * 2


def ring(draw, box, color=ACCENT, pad=9, radius=14, width=4):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0 - pad, y0 - pad, x1 + pad, y1 + pad), radius,
                           outline=color, width=width)


def strip_window(path: Path, top_h: int, bottom_from: int) -> Image.Image:
    """One window screenshot with the empty middle removed (pixel coords)."""
    im = Image.open(path)
    top = im.crop((0, 0, im.width, top_h))
    bottom = im.crop((0, bottom_from, im.width, im.height))
    out = Image.new("RGBA", (im.width, top.height + bottom.height), (255, 255, 255, 255))
    out.paste(top, (0, 0))
    out.paste(bottom, (0, top.height))
    return out


def load_geo(name: str) -> dict:
    return json.loads((SHOTS / name).read_text(encoding="utf-8"))


def tip_panel(canvas, top: int, text: str, height: int = 132) -> Image.Image:
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((M, top, W - M, top + height), 20, fill=ACCENT_TINT)
    d.rounded_rectangle((M, top + 24, M + 8, top + height - 24), 4, fill=ACCENT)
    paragraph(d, M + 36, top + 24, text, f_rg(27), BODY, CARD_W - 72, 42)
    return canvas


def bullets(canvas, top: int, items: list[tuple[str, str]], step: int = 78) -> int:
    d = ImageDraw.Draw(canvas)
    y = top
    for head, text in items:
        d.rounded_rectangle((M, y + 12, M + 12, y + 36), 6, fill=ACCENT)
        d.text((M + 30, y), head, font=f_bd(31), fill=INK)
        d.text((M + 210, y + 2), text, font=f_rg(29), fill=BODY)
        y += step
    return y


def cover() -> Image.Image:
    canvas = background()
    canvas = brand(canvas)
    d = ImageDraw.Draw(canvas)

    kicker(d, M, 244, "本地 AI · 视频整理")
    d.text((M, 292), "视频太多找不到？", font=f_bd(94), fill=INK)

    y = 418
    head = "让 AI 先看"
    tail = "一遍。"
    d.text((M, y), head + tail, font=f_bd(94), fill=ACCENT_DEEP)
    head_w = d.textlength(head, font=f_bd(94))
    tail_w = d.textlength(tail, font=f_bd(94))
    bar_y = y + 118
    d.rounded_rectangle((M + head_w + 6, bar_y, M + head_w + tail_w - 10, bar_y + 12),
                        6, fill=(122, 194, 227))

    paragraph(d, M, y + 152,
              "本地识别画面内容，自动打标签；按标签一键筛出想要的片段，再批量转封装或压缩。",
              f_rg(34), BODY, CARD_W - 40, 52)

    shot = strip_window(SHOTS / "filtered.png", 620, 1064)
    canvas, bottom = paste_window(canvas, shot, M, 704, CARD_W)

    d = ImageDraw.Draw(canvas)
    labels = [
        ("14 个文件", ACCENT_TINT, ACCENT_DEEP),
        ("9 条含人物", ACCENT_SOFT, ACCENT_DEEP),
        ("视频不上传", WARM, (150, 96, 40)),
    ]
    x = M
    for text, fill, fg in labels:
        x = chip(d, x, bottom + 26, text, f_bd(27), fill, fg, h=56, pad=24,
                 outline=HAIR) + 14

    panel_top = bottom + 112
    d.rounded_rectangle((M, panel_top, W - M, panel_top + 96), 22, fill=WHITE,
                        outline=HAIR, width=2)
    flow = "AI 识别  →  标签筛选  →  批量处理"
    fnt = f_bd(30)
    tw = d.textlength(flow, font=fnt)
    d.text((M + (CARD_W - tw) / 2, panel_top + 28), flow, font=fnt, fill=ACCENT_DEEP)

    d.text((M, panel_top + 128), "Windows 10 / 11 · 约 168 MB · 解压就能用",
           font=f_rg(28), fill=MUTED)
    footer(canvas, 1)
    return canvas.convert("RGB")


def comparison() -> Image.Image:
    canvas = background()
    canvas = brand(canvas)
    d = ImageDraw.Draw(canvas)

    kicker(d, M, 190, "为什么需要它")
    d.text((M, 236), "文件名说明不了内容", font=f_bd(68), fill=INK)
    d.text((M, 330), "但标签可以。", font=f_bd(68), fill=ACCENT_DEEP)

    rows = [
        ("VID_20241103_143022.mp4", [("人", ACCENT_SOFT), ("户外", GREEN_TINT)]),
        ("GX010042.MP4", [("狗", WARM), ("车", ACCENT_TINT)]),
        ("屏幕录制 2024-11-03.mp4", [("录屏", (238, 236, 250)), ("竖屏", WARM)]),
        ("MVI_0031.MOV", [("人", ACCENT_SOFT), ("特写", (238, 236, 250))]),
    ]

    def panel(top, title, hint, tagged):
        nonlocal canvas
        row_h = 72
        bottom = top + 96 + len(rows) * row_h + 24
        canvas = shadowed(canvas, (M, top, W - M, bottom), 24, 24, 14, 45)
        dd = ImageDraw.Draw(canvas)
        dd.rounded_rectangle((M, top, W - M, bottom), 24, fill=WHITE, outline=HAIR, width=2)
        dd.text((M + 38, top + 26), title, font=f_bd(32),
                fill=INK if tagged else (120, 136, 145))
        hint_w = dd.textlength(hint, font=f_rg(23))
        dd.text((W - M - 38 - hint_w, top + 34), hint, font=f_rg(23), fill=MUTED)
        for i, (name, tags) in enumerate(rows):
            ry = top + 96 + i * row_h
            dd.line((M + 38, ry - 2, W - M - 38, ry - 2), fill=(240, 246, 249), width=2)
            dd.text((M + 38, ry + 18), name, font=f_rg(25),
                    fill=INK if tagged else (152, 166, 175))
            if tagged:
                tx = W - M - 38
                for label, fill in reversed(tags):
                    fnt = f_bd(23)
                    tw = dd.textlength(label, font=fnt)
                    tx -= tw + 28
                    dd.rounded_rectangle((tx, ry + 12, tx + tw + 28, ry + 52), 20, fill=fill)
                    dd.text((tx + 14, ry + 17), label, font=fnt, fill=ACCENT_DEEP)
                    tx -= 10
            else:
                tw = dd.textlength("—", font=f_bd(26))
                dd.text((W - M - 38 - tw, ry + 14), "—", font=f_bd(26),
                        fill=(186, 199, 207))
        return bottom

    b1 = panel(444, "只看到文件名", "打开 → 快进 → 关掉 → 下一条", False)

    d = ImageDraw.Draw(canvas)
    cx = W // 2
    d.line((cx, b1 + 22, cx, b1 + 76), fill=ACCENT, width=6)
    d.polygon([(cx - 14, b1 + 68), (cx + 14, b1 + 68), (cx, b1 + 94)], fill=ACCENT)

    b2 = panel(b1 + 116, "扫描之后", "按标签筛，一秒定位", True)

    d = ImageDraw.Draw(canvas)
    paragraph(d, M, b2 + 34,
              "标签来自画面本身：人物、猫狗、汽车、食物、屏幕……\n8 类常用标签在本机识别，云端模式可扩到 26 类。",
              f_rg(29), BODY, CARD_W, 46)
    footer(canvas, 2)
    return canvas.convert("RGB")


def step_one() -> Image.Image:
    canvas = background()
    canvas = brand(canvas)
    d = ImageDraw.Draw(canvas)
    kicker(d, M, 190, "STEP 01 · 扫描")
    d.text((M, 236), "选个文件夹，", font=f_bd(76), fill=INK)
    d.text((M, 330), "参数自己读出来。", font=f_bd(76), fill=ACCENT_DEEP)
    d.text((M, 448), "不用建项目，不用导入素材，不搬文件。", font=f_rg(30), fill=MUTED)

    shot = strip_window(SHOTS / "filtered.png", 620, 1064)
    canvas, bottom = paste_window(canvas, shot, M, 520, CARD_W)

    end = bullets(canvas, bottom + 46, [
        ("真实参数", "ffprobe 读取分辨率、时长、码率、封装格式"),
        ("整棵目录", "递归扫描子文件夹，支持 mp4 / mkv / mov / webm"),
        ("原地整理", "不复制、不移动，文件还在原来的位置"),
    ])
    tip_panel(canvas, end + 8,
              "扫描只读取元数据，几百个文件也只要几秒；慢的是 AI 识别，可以随时取消。")
    footer(canvas, 3)
    return canvas.convert("RGB")


def step_two() -> Image.Image:
    canvas = background()
    canvas = brand(canvas)
    d = ImageDraw.Draw(canvas)
    kicker(d, M, 190, "STEP 02 · 打标签")
    d.text((M, 236), "标签在你自己", font=f_bd(76), fill=INK)
    d.text((M, 330), "电脑上认。", font=f_bd(76), fill=ACCENT_DEEP)
    d.text((M, 448), "内置视觉模型走 DirectML，有显卡用显卡，没有就用 CPU。", font=f_rg(30), fill=MUTED)

    shot = Image.open(SHOTS / "settings-hi.png")
    canvas, bottom = paste_window(canvas, shot, M, 520, CARD_W)

    end = bullets(canvas, bottom + 42, [
        ("GPU 优先", "NVIDIA / AMD / Intel 都能用，失败自动回退 CPU"),
        ("只写标签", "关键帧和视频都不离开电脑，识别结果存在本地"),
        ("可升级", "8 类本机识别，云端模式可扩到 26 类，还能加自定义标签"),
    ])
    tip_panel(canvas, end + 6,
              "首次识别每条 1–3 秒，之后走本地缓存；26 个内置标签可以按需开关。")
    footer(canvas, 4)
    return canvas.convert("RGB")


def step_three() -> Image.Image:
    canvas = background()
    canvas = brand(canvas)
    d = ImageDraw.Draw(canvas)
    kicker(d, M, 190, "STEP 03 · 筛选")
    d.text((M, 236), "按内容筛，", font=f_bd(76), fill=INK)
    d.text((M, 330), "一秒挑出想要的。", font=f_bd(76), fill=ACCENT_DEEP)
    d.text((M, 448), "标签、格式、关键词可以叠加，边输入边刷新。", font=f_rg(30), fill=MUTED)

    shot = strip_window(SHOTS / "filtered.png", 620, 1064)
    canvas, bottom = paste_window(canvas, shot, M, 520, CARD_W)

    geo = load_geo("xhs-geometry-main.json")
    scale = CARD_W / (1440 * DPI_SCALE)
    ox, oy = M, 520

    def to_box(rect):
        x, y, w, h = (v * DPI_SCALE for v in rect)
        return (ox + x * scale, oy + y * scale, ox + (x + w) * scale, oy + (y + h) * scale)

    d = ImageDraw.Draw(canvas)
    ring(d, to_box(geo["tag_filter"]))
    ring(d, to_box(geo["select_all"]))

    end = bullets(canvas, bottom + 48, [
        ("组合过滤", "标签 × 格式 × 关键词，边搜边筛"),
        ("实时统计", "已选 9 条 · 总时长 1:46 · 33.31 MB"),
        ("导出清单", "一键存成 TXT，交给剪辑或归档"),
    ])
    tip_panel(canvas, end + 6,
              "筛选是纯本地查询，改标签或关键词立即刷新，不会重新识别一遍。")
    footer(canvas, 5)
    return canvas.convert("RGB")


def step_four() -> Image.Image:
    canvas = background()
    canvas = brand(canvas)
    d = ImageDraw.Draw(canvas)
    kicker(d, M, 190, "STEP 04 · 批量")
    d.text((M, 236), "选中的，", font=f_bd(76), fill=INK)
    d.text((M, 330), "一个对话框全处理。", font=f_bd(76), fill=ACCENT_DEEP)
    d.text((M, 448), "转封装、压缩转码、自定义命令；先看预览，再开始。", font=f_rg(30), fill=MUTED)

    shot_w = 880
    shot = Image.open(SHOTS / "batch-hi.png")
    canvas, bottom = paste_window(canvas, shot, M, 502, shot_w)

    geo = load_geo("xhs-geometry-batch.json")
    scale = shot_w / (960 * DPI_SCALE)
    ox, oy = M, 502

    def to_box(rect):
        x, y, w, h = (v * DPI_SCALE for v in rect)
        return (ox + x * scale, oy + y * scale, ox + (x + w) * scale, oy + (y + h) * scale)

    d = ImageDraw.Draw(canvas)
    ring(d, to_box(geo["copy"]))
    ring(d, to_box(geo["run"]))

    end = bullets(canvas, bottom + 40, [
        ("三种任务", "快速转换 / 压缩转码 / 自定义命令"),
        ("先看再跑", "每个文件都有命令预览，输出自动防冲突"),
    ])
    tip_panel(canvas, end + 2,
              "参数不熟就选「快速转换」或「压缩转码」的均衡档，画质和体积都稳妥。")
    footer(canvas, 6)
    return canvas.convert("RGB")


def download() -> Image.Image:
    canvas = background()
    canvas = brand(canvas)
    d = ImageDraw.Draw(canvas)
    kicker(d, M, 190, "下载")
    d.text((M, 236), "免费开源，", font=f_bd(84), fill=INK)
    d.text((M, 338), "解压就能用。", font=f_bd(84), fill=ACCENT_DEEP)
    paragraph(d, M, 470,
              "不需要 Python，不需要先装 FFmpeg，模型和运行库都在包里。",
              f_rg(33), BODY, CARD_W - 20, 48)

    top = 566
    canvas = shadowed(canvas, (M, top, W - M, top + 436), 28, 26, 16, 55)
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle((M, top, W - M, top + 436), 28, fill=WHITE, outline=HAIR, width=2)

    d.text((M + 44, top + 38), "GitHub Releases", font=f_bd(26), fill=MUTED)
    d.text((M + 44, top + 82), "yvgui2004/media-filter", font=f_mono(40), fill=INK)
    d.line((M + 44, top + 146, W - M - 44, top + 146), fill=HAIR, width=2)
    d.text((M + 44, top + 170), "下载 MediaFilter-0.2.0-win64.zip", font=f_bd(31), fill=INK)
    d.text((M + 44, top + 216), "约 168 MB · Windows 10 / 11 64 位", font=f_rg(27), fill=BODY)

    steps = [("①", "下载 zip"), ("②", "解压到任意目录"), ("③", "双击 MediaFilter.exe")]
    x = M + 44
    for mark, text in steps:
        label = f"{mark} {text}"
        x = chip(d, x, top + 274, label, f_bd(24), ACCENT_TINT, ACCENT_DEEP,
                 h=50, pad=20, outline=HAIR) + 10

    bx = M + 44
    for label in ("MIT 协议", "196 项测试", "离线可用"):
        bx = chip(d, bx, top + 352, label, f_bd(24), ACCENT_TINT, ACCENT_DEEP,
                  h=48, pad=20, outline=HAIR) + 12

    d.text((M, 1046), "也可以直接访问落地页", font=f_bd(29), fill=INK)
    d.text((M, 1094), "yvgui2004.github.io/media-filter", font=f_mono(33), fill=ACCENT_DEEP)
    d.text((M, 1156), "开源地址 · 文档 · 更新日志 · 问题反馈", font=f_rg(25), fill=MUTED)

    d.rounded_rectangle((M, 1266, W - M, 1442), 22, fill=ACCENT_TINT, outline=HAIR, width=2)
    paragraph(d, M + 36, 1298,
              "觉得有用的话，去仓库点个 Star。\n这是独立开发者继续更新的最大动力。",
              f_rg(29), BODY, CARD_W - 72, 46)
    footer(canvas, 7)
    return canvas.convert("RGB")


def main() -> None:
    cards = [cover, comparison, step_one, step_two, step_three, step_four, download]
    for i, make in enumerate(cards, start=1):
        img = make()
        path = OUT / f"{i:02d}.png"
        img.save(path, "PNG")
        print(f"  {path}  {img.width}x{img.height}")


if __name__ == "__main__":
    main()