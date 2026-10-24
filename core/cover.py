"""封面：封底 / 书脊 / 封面 展开图。

四种版式（classic 竖排文学 / modern 教材 / minimal 极简 / image 满图），
每套都有配色；书脊可按页数和纸张克重自动算厚度。
单位换算按 dpi 走：pt→px = pt * dpi / 72。
"""
from __future__ import annotations

import os
from typing import Optional

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = r"C:\Windows\Fonts\simsun.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"
FONT_MAP = {
    "宋体": r"C:\Windows\Fonts\simsun.ttc",
    "黑体": r"C:\Windows\Fonts\simhei.ttf",
    "微软雅黑": r"C:\Windows\Fonts\msyh.ttc",
    "楷体": r"C:\Windows\Fonts\simkai.ttf",
}

MM = 1 / 25.4

# 纸厚（mm/张），双面书页 = 页数/2 张
PAPER_THICK = {
    "70g 胶版": 0.09,
    "80g 胶版": 0.104,
    "100g 胶版": 0.125,
    "128g 铜版": 0.13,
    "157g 铜版": 0.16,
}

TEMPLATES = {
    "classic": "竖排文学",
    "modern": "教材技术",
    "minimal": "极简留白",
    "image": "满图压字",
}

PALETTES = {
    "米白·朱红": {"paper": "#F2ECE0", "ink": "#211E1A", "accent": "#B23A2E",
                 "back": "#E7DECB", "spine": "#B23A2E", "spine_ink": "#FBF3E6"},
    "藏青·米白": {"paper": "#F3EEE3", "ink": "#1B2C3E", "accent": "#1B2C3E",
                 "back": "#1B2C3E", "spine": "#1B2C3E", "spine_ink": "#F3EEE3"},
    "墨黑·银灰": {"paper": "#F4F4F2", "ink": "#111111", "accent": "#111111",
                 "back": "#111111", "spine": "#111111", "spine_ink": "#EDEDED"},
    "灰蓝·白": {"paper": "#FFFFFF", "ink": "#22303A", "accent": "#8C9AA3",
                "back": "#8C9AA3", "spine": "#22303A", "spine_ink": "#FFFFFF"},
    "砖红·暖白": {"paper": "#B23A2E", "ink": "#FBF7F0", "accent": "#E8DCC8",
                 "back": "#8E2E24", "spine": "#E8DCC8", "spine_ink": "#8E2E24"},
}


def _px(mm: float, dpi: int) -> int:
    return max(1, int(round(mm * MM * dpi)))


def _font(path: str, px: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, max(4, int(px)))
    except Exception:
        return ImageFont.load_default()


def spine_from_pages(pages: int, paper: str = "80g 胶版") -> float:
    """书脊厚度（mm）：页数 ÷ 2 × 每张纸厚。"""
    t = PAPER_THICK.get(paper, 0.104)
    return round(max(0.0, pages) / 2 * t, 1)


def load_source(src, dpi: int = 200) -> Image.Image:
    if isinstance(src, (tuple, list)):
        path, page = src[0], int(src[1])
        with fitz.open(path) as doc:
            page = max(0, min(page, len(doc) - 1))
            pix = doc[page].get_pixmap(dpi=dpi)
            return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    with Image.open(src) as im:
        return im.convert("RGB")


def _fit_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    iw, ih = img.size
    s = max(w / iw, h / ih)
    im = img.resize((max(1, int(iw * s)), max(1, int(ih * s))), Image.LANCZOS)
    x = (im.width - w) // 2
    y = (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def _fit_contain(img: Image.Image, w: int, h: int, bg=(255, 255, 255)) -> Image.Image:
    """等比适应：整张图都保留，四周用底色补齐。"""
    iw, ih = img.size
    s = min(w / iw, h / ih)
    im = img.resize((max(1, int(iw * s)), max(1, int(ih * s))), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), bg)
    canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return canvas


def _hex(c: str):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _spine_fit(text: str, px: int, width_px: int) -> int:
    f = _font(FONT_PATH, px)
    longest = max((f.getbbox(ch)[2] - f.getbbox(ch)[0]) for ch in text) if text else 0
    if longest and longest > width_px * 0.72:
        return max(6, int(px * width_px * 0.72 / longest))
    return px


