"""拼版内核：全部用 PyMuPDF 实现（比 pypdf 快一个数量级）。

这里只有纯逻辑，不依赖 Qt，方便单测。
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import pymupdf as fitz

A4_W, A4_H = 595.276, 841.890


def friendly_error(err: Exception, path: str = "") -> str:
    """把库的原始报错翻译成用户能看懂的一句话。"""
    msg = f"{type(err).__name__}: {err}"
    low = msg.lower()
    name = os.path.basename(path) if path else ""
    who = f"「{name}」" if name else "这个 PDF"
    if "encrypted" in low or "password" in low or "needs_pass" in low:
        return f"{who}设了打开密码。请先用别的软件去掉密码再导入。"
    if "filedataerror" in low or "failed to open" in low or "no such file" in low:
        return f"打不开{who}：文件可能已损坏，或者它并不是真正的 PDF。"
    if "zero pages" in low or "no pages" in low:
        return f"{who}里没有页面。"
    if "permission" in low or "access is denied" in low or "errno 13" in low:
        return "文件正被别的程序占用（比如阅读器还开着）。关掉它，或换个输出文件夹再试。"
    if "no space" in low or "errno 28" in low:
        return "磁盘空间不够了，清理一下再试。"
    return f"处理{who}时出错：{err}"


def unique_path(path: str) -> str:
    """目标已存在时自动加 -2/-3，绝不覆盖用户已有文件。"""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{base}-{i}{ext}"):
        i += 1
    return f"{base}-{i}{ext}"
MM = 72 / 25.4
ProgressCb = Callable[[int, int], None] | None


# ---------------------------------------------------------------- 页面摆放
def place_page(dst: fitz.Page, src: fitz.Document, pno: int, cell: fitz.Rect,
               mode: str = "contain", margin: float = 0.0, rotate: int = 0,
               overlay: bool = True) -> None:
    """把 src 的第 pno 页放进 dst 的 cell 矩形里。

    mode: contain 等比适应 / cover 等比填满(裁边) / stretch 拉伸 / center 原大小居中
    rotate: 0 或 90（逆时针）
    """
    r = fitz.Rect(cell)
    if margin:
        r = fitz.Rect(r.x0 + margin, r.y0 + margin, r.x1 - margin, r.y1 - margin)
    if r.is_empty:
        return

    src_page = src[pno]
    sw, sh = src_page.rect.width, src_page.rect.height
    if rotate % 180 == 90:
        sw, sh = sh, sw

    if mode == "center":
        w = min(sw, r.width)
        h = min(sh, r.height)
        box = fitz.Rect(0, 0, w, h)
        box = box + (r.tl + ((r.width - w) / 2, (r.height - h) / 2))
        dst.show_pdf_page(box, src, pno, keep_proportion=True, overlay=overlay,
                          rotate=rotate)
        return

    if mode == "cover":
        scale = max(r.width / sw, r.height / sh)
        vis_w, vis_h = r.width / scale, r.height / scale
        # 源页里的可见区域（fitz 坐标，左上原点）
        cx, cy = src_page.rect.width / 2, src_page.rect.height / 2
        if rotate % 180 == 90:
            cx, cy = cy, cx
            vis_w, vis_h = vis_h, vis_w
        clip = fitz.Rect(cx - vis_w / 2, cy - vis_h / 2, cx + vis_w / 2, cy + vis_h / 2)
        try:
            dst.show_pdf_page(r, src, pno, keep_proportion=False, overlay=overlay,
                              rotate=rotate, clip=clip)
            return
        except Exception:
            mode = "contain"  # 老版本不支持 clip 时退回 contain

    keep = mode == "contain"
    dst.show_pdf_page(r, src, pno, keep_proportion=keep, overlay=overlay, rotate=rotate)


# ---------------------------------------------------------------- 页码编排
def split_signatures(total_pages: int, max_sheets: int = 5) -> list[int]:
    """把总页数分成若干帖，每帖页数是 4 的倍数；不出现只有 1 张纸的末帖。

    返回每帖的页数（不含补白）。
    """
    total_pages = max(int(total_pages), 0)
    if total_pages == 0:
        return []
    total_sheets = math.ceil(total_pages / 4)
    if total_sheets <= max_sheets:
        return [total_pages]

    # 帖数取最接近的整数（不是一味向上取整），这样不会多出一个只有 4 张的尾巴
    k = max(1, int(round(total_sheets / max_sheets)))
    while k > 1 and total_sheets / k > max_sheets + 0.5:
        k += 1
    while k > 1 and total_sheets // k < 2:      # 每帖至少 2 张纸
        k -= 1
    base, rem = divmod(total_sheets, k)
    out, left = [], total_pages
    for i in range(k):
        # 少纸的帖放前面、满帖放后面（与已验收的四册书一致）
        sheets = base + (0 if i < k - rem else 1)
        take = min(sheets * 4, left)
        out.append(take)
        left -= take
    return [x for x in out if x > 0]


def booklet_sheets(pages_in_sig: int) -> list[list[int | None]]:
    """一帖的纸张顺序：每张 [正面左, 正面右, 背面左, 背面右]（书页号从 1 起，None=空白）。"""
    padded = pages_in_sig + (-pages_in_sig) % 4
    out = []
    for i in range(padded // 4):
        out.append([
            padded - 2 * i,          # 正面左 = 末页
            1 + 2 * i,               # 正面右 = 首页
            2 + 2 * i,               # 背面左
            padded - 1 - 2 * i,      # 背面右
        ])
    return out


def booklet_plan(total_pages: int, max_sheets: int = 5, skip: int = 0,
                 start_page: int = 1) -> list[dict]:
    """返回 [{offset, count, sheets:[...]}, ...]，供渲染与统计共用。"""
    offset = skip + (start_page - 1)
    effective = total_pages - offset
    if effective <= 0:
        return []
    plan, cursor = [], offset
    for count in split_signatures(effective, max_sheets):
        plan.append({"offset": cursor, "count": count,
                     "sheets": booklet_sheets(count)})
        cursor += count
    return plan


def fourstack_order(total_pages: int, skip: int = 0, start_page: int = 1
                    ) -> tuple[list[int | None], int, int]:
    """四堆叠放：每张纸 8 页（正 4 背 4）。返回 (顺序, 张数, 每堆页数)。"""
    offset = skip + (start_page - 1)
    effective = total_pages - offset
    if effective <= 0:
        return [], 0, 0
    sheets = math.ceil(effective / 8)
    padded = sheets * 8
    group = padded // 4
    order: list[int | None] = []
    for n in range(1, sheets + 1):
        for g in (0, 1, 2, 3):
            pno = g * group + (2 * n - 1)
            order.append(offset + pno - 1 if pno <= effective else None)
        for g in (1, 0, 3, 2):
            pno = g * group + 2 * n
            order.append(offset + pno - 1 if pno <= effective else None)
    return order, sheets, group


# ---------------------------------------------------------------- 输出
def new_a4(landscape: bool = False) -> tuple[fitz.Document, fitz.Page]:
    doc = fitz.open()
    return doc, doc.new_page(width=A4_W, height=A4_H)


def _a6_from_a5(doc5: fitz.Document) -> fitz.Document:
    """把 A5 小册子的每一面两两上下拼成 A4（A6 成书）。

    配对规则：正面与正面同张（0,2），背面与背面同张（1,3）。
    这样沿中线横切后，上/下两张各自"正面-背面"仍然对得上。
    """
    out = fitz.open()
    n = len(doc5)
    half_h = A4_H / 2
    for k in range(0, n, 4):
        for side in (0, 1):                       # 0=正面页, 1=背面页
            page = out.new_page(width=A4_W, height=A4_H)
            for j, idx in enumerate((k + side, k + side + 2)):
                if idx >= n:
                    continue
                cell = fitz.Rect(0, j * half_h, A4_W, (j + 1) * half_h)
                page.show_pdf_page(cell, doc5, idx, keep_proportion=True)
            # 横切辅助线
            page.draw_line(fitz.Point(0, half_h), fitz.Point(A4_W, half_h),
                           color=(0.7, 0.25, 0.2), width=0.6,
                           dashes="[3 3] 0")
    return out


def impose_booklet(src_path: str, out_path: str, max_sheets: int = 5,
                   binding: str = "left", mirror: bool = False,
                   mode: str = "contain", margin_mm: float = 0.0,
                   skip: int = 0, start_page: int = 1,
                   book_size: str = "A5",
                   progress: ProgressCb = None) -> dict:
    src = fitz.open(src_path)
    plan = booklet_plan(len(src), max_sheets, skip, start_page)
    out = fitz.open()
    gutter = 0.0          # A4 横向的一半正好是 A5，中缝不留白
    margin = margin_mm * MM
    total = sum(len(p["sheets"]) for p in plan) or 1
    done = 0
    blanks = 0

    # 小册子用 A4 横向：对折后每半张正好是 A5（148×210mm = 419.5×595.3pt）
    sheet_w, sheet_h = A4_H, A4_W
    cw = (sheet_w - gutter) / 2
    _pw, _ph = src[0].rect.width, src[0].rect.height
    _, m_v, m_h = _fit_margins(cw, sheet_h, _pw, _ph, margin)

    for sig in plan:
        for sheet in sig["sheets"]:
            page = out.new_page(width=sheet_w, height=sheet_h)
            cells = [fitz.Rect(0, 0, cw, sheet_h),
                     fitz.Rect(cw + gutter, 0, sheet_w, sheet_h)]
            front, back = sheet[:2], sheet[2:]

            if binding == "right":
                front = front[::-1]
                back = back[::-1]
            if mirror:
                back = back[::-1]

            for cell, pno in zip(cells, front):
                _draw(page, src, cell, pno, sig, mode, margin)
            page2 = out.new_page(width=sheet_w, height=sheet_h)
            for cell, pno in zip(cells, back):
                _draw(page2, src, cell, pno, sig, mode, margin)
            blanks += sum(1 for p in sheet if p is None or p > sig["count"])
            done += 1
            if progress:
                progress(done, total)
    sheets_total = sum(len(p["sheets"]) for p in plan)
    if book_size == "A6":
        final = _a6_from_a5(out)
        out.close()
        out = final
        sheets_total = len(out) // 2
        pages_total = len(out)
    else:
        pages_total = sheets_total * 2

    out.save(out_path, garbage=1, deflate=True)
    out.close()
    src.close()
    return {"signatures": len(plan), "sheets": sheets_total,
            "pages": pages_total, "blanks": blanks,
            "groups": [p["count"] for p in plan], "size": book_size,
            "margins_mm": {"top": m_v / MM, "bottom": m_v / MM,
                           "left": m_h / MM, "right": m_h / MM}}


def _draw(dst, src, cell, pno, sig, mode, margin, rotate=0):
    if pno is None or pno > sig["count"]:
        return
    idx = sig["offset"] + pno - 1
    if idx < 0 or idx >= len(src):
        return
    place_page(dst, src, idx, cell, mode=mode, margin=margin, rotate=rotate)


def impose_fourstack(src_path: str, out_path: str, binding: str = "left",
                     mode: str = "contain", margin_mm: float = 0.0,
                     skip: int = 0, start_page: int = 1,
                     progress: ProgressCb = None) -> dict:
    src = fitz.open(src_path)
    order, sheets, _ = fourstack_order(len(src), skip, start_page)
    out = fitz.open()
    gutter = 10.0
    cw = (A4_W - gutter) / 2
    ch = (A4_H - gutter) / 2
    cells = [fitz.Rect(0, 0, cw, ch), fitz.Rect(cw + gutter, 0, A4_W, ch),
             fitz.Rect(0, ch + gutter, cw, A4_H), fitz.Rect(cw + gutter, ch + gutter, A4_W, A4_H)]
    margin = margin_mm * MM
    _pw, _ph = src[0].rect.width, src[0].rect.height
    _, m_v, m_h = _fit_margins(cw, ch, _pw, _ph, margin)
    blanks = 0
    for s in range(sheets):
        chunk = order[s * 8:(s + 1) * 8]
        for side, half in enumerate((chunk[:4], chunk[4:])):
            page = out.new_page(width=A4_W, height=A4_H)
            # 与旧版一致：左装订时正面转 0/2 格，背面转 1/3 格（右装订相反）
            rotate_groups = (0, 2) if side == 0 else (1, 3)
            if binding != "left":
                rotate_groups = tuple(g for g in range(4) if g not in rotate_groups)
            for gi, (cell, pno) in enumerate(zip(cells, half)):
                if pno is None:
                    blanks += 1
                    continue
                rot = 180 if gi in rotate_groups else 0
                place_page(page, src, pno, cell, mode=mode, margin=margin, rotate=rot)
        if progress:
            progress(s + 1, sheets)
    out.save(out_path, garbage=1, deflate=True)
    out.close(); src.close()
    return {"sheets": sheets, "pages": sheets * 2, "blanks": blanks,
            "margins_mm": {"top": m_v / MM, "bottom": m_v / MM,
                           "left": m_h / MM, "right": m_h / MM}}


def _fit_margins(cw: float, ch: float, pw: float, ph: float, m: float, inset: int = 2):
    """页面 pw×ph 放进 cw×ch 的格子、四边至少留 m，返回 (缩放, 上下实际边距, 左右实际边距)。

    页面比例和格子比例不会完全一致，所以总有一边多于设定值 —— 这个函数把真实值算出来，
    界面照实报，别让人以为填 10mm 就真的四面都是 10mm。

    inset：格子被扣了几倍的边距。4合1 是每格只扣一份（1），其余拼版是四边各扣（2）。
    """
    aw = max(cw - inset * m, 1.0)
    ah = max(ch - inset * m, 1.0)
    s = min(aw / pw, ah / ph)
    return s, m + (ah - ph * s) / 2, m + (aw - pw * s) / 2


def impose_fourup(src_path: str, out_path: str, layout: str = "A",
                  margin_mm: float = 10.0, start_page: int = 1,
                  progress: ProgressCb = None) -> dict:
    src = fitz.open(src_path)
    order = {"A": [0, 1, 2, 3], "B": [0, 2, 1, 3],
             "C": [2, 0, 3, 1], "D": [1, 0, 3, 2]}[layout]
    margin = margin_mm * MM
    cell_w = (A4_W - 2 * margin) / 2
    cell_h = (A4_H - 2 * margin) / 2
    # 顺序：左上 / 右上 / 左下 / 右下（PyMuPDF 的 y 轴向下）
    cells = [fitz.Rect(margin, margin, margin + cell_w, margin + cell_h),
             fitz.Rect(margin + cell_w, margin, margin + 2 * cell_w, margin + cell_h),
             fitz.Rect(margin, margin + cell_h, margin + cell_w, margin + 2 * cell_h),
             fitz.Rect(margin + cell_w, margin + cell_h, margin + 2 * cell_w, margin + 2 * cell_h)]
    out = fitz.open()
    start = max(start_page - 1, 0)
    groups = list(range(start, len(src), 4)) or [start]
    m_v = m_h = None
    for gi, base in enumerate(groups):
        page = out.new_page(width=A4_W, height=A4_H)
        for slot, off in enumerate(order):
            pno = base + off
            if pno < len(src):
                # 边距已经在格子上扣过了，这里不再叠加隐藏边距（原来多扣 3pt，填 0 也贴不到边）
                place_page(page, src, pno, cells[slot], mode="contain", margin=0)
                if m_v is None:
                    pw, ph = src[pno].rect.width, src[pno].rect.height
                    # 格子已经按边距缩过了，这里要用整格（未扣边距）来算真实距离
                    _, m_v, m_h = _fit_margins(A4_W / 2, A4_H / 2, pw, ph, margin, inset=1)
        if progress:
            progress(gi + 1, len(groups))
    out.save(out_path, garbage=1, deflate=True)
    out.close(); src.close()
    return {"sheets": len(groups), "pages": len(groups),
            "margins_mm": {"top": (m_v or 0) / MM, "bottom": (m_v or 0) / MM,
                           "left": (m_h or 0) / MM, "right": (m_h or 0) / MM}}


def impose_a5a4(src_path: str, out_path: str, rotate: bool = True,
                mode: str = "contain", margin_mm: float = 0.0,
                progress: ProgressCb = None) -> dict:
    src = fitz.open(src_path)
    n = len(src)
    half = n // 2
    part1 = half if half % 2 == 0 else half + 1
    iterations = max(part1, n - part1)
    margin = margin_mm * MM
    out = fitz.open()
    pw, ph = src[0].rect.width, src[0].rect.height
    if rotate:
        pw, ph = ph, pw
    _, m_v, m_h = _fit_margins(A4_W, A4_H / 2, pw, ph, margin)
    for i in range(iterations):
        page = out.new_page(width=A4_W, height=A4_H)
        top = fitz.Rect(0, 0, A4_W, A4_H / 2)
        bottom = fitz.Rect(0, A4_H / 2, A4_W, A4_H)
        if i < part1:
            place_page(page, src, i, top, mode=mode, margin=margin,
                       rotate=(90 if rotate else 0))
        if part1 + i < n:
            place_page(page, src, part1 + i, bottom, mode=mode, margin=margin,
                       rotate=(90 if rotate else 0))
        if progress:
            progress(i + 1, iterations)
    out.save(out_path, garbage=1, deflate=True)
    out.close(); src.close()
    return {"sheets": iterations, "pages": iterations,
            "blanks": iterations * 2 - n,
            "margins_mm": {"top": m_v / MM, "bottom": m_v / MM,
                           "left": m_h / MM, "right": m_h / MM}}


def add_page_numbers(src_path: str, out_path: str, start: int = 1,
                     fmt: str = "{n}", pos: str = "bottom-center",
                     font_size: float = 10.0, margin_mm: float = 12.0,
                     mirror: bool = False, skip: int = 0,
                     color: tuple = (0, 0, 0),
                     progress: ProgressCb = None) -> dict:
    """给每页加页码。

    fmt: {n} 当前页码，{total} 最后一页的页码（都从 start 起算）
    pos: bottom-center（下中）/ bottom-outer（下外侧）/ top-outer（上外侧）
    mirror: 右装订时勾上，外侧左右对调
    skip: 前几页不编号（例如封面）
    """
    doc = fitz.open(src_path)
    total_pages = len(doc)
    margin = margin_mm * MM
    last_no = start + max(0, total_pages - skip) - 1
    added = 0
    count = max(1, total_pages - skip)

    for i in range(skip, total_pages):
        page = doc[i]
        num = start + (i - skip)
        text = fmt.replace("{n}", str(num)).replace("{total}", str(last_no))
        if not text:
            continue
        w = fitz.get_text_length(text, fontname="china-s", fontsize=font_size)
        r = page.rect
        odd = ((i - skip) % 2 == 0)          # 第一页算奇数页

        if pos == "bottom-center":
            x = (r.width - w) / 2
            y = r.height - margin
        else:
            outer_right = odd
            if mirror:
                outer_right = not outer_right
            x = (r.width - margin - w) if outer_right else margin
            y = (margin + font_size) if pos.startswith("top") else (r.height - margin)

        try:
            page.insert_text((x, y), text, fontname="china-s",
                             fontsize=font_size, color=color, overlay=True)
            added += 1
        except Exception:
            pass
        if progress:
            progress(i - skip + 1, count)

    doc.save(out_path, garbage=1, deflate=True)
    doc.close()
    return {"pages": total_pages, "numbered": added}


def add_page_numbers_preview(src_path: str, out_path: str, limit: int = 6, **kw) -> dict:
    """预览用：只取前几页编号，参数与正式版一致。"""
    with fitz.open(src_path) as src:
        n = min(limit, len(src))
        tmp = fitz.open()
        tmp.insert_pdf(src, from_page=0, to_page=n - 1)
        tmp_path = out_path + ".src.pdf"
        tmp.save(tmp_path)
        tmp.close()
    try:
        return add_page_numbers(tmp_path, out_path, **kw)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def merge_pdfs(paths: Sequence[str], out_path: str) -> dict:
    out = fitz.open()
    for p in paths:
        with fitz.open(p) as d:
            out.insert_pdf(d)
    out.save(out_path, garbage=1, deflate=True)
    n = len(out)
    out.close()
    return {"pages": n}


def thumbnail(path_or_doc, pno: int = 0, dpi: int = 40) -> bytes:
    doc = path_or_doc if isinstance(path_or_doc, fitz.Document) else fitz.open(path_or_doc)
    pix = doc[pno].get_pixmap(dpi=dpi)
    data = pix.tobytes("png")
    if not isinstance(path_or_doc, fitz.Document):
        doc.close()
    return data
