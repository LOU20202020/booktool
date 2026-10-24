"""真实书稿回归：用 ~/java-course/book/out 里的四册书跑拼版，跟 10 月 11 日已验证的输出对拍。

没有真实书稿时自动跳过（返回 0）。
"""
from __future__ import annotations

import glob
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf as fitz
from core import pdfops

BOOK = os.path.expanduser("~/java-course/book/out")
OLD = os.path.join(BOOK, "小册子-20面分帖")
TMP = tempfile.mkdtemp(prefix="booktool_real_")
FAILS: list[str] = []

VOLS = [
    ("第①册-认 Java(上).pdf", "第①册-认Java(上)-20面分帖-A4双面.pdf", 102),
    ("第②册-认 Java(下).pdf", "第②册-认Java(下)-20面分帖-A4双面.pdf", 130),
    ("第③册-模组(上).pdf", "第③册-模组(上)-20面分帖-A4双面.pdf", 130),
    ("第④册-模组(下).pdf", "第④册-模组(下)-20面分帖-A4双面.pdf", 136),
]


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"   [{detail}]"))
    if not cond:
        FAILS.append(name)


def diff_pages(a_path, b_path, page, dpi=72):
    """两页渲染后的平均像素差（0-255）。"""
    def render(p):
        with fitz.open(p) as d:
            pix = d[page].get_pixmap(dpi=dpi)
            return pix
    pa, pb = render(a_path), render(b_path)
    if (pa.width, pa.height) != (pb.width, pb.height):
        return 999.0
    sa, sb = pa.samples, pb.samples
    n = min(len(sa), len(sb))
    step = max(1, n // 200000)
    total = cnt = 0
    for i in range(0, n, step):
        total += abs(sa[i] - sb[i])
        cnt += 1
    return total / max(1, cnt)


def main() -> int:
    if not os.path.isdir(OLD):
        print("没有真实书稿，跳过")
        return 0

    for src_name, old_name, expect_sides in VOLS:
        src = os.path.join(BOOK, src_name)
        old = os.path.join(OLD, old_name)
        if not (os.path.exists(src) and os.path.exists(old)):
            print(f"SKIP  {src_name}（文件不在）")
            continue
        out = os.path.join(TMP, "out-" + old_name)
        st = pdfops.impose_booklet(src, out, max_sheets=5, binding="left")
        with fitz.open(out) as d:
            n = len(d)
            w, h = d[0].rect.width, d[0].rect.height
        check(f"{src_name} 面数={expect_sides}", n == expect_sides, f"got {n}")
        check(f"{src_name} A4 横向", abs(w - 841.89) < 1 and abs(h - 595.28) < 1, f"{w:.0f}x{h:.0f}")
        d0 = diff_pages(out, old, 0)
        d1 = diff_pages(out, old, 1)
        check(f"{src_name} 首页与已验收文件一致（差 {d0:.1f}/{d1:.1f}）", d0 < 6 and d1 < 6,
              f"{d0:.1f} {d1:.1f}")

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 项失败：" + "、".join(FAILS))
        return 1
    print("✅ 真实书稿全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