def _fit_title(draw, text, font_path, px, max_w, min_px=10):
    f = _font(font_path, px)
    while draw.textlength(text, font=f) > max_w and px > min_px:
        px = int(px * 0.92)
        f = _font(font_path, px)
    return f, px


def _wrap(draw, text: str, font, max_w: float) -> list:
    """按实际宽度折行：中文逐字、英文按词。"""
    out = []
    for para in text.split("\n"):
        if not para.strip():
            out.append("")
            continue
        line = ""
        for token in _tokens(para):
            trial = line + token
            if line and draw.textlength(trial, font=font) > max_w:
                out.append(line.rstrip())
                line = token.lstrip()
            else:
                line = trial
        if line.strip():
            out.append(line.rstrip())
    return out


def _tokens(text: str):
    """中文按字切，连续英文/数字按词切。"""
    buf, word = [], ""
    for ch in text:
        if ch.isascii() and not ch.isspace():
            word += ch
        else:
            if word:
                buf.append(word)
                word = ""
            buf.append(ch)
    if word:
        buf.append(word)
    return buf


def _draw_vertical(draw, text, x_center, y_top, px, fill, height):
    f = _font(FONT_PATH, px)
    cell = min(px * 1.32, height / max(1, len(text)))
    y = y_top
    for ch in text:
        if not ch.strip():
            continue
        bbox = draw.textbbox((0, 0), ch, font=f)
        wch, hch = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((x_center - wch / 2 - bbox[0], y + (cell - hch) / 2 - bbox[1]),
                  ch, font=f, fill=fill)
        y += cell


