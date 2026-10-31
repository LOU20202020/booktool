"""回归自测：每次改完代码都必须跑一遍。

用法：python tests/regression.py
print("
=== 内置转换引擎：查找顺序 ===")
import tempfile as _tf
from core import convert as _C

_real_root = _C.bundle_root
_tmp = _tf.mkdtemp()
os.makedirs(os.path.join(_tmp, "Calibre"), exist_ok=True)
with open(os.path.join(_tmp, "Calibre", "ebook-convert.exe"), "w") as _fh:
    _fh.write("")
_C.bundle_root = lambda: _tmp                      # 假装程序装在这个目录
check(_C.bundled_binary().endswith("ebook-convert.exe"), "exe 旁边有 Calibre 就先用它",
      _C.bundled_binary())
check(_C.is_bundled(), "认得出这是自带的那份")
check("内置" in _C.engine_label(), "界面上写「内置 Calibre」", _C.engine_label())
check(_C.sub_env().get("CALIBRE_CONFIG_DIRECTORY", "").startswith(_tmp),
      "配置目录跟着程序走（换台机器也带得走）",
      _C.sub_env().get("CALIBRE_CONFIG_DIRECTORY", "")[:60])
os.remove(os.path.join(_tmp, "Calibre", "ebook-convert.exe"))
check(_C.bundled_binary() == "", "没有自带的那份就退回探本机安装")
_C.bundle_root = _real_root

全部通过退出码 0，失败退出码 1。
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf as fitz
from PIL import Image

from core import cover as cover_core
from core import pdfops

TMP = tempfile.mkdtemp(prefix="booktool_test_")
FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"   [{detail}]"))
    if not cond:
        FAILS.append(name)


def make_pdf(name: str, pages: int, w=419.53, h=595.28, label=True) -> str:
    path = os.path.join(TMP, name)
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page(width=w, height=h)
        if label:
            p.insert_text((60, 120), str(i + 1), fontname="helv", fontsize=90)
    doc.save(path)
    doc.close()
    return path


def texts(path: str, page: int) -> str:
    with fitz.open(path) as d:
        return d[page].get_text().replace("\n", " ")


def nums(path: str, page: int) -> list[int]:
    out = []
    for tok in texts(path, page).split():
        if tok.isdigit():
            out.append(int(tok))
    return out


def main() -> int:
    # ---------------- 小册子 A5 ----------------
    src16 = make_pdf("s16.pdf", 16)
    out = os.path.join(TMP, "b5.pdf")
    st = pdfops.impose_booklet(src16, out, max_sheets=5)
    with fitz.open(out) as d:
        w, h = d[0].rect.width, d[0].rect.height
        n = len(d)
    check("小册子A5 面数=8", n == 8, f"got {n}")
    check("小册子A5 是 A4 横向", abs(w - 841.89) < 1 and abs(h - 595.28) < 1, f"{w:.1f}x{h:.1f}")
    check("小册子A5 第1张正面 = 16|1", set(nums(out, 0)) == {16, 1}, str(nums(out, 0)))
    check("小册子A5 第1张背面 = 2|15", set(nums(out, 1)) == {2, 15}, str(nums(out, 1)))

    # ---------------- 小册子 A6 ----------------
    out6 = os.path.join(TMP, "b6.pdf")
    st6 = pdfops.impose_booklet(src16, out6, max_sheets=5, book_size="A6")
    with fitz.open(out6) as d:
        n6 = len(d)
    check("A6 面数=4（张数减半）", n6 == 4, f"got {n6}")
    check("A6 正面 = 16,1,14,3", set(nums(out6, 0)) == {16, 1, 14, 3}, str(nums(out6, 0)))
    check("A6 背面 = 2,15,4,13", set(nums(out6, 1)) == {2, 15, 4, 13}, str(nums(out6, 1)))

    # ---------------- 补空白 ----------------
    src14 = make_pdf("s14.pdf", 14)
    out14 = os.path.join(TMP, "b14.pdf")
    st14 = pdfops.impose_booklet(src14, out14, max_sheets=5)
    check("14 页补到 16 面（2 格空白）", st14["blanks"] == 2, str(st14))
    check("14 页最外张只有 1/2（另半是空白）",
          set(nums(out14, 0)) == {1} and set(nums(out14, 1)) == {2},
          f"{nums(out14, 0)} / {nums(out14, 1)}")

    # ---------------- 四堆叠 ----------------
    outfs = os.path.join(TMP, "fs.pdf")
    pdfops.impose_fourstack(src16, outfs)
    check("四堆叠 第1面 = 1,5,9,13", set(nums(outfs, 0)) == {1, 5, 9, 13}, str(nums(outfs, 0)))
    check("四堆叠 第2面 = 2,6,10,14", set(nums(outfs, 1)) == {2, 6, 10, 14}, str(nums(outfs, 1)))

    # ---------------- 4合1 ----------------
    out4 = os.path.join(TMP, "4up.pdf")
    pdfops.impose_fourup(src16, out4, layout="A", start_page=3)
    check("4合1 模式A 起始3 = 3,4,5,6", set(nums(out4, 0)) == {3, 4, 5, 6}, str(nums(out4, 0)))
    out4c = os.path.join(TMP, "4upc.pdf")
    pdfops.impose_fourup(src16, out4c, layout="C")
    check("4合1 模式C = 3,1,4,2", set(nums(out4c, 0)) == {1, 2, 3, 4}, str(nums(out4c, 0)))

    # ---------------- 分拆 ----------------
    src206 = make_pdf("s206.pdf", 206)
    from ui import __name__ as _  # noqa: F401  仅确认包可导入
    parts = [(0, 68), (69, 137), (138, 205)]
    counts = []
    for k, (a, b) in enumerate(parts):
        p = os.path.join(TMP, f"part{k}.pdf")
        d = fitz.open(src206)
        o = fitz.open()
        o.insert_pdf(d, from_page=a, to_page=b)
        o.save(p)
        counts.append(len(o))
        o.close(); d.close()
    check("分拆 3 份 = 69/69/68", counts == [69, 69, 68], str(counts))

    # ---------------- 合并 ----------------
    merged = os.path.join(TMP, "merged.pdf")
    stm = pdfops.merge_pdfs([src16, src206], merged)
    check("合并页数 = 222", stm["pages"] == 222, str(stm))
    check("合并第 17 页是第二个文件第 1 页", 1 in nums(merged, 16), str(nums(merged, 16)))

    # ---------------- 加页码 ----------------
    outn = os.path.join(TMP, "num.pdf")
    stn = pdfops.add_page_numbers(src16, outn, start=1, fmt="{n}", pos="bottom-center",
                                  font_size=10, margin_mm=12, skip=1)
    check("加页码 跳过封面：首页无页码", nums(outn, 0) == [1] or nums(outn, 0) == [])
    check("加页码 第2页显示 1", 1 in nums(outn, 1), str(nums(outn, 1)))
    check("加页码 最后一页显示 15", 15 in nums(outn, 15), str(nums(outn, 15)))

    # ---------------- 封面 ----------------
    img = cover_core.render_cover(148, 210, 12, 3, dpi=120, title="认出 Java",
                                  subtitle="从一行代码开始", author="LOU0122 著", spine_pt=16)
    mm_w, mm_h = img.width / 120 * 25.4, img.height / 120 * 25.4
    check("封面展开尺寸 ≈ 314×216mm", abs(mm_w - 314) < 1.5 and abs(mm_h - 216) < 1.5,
          f"{mm_w:.1f}x{mm_h:.1f}")
    corners = [img.getpixel((1, 1)), img.getpixel((img.width - 2, 1)),
               img.getpixel((1, img.height - 2)), img.getpixel((img.width - 2, img.height - 2))]
    check("封面四角不是白（出血有内容）", all(c != (255, 255, 255) for c in corners), str(corners))

    cov_pdf = os.path.join(TMP, "cover.pdf")
    cover_core.save_pdf(img, cov_pdf, dpi=120)
    with fitz.open(cov_pdf) as d:
        pw, ph = d[0].rect.width / 72 * 25.4, d[0].rect.height / 72 * 25.4
    check("封面 PDF 页面尺寸正确", abs(pw - 314) < 1.5 and abs(ph - 216) < 1.5, f"{pw:.1f}x{ph:.1f}")

    # ---------------- 异常/特殊稿件 ----------------
    mixed = os.path.join(TMP, "mixed.pdf")
    d = fitz.open()
    for i in range(8):
        sz = (595, 842) if i % 2 == 0 else (420, 595)
        pg = d.new_page(width=sz[0], height=sz[1])
        pg.insert_text((40, 80), str(i + 1), fontsize=40)
    d.save(mixed); d.close()
    om = os.path.join(TMP, "o_mixed.pdf")
    stm = pdfops.impose_booklet(mixed, om)
    check("A4/A5 混排能拼", stm["sheets"] == 2 and abs(fitz.open(om)[0].rect.width - 842) < 2,
          f"{stm['sheets']} 张")

    scan = os.path.join(TMP, "scan.pdf")
    d = fitz.open()
    for i in range(8):
        pg = d.new_page(width=595, height=842)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 80)); pix.clear_with(200)
        pg.insert_image(pg.rect, pixmap=pix)
    d.save(scan); d.close()
    os_ = os.path.join(TMP, "o_scan.pdf")
    sts = pdfops.impose_booklet(scan, os_)
    check("扫描件（无文字层）能拼", sts["sheets"] == 2, f"{sts['sheets']} 张")

    enc = os.path.join(TMP, "enc.pdf")
    d = fitz.open(); d.new_page(); d.save(enc, encryption=fitz.PDF_ENCRYPT_AES_256,
                                          owner_pw="o", user_pw="u"); d.close()
    try:
        pdfops.impose_booklet(enc, os.path.join(TMP, "o_enc.pdf"))
        check("加密 PDF 给出明确提示", False, "没有报错")
    except Exception as e:  # noqa: BLE001
        msg = pdfops.friendly_error(e, enc)
        check("加密 PDF 给出明确提示", "密码" in msg, msg)

    # ---------------- 不覆盖同名文件 ----------------
    dup = os.path.join(TMP, "dup.pdf")
    open(dup, "wb").write(b"x")
    alt = pdfops.unique_path(dup)
    check("同名输出自动改名", alt != dup and alt.endswith("-2.pdf"), alt)
    open(alt, "wb").write(b"x")
    check("再加一个变 -3", pdfops.unique_path(dup).endswith("-3.pdf"), pdfops.unique_path(dup))

    # ---------------- 大稿加页码不许慢 ----------------
    import time as _t
    big = os.path.join(TMP, "big300.pdf")
    with fitz.open() as d:
        for i in range(300):
            d.new_page(width=595, height=842).insert_text((60, 100), f"P{i}", fontsize=20)
        d.save(big)
    t0 = _t.time()
    pdfops.add_page_numbers(big, os.path.join(TMP, "big300_num.pdf"))
    dt = _t.time() - t0
    check(f"300 页加页码 {dt:.2f}s（<6s）", dt < 6.0)

    # ---------------- 辅助线不许进成品 ----------------
    from PIL import ImageChops

    def _cov(marks, sheet):
        return cover_core.render_cover(148, 210, 10.4, 3, dpi=72, title="测试书名",
                                       author="作者", template="classic",
                                       crop_marks=marks, sheet=sheet)

    for sheet in ("cover", "a4"):
        da = ImageChops.difference(_cov(True, sheet), _cov(False, sheet)).convert("L")
        W, H = da.size
        mm = 72 / 25.4
        if sheet == "a4":
            sc = min(1.0, (297 - 10) / (148 * 2 + 10.4 + 6), (210 - 10) / (210 + 6))
            w = int((148 * 2 + 10.4 + 6) * mm * sc)
            h = int((210 + 6) * mm * sc)
            px, py = (W - w) // 2, (H - h) // 2
            b = int(3 * mm * sc)
            box = (px + b, py + b, px + w - b, py + h - b)
        else:
            b = int(3 * mm)
            box = (b, b, W - b, H - b)
        inner = da.crop(box)
        bad = sum(1 for v in inner.getdata() if v > 8)
        check(f"辅助线不进成品（{sheet}）", bad == 0, f"{bad} 个像素")

    # ---------------- 封面模板 ----------------
    check("书脊按页数算（204 页 80g）",
          abs(cover_core.spine_from_pages(204, "80g 胶版") - 10.6) < 0.15,
          str(cover_core.spine_from_pages(204, "80g 胶版")))
    for tpl in cover_core.TEMPLATES:
        img = cover_core.render_cover(148, 210, 10.6, dpi=72, title="测试书名",
                                      subtitle="副标题", author="作者",
                                      template=tpl, palette="米白·朱红",
                                      back_text="封底文字", barcode=True)
        w_mm = (148 * 2 + 10.6 + 6) * 72 / 25.4
        check(f"封面模板 {tpl} 能渲染", abs(img.width - w_mm) < 4 and img.height > 500,
              f"{img.size}")

    # ---------------- 页边距：填多少，纸上离边多少（不能再靠"看着还行"） ----------------
    MMv = 72 / 25.4

    def _solid(name, wmm, hmm, pages=8):
        path = os.path.join(TMP, name)
        doc = fitz.open()
        for _ in range(pages):
            pg = doc.new_page(width=wmm * MMv, height=hmm * MMv)
            pg.draw_rect(pg.rect, color=None, fill=(0.2, 0.35, 0.6))
        doc.save(path)
        doc.close()
        return path

    a5 = _solid("margin_a5.pdf", 148, 210)
    a6 = _solid("margin_a6.pdf", 105, 148)
    def _ink_mm(pdf, page_no=0, dpi=72):
        doc = fitz.open(pdf)
        pix = doc[page_no].get_pixmap(dpi=dpi)
        doc.close()
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        w, h = img.size
        px = img.load()
        xs, ys = [], []
        for y in range(h):
            for x in range(w):
                r, g, b = px[x, y]
                if not (r > 240 and g > 240 and b > 240):
                    xs.append(x)
                    ys.append(y)
        k = dpi / 25.4
        return min(xs) / k, min(ys) / k, max(xs) / k, max(ys) / k

    # 4合1：填 0 不许有隐藏白边（旧版写死 3pt），填 10 左右必须真的 10
    st = pdfops.impose_fourup(a6, os.path.join(TMP, "reg_4up0.pdf"), "A", 0, 1)
    x0, y0, x1, y1 = _ink_mm(os.path.join(TMP, "reg_4up0.pdf"))
    check("4合1 边距 0 时贴边（误差<1mm）", max(x0, y0, 210 - x1, 297 - y1) < 1.0,
          f"{x0:.1f}/{y0:.1f}/{210 - x1:.1f}/{297 - y1:.1f}")
    st = pdfops.impose_fourup(a6, os.path.join(TMP, "reg_4up10.pdf"), "A", 10, 1)
    x0, y0, x1, y1 = _ink_mm(os.path.join(TMP, "reg_4up10.pdf"))
    m = st["margins_mm"]
    check("4合1 边距 10mm：左右真的 10（±0.6）", abs(x0 - 10) < 0.6 and abs((210 - x1) - 10) < 0.6,
          f"左{x0:.1f} 右{210 - x1:.1f}")
    check("4合1 报的实际边距和纸上一致（±0.6）",
          abs(m["left"] - x0) < 0.6 and abs(m["top"] - y0) < 0.6,
          f"报{m['top']:.1f}/{m['left']:.1f} 实{y0:.1f}/{x0:.1f}")

    # ---------------- 结果 ----------------
    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 项失败：" + "、".join(FAILS))
        return 1
    print("✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