def render_cover(width_mm: float, height_mm: float, spine_mm: float,
                 bleed_mm: float = 3.0, dpi: int = 300,
                 front_img: Optional[str] = None, back_img: Optional[str] = None,
                 spine_img: Optional[str] = None,
                 title: str = "", subtitle: str = "", author: str = "",
                 spine_text: Optional[str] = None, vertical: bool = True,
                 spine_pt: float = 16, front_bg: str = "", back_bg: str = "",
                 spine_bg: str = "", ink: str = "", accent: str = "",
                 title_font: str = "宋体", title_color: Optional[str] = None,
                 back_text: str = "", crop_marks: bool = False,
                 template: str = "classic", palette: str = "米白·朱红",
                 publisher: str = "", series: str = "",
                 barcode: bool = True, fit: str = "cover",
                 sheet: str = "cover", safety_mm: float = 5.0) -> Image.Image:
    """返回展开图（RGB）。尺寸 = 2W + 书脊 + 2×出血 × (H + 2×出血)。"""
    pal = PALETTES.get(palette, PALETTES["米白·朱红"])
    paper = front_bg or pal["paper"]
    ink_c = ink or pal["ink"]
    accent_c = accent or pal["accent"]
    back_c = back_bg or pal["back"]
    spine_c = spine_bg or pal["spine"]
    spine_ink = pal["spine_ink"]

    B = _px(bleed_mm, dpi)
    W = _px(width_mm, dpi)
    H = _px(height_mm, dpi)
    S = max(1, _px(spine_mm, dpi))
    total_w, total_h = W * 2 + S + 2 * B, H + 2 * B
    canvas = Image.new("RGB", (total_w, total_h), (255, 255, 255))

    def panel(img_path, w, h, bg):
        if img_path:
            try:
                src = load_source(img_path, dpi=min(dpi, 300))
                if fit == "contain":
                    return _fit_contain(src, w, h, _hex(bg))
                if fit == "stretch":
                    return src.resize((w, h), Image.LANCZOS)
                return _fit_cover(src, w, h)
            except Exception:
                pass
        return Image.new("RGB", (w, h), bg)

    back = panel(back_img, W + B, H + 2 * B, back_c)
    canvas.paste(back, (0, 0))
    spine = panel(spine_img, S, H + 2 * B, spine_c)
    canvas.paste(spine, (W + B, 0))
    front = panel(front_img, W + B, H + 2 * B, paper)
    canvas.paste(front, (W + B + S, 0))

    draw = ImageDraw.Draw(canvas)
    fx0 = W + B + S
    m = W * 0.085
    tf = FONT_MAP.get(title_font, FONT_PATH)
    filled = bool(front_img)          # 满图时文字要反白

    # ---------------- 封面 ----------------
    if template == "classic":
        # 双细线边框 + 竖排书名（右侧一列），副题竖排在左，作者沉底但留安全距
        inset = W * 0.062
        draw.rectangle([fx0 + inset, B + inset, fx0 + W - inset, B + H - inset],
                       outline=accent_c, width=max(2, H // 500))
        draw.rectangle([fx0 + inset * 1.18, B + inset * 1.18,
                        fx0 + W - inset * 1.18, B + H - inset * 1.18],
                       outline=accent_c, width=1)
        avail_h = H - 2 * inset * 1.5
        t_px = int(min(W * 0.135, avail_h * 0.60 / max(1, len(title)) * 1.9))
        title_cx = fx0 + W - inset * 1.6 - t_px * 0.62
        _draw_vertical(draw, title, title_cx, B + inset * 2.95, t_px,
                       title_color or ink_c, avail_h * 0.68)
        if subtitle:
            s_px = max(10, int(t_px * 0.40))
            _draw_vertical(draw, subtitle, title_cx - t_px * 1.55,
                           B + inset * 2.4, s_px, ink_c, avail_h * 0.62)
        if author:
            a_size = int(H * 0.032)
            f = _font(FONT_PATH, a_size)
            tw = draw.textlength(author, font=f)
            a_x = fx0 + inset * 1.7
            a_y = B + H - inset * 2.5 - a_size
            draw.text((a_x, a_y), author, font=f, fill=ink_c)
            # 短横线放在文字下方，留 ~40% 字高间距，绝不压字
            rule_y = a_y + a_size * 1.42
            draw.rectangle([a_x, rule_y, a_x + min(tw * 0.55, W * 0.18),
                            rule_y + max(2, H // 480)], fill=accent_c)

    elif template == "modern":
        band = H * 0.20
        draw.rectangle([fx0, B, fx0 + W, B + band], fill=accent_c)
        f, size = _fit_title(draw, title, FONT_BOLD, int(band * 0.44), W - 2 * m)
        tc = "#FBF7F0" if sum(_hex(accent_c)) < 380 else "#1A1A1A"
        bb = draw.textbbox((0, 0), title, font=f)
        draw.text((fx0 + m, B + band / 2 - (bb[3] - bb[1]) / 2 - bb[1]),
                  title, font=f, fill=tc)
        y = B + band + H * 0.075
        if subtitle:
            f2, s2 = _fit_title(draw, subtitle, tf, int(H * 0.055), W - 2 * m)
            draw.text((fx0 + m, y), subtitle, font=f2, fill=ink_c)
            y += s2 * 1.7
        draw.rectangle([fx0 + m, y + H * 0.02, fx0 + m + W * 0.20,
                        y + H * 0.02 + max(3, H // 260)], fill=accent_c)
        if series:
            f3 = _font(tf, int(H * 0.030))
            draw.text((fx0 + m, B + H * 0.60), series, font=f3, fill=ink_c)
        if author:
            f4 = _font(tf, int(H * 0.036))
            draw.text((fx0 + m, B + H - m), author, font=f4, fill=ink_c)
        if publisher:
            f5 = _font(tf, int(H * 0.026))
            tw = draw.textlength(publisher, font=f5)
            draw.text((fx0 + W - m - tw, B + H - m), publisher, font=f5,
                      fill=accent_c)

    elif template == "image":
        # 满图压字：底部一层真渐变（用 L 通道当遮罩合成）
        if not front_img:
            draw.rectangle([fx0, B, fx0 + W, B + H], fill=paper)
        grad_h = int(H * 0.58)
        mask = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(mask)
        for i in range(grad_h):
            alpha = int(225 * (i / max(1, grad_h - 1)) ** 1.25)
            md.line([(0, H - grad_h + i), (W, H - grad_h + i)], fill=alpha)
        region = canvas.crop((fx0, B, fx0 + W, B + H))
        dark = Image.new("RGB", (W, H), (0, 0, 0))
        region = Image.composite(dark, region, mask)
        # 8 位色深下深色渐变会有色带：只在渐变区撒一点极细的噪点把它打散
        grain = Image.effect_noise((W, H), 7).convert("RGB")
        region = Image.composite(Image.blend(region, grain, 0.045), region,
                                 mask.point(lambda v: min(255, int(v * 1.6))))
        canvas.paste(region, (fx0, B))
        # 从下往上堆，避免标题和副题打架
        base = B + H - m * 1.55
        author_size = int(H * 0.030)
        sub_size = int(H * 0.042)
        f, size = _fit_title(draw, title, FONT_BOLD, int(H * 0.115), W - 2 * m)
        y_author = base - author_size
        y_sub = y_author - sub_size * 1.75
        y_title = y_sub - size * 1.22
        if y_title < B + H * 0.22:          # 太长就整体上移一点
            y_title = B + H * 0.22
        draw.text((fx0 + m, y_title), title, font=f, fill="#FFFFFF")
        if subtitle:
            f2, s2 = _fit_title(draw, subtitle, tf, sub_size, W - 2 * m)
            draw.text((fx0 + m, y_title + size * 1.24), subtitle, font=f2, fill="#F2F2F2")
        if author:
            f3 = _font(tf, author_size)
            draw.text((fx0 + m, y_author), author, font=f3, fill="#EDEDED")

    else:  # minimal
        y = B + H * 0.15
        f, size = _fit_title(draw, title, tf, int(H * 0.095), W - 2 * m)
        draw.text((fx0 + m, y), title, font=f, fill=title_color or ink_c)
        y += size * 1.34
        if subtitle:
            f2, s2 = _fit_title(draw, subtitle, tf, int(H * 0.040), W - 2 * m)
            draw.text((fx0 + m, y), subtitle, font=f2, fill=ink_c)
            y += s2 * 2.15
        else:
            y += H * 0.02
        draw.rectangle([fx0 + m, y, fx0 + m + W * 0.10,
                        y + max(2, H // 420)], fill=accent_c)
        y += H * 0.045
        if series:
            f3 = _font(tf, int(H * 0.026))
            draw.text((fx0 + m, y), series, font=f3, fill=ink_c)
        if author:
            f4 = _font(tf, int(H * 0.032))
            draw.text((fx0 + m, B + H - m * 1.35), author, font=f4, fill=ink_c)

    # ---------------- 封底 ----------------
    if back_text:
        fs = int(H * 0.031)
        fb = _font(tf, fs)
        bx = B + W * 0.12
        by = B + H * 0.20
        max_w = W * 0.76
        for ln in _wrap(draw, back_text, fb, max_w):
            draw.text((bx, by), ln, font=fb,
                      fill=ink_c if template != "image" else "#F2F2F2")
            by += fs * 1.75

    if barcode and template in ("classic", "modern", "minimal"):
        bw, bh = W * 0.28, H * 0.13
        bx, by = B + W - bw - W * 0.10, B + H - bh - H * 0.07
        draw.rectangle([bx, by, bx + bw, by + bh], fill="#FFFFFF", outline="#BDBDBD")
        f = _font(tf, int(bh * 0.18))
        draw.text((bx + bw * 0.12, by + bh * 0.70), "ISBN", font=f, fill="#9E9E9E")

    if publisher and template in ("classic", "minimal"):
        f5 = _font(tf, int(H * 0.024))
        draw.text((B + W * 0.12, B + H * 0.08), publisher, font=f5, fill=ink_c)

    # ---------------- 书脊 ----------------
    text = spine_text if spine_text is not None else title
    if text:
        if vertical:
            text = "".join(ch for ch in text if ch.strip())
        px = max(6, int(spine_pt * dpi / 72))
        px = _spine_fit(text, px, S)
        if vertical and text:
            px = min(px, int(S * 0.8))
            cell = min(px, (total_h * 0.9) / max(1, len(text)))
            px = max(6, int(cell * 0.92))
        f = _font(FONT_PATH, px)
        if vertical:
            cell = (total_h * 0.86) / max(1, len(text))
            cell = min(cell, px * 1.25)
            total = cell * len(text)
            y = (total_h - total) / 2
            for ch in text:
                bbox = draw.textbbox((0, 0), ch, font=f)
                wch, hch = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.text((W + B + (S - wch) / 2 - bbox[0],
                           y + (cell - hch) / 2 - bbox[1]), ch,
                          font=f, fill=spine_ink)
                y += cell
        else:
            tw = draw.textlength(text, font=f)
            draw.text((W + B + (S - tw) / 2, (total_h - px) / 2), text,
                      font=f, fill=spine_ink)

    if sheet == "a4":
        return _compose_a4(canvas, dpi, (B, W, H, S), crop_marks, safety_mm)

    # ---------------- 裁切线（仅封面模式） ----------------
    if crop_marks:
        _marks_spread(draw, B, W, H, S, total_h, fx0)

    return canvas


def _marks_spread(draw, B, W, H, S, total_h, fx0):
    """裁切/折页线：全部落在出血区，成品框以内一根线都不画。"""
    tick = max(6, int(B * 0.8))
    right = fx0 + W
    for left, dx in ((B, -1), (right, 1)):
        for top, dy in ((B, -1), (B + H, 1)):
            x0, y0 = left + dx * 2, top + dy * 2  # 从出血里 2px 处起笔，切线绝不压线
            draw.line([(x0, y0), (x0 + dx * tick, y0)], fill="#000000", width=1)
            draw.line([(x0, y0), (x0, y0 + dy * tick)], fill="#000000", width=1)
    step = max(3, B // 3)
    for x in (W + B, W + B + S):
        for y0, y1 in ((0, B - 3), (B + H + 3, total_h)):
            yy = y0
            while yy < y1:
                draw.line([(x, yy), (x, min(yy + step, y1))], fill="#000000", width=1)
                yy += step * 2


def _compose_a4(spread: Image.Image, dpi: int, geo: tuple,
                marks: bool, safety_mm: float) -> Image.Image:
    """把展开图居中放到 A4 横向纸上；放不下就等比缩小，四周留白。

    geo = (出血px, 成品宽px, 成品高px, 书脊px)，用来算成品框和书脊折线位置。
    所有辅助线都画在成品框外（出血里或纸的空白处），裁切后封面上一根线都没有。
    """
    B, W, H, S = geo
    mm = dpi / 25.4
    sheet_w, sheet_h = int(round(297 * mm)), int(round(210 * mm))
    safe = max(4, int(round(safety_mm * mm)))
    scale = min(1.0, (sheet_w - 2 * safe) / spread.width,
                (sheet_h - 2 * safe) / spread.height)
    w = max(1, int(round(spread.width * scale)))
    h = max(1, int(round(spread.height * scale)))
    img = spread.resize((w, h), Image.LANCZOS) if scale < 1.0 else spread.copy()
    px, py = (sheet_w - w) // 2, (sheet_h - h) // 2
    canvas = Image.new("RGB", (sheet_w, sheet_h), (255, 255, 255))
    canvas.paste(img, (px, py))
    if marks:
        draw = ImageDraw.Draw(canvas)
        b = max(1, int(round(B * scale)))
        trim = (px + b, py + b, px + w - b, py + h - b)
        # 角线只画在贴图外的白边里，与成品边同一直线；连出血区都不碰
        tick = max(6, min(int(round(6 * mm)), px - 1, sheet_h - (py + h) - 1))
        for x in (trim[0], trim[2]):
            for y_top in (py, py + h):
                dy = -1 if y_top == py else 1
                draw.line([(x, y_top + dy * 2), (x, y_top + dy * (tick + 2))],
                          fill="#000000", width=1)
        for y in (trim[1], trim[3]):
            for x_left in (px, px + w):
                dx = -1 if x_left == px else 1
                draw.line([(x_left + dx * 2, y), (x_left + dx * (tick + 2), y)],
                          fill="#000000", width=1)
        # 书脊折线：只在成品上下边缘之外（出血/白边）画虚线
        step = max(3, int(round(2 * mm)))
        for gx in (B + W, B + W + S):
            fx = px + int(round(gx * scale))
            for y_start, y_end, direction in (
                    (py + b - 3, py, -1), (py + h - b + 3, py + h, 1)):
                yy = y_start
                while (yy > y_end if direction < 0 else yy < y_end):
                    yy2 = yy + direction * step
                    if direction < 0:
                        yy2 = max(y_end, yy2)
                    else:
                        yy2 = min(y_end, yy2)
                    draw.line([(fx, yy), (fx, yy2)], fill="#000000", width=1)
                    yy = yy2 + direction * step
    canvas.info["scale"] = scale
    return canvas


def save_pdf(img: Image.Image, path: str, dpi: int = 300) -> None:
    img.convert("RGB").save(path, "PDF", resolution=dpi)
