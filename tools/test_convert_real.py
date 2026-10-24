"""真 Calibre 转换验证：EPUB → PDF、EPUB → MOBI → PDF，全走程序自己的 core.convert。

用法：
    python tools/test_convert_real.py [epub路径]

没有 Calibre 时退出码 2（不报失败）。
"""
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import convert as C

TMP = tempfile.mkdtemp(prefix="btconvreal-")
FAIL = []


def check(cond, what, extra=""):
    print(("  ✔ " if cond else "  ✘ ") + what + (f"  {extra}" if extra else ""))
    if not cond:
        FAIL.append(what)
    return cond


exe = C.binary()
print("ebook-convert:", exe or "（没找到）")
if not exe:
    print("没装 Calibre：先安装，再跑这个脚本")
    sys.exit(2)
print("available():", C.available())

epub = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    tempfile.gettempdir(), "gutenberg.epub")
if not os.path.exists(epub):
    print("找不到测试用 epub：", epub)
    sys.exit(2)

print("\n=== 1) EPUB → PDF（文字书，A5，宋体 11pt）===")
out = C.convert(epub, os.path.join(TMP, "epub2pdf.pdf"), paper="A5", font="宋体",
                font_size=11, margin="中", page_numbers=True, chapter_break=True,
                kind="文字书",
                progress=lambda p, m: None)
check(out["pages"] > 20, "页数合理", f"{out['pages']} 页")
check(out["bookmarks"] > 0, "目录带出来了", f"{out['bookmarks']} 条")
check(out["size"] > 20_000, "文件不是空壳", out["size_text"])
check(os.path.exists(out["out"]), "文件落地", os.path.basename(out["out"]))

print("\n=== 2) EPUB → MOBI（用 calibre 自己造一个 mobi）===")
mobi = os.path.join(TMP, "book.mobi")
proc = subprocess.run([exe, epub, mobi], capture_output=True, text=True,
                      encoding="utf-8", errors="replace")
check(proc.returncode == 0 and os.path.exists(mobi), "mobi 造出来了",
      f"{os.path.getsize(mobi) / 1024:.0f} KB" if os.path.exists(mobi) else proc.stderr[-120:])

print("\n=== 3) MOBI → PDF（走程序自己的路径）===")
if os.path.exists(mobi):
    out2 = C.convert(mobi, os.path.join(TMP, "mobi2pdf.pdf"), paper="A5",
                     font="黑体", font_size=10.5, kind="文字书")
    check(out2["pages"] > 20, "mobi 也能转", f"{out2['pages']} 页")
    check(out2["bookmarks"] > 0, "mobi 目录也在", f"{out2['bookmarks']} 条")

print("\n=== 4) 漫画模式（零边距、关字体重排）===")
out3 = C.convert(epub, os.path.join(TMP, "comic.pdf"), kind="漫画", paper="B6")
check(out3["pages"] > 10, "漫画模式能出活", f"{out3['pages']} 页")

print("\n=== 5) 首页渲染出来看一眼 ===")
import pymupdf
png = os.path.join(tempfile.gettempdir(), "shots", "convert-first-page.png")
os.makedirs(os.path.dirname(png), exist_ok=True)
with pymupdf.open(out["out"]) as doc:
    doc[0].get_pixmap(dpi=110).save(png)
print("  出图:", png)

print("\n=== 6) 自造一本中文 EPUB，验中文字体 ===")
import zipfile

cn_epub = os.path.join(TMP, "chinese.epub")
paras = "".join(
    f"<p>第 {i + 1} 段：把 PDF 排成能折、能订、能裁的书。这一行用来验中文字体和换行，"
    f"包括标点，。；：！？——和阿拉伯数字 0123456789。</p>" for i in range(40))
with zipfile.ZipFile(cn_epub, "w") as z:
    z.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
    z.writestr("META-INF/container.xml",
               '<?xml version="1.0"?><container version="1.0" '
               'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
               '<rootfiles><rootfile full-path="OEBPS/content.opf" '
               'media-type="application/oebps-package+xml"/></rootfiles></container>')
    z.writestr("OEBPS/content.opf",
               '<?xml version="1.0" encoding="utf-8"?>'
               '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" '
               'unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
               '<dc:title>中文测试书</dc:title><dc:creator>LOU0122</dc:creator>'
               '<dc:language>zh-CN</dc:language><dc:identifier id="id">test-1</dc:identifier>'
               '</metadata><manifest>'
               '<item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>'
               '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
               '</manifest><spine toc="ncx"><itemref idref="c1"/></spine></package>')
    z.writestr("OEBPS/toc.ncx",
               '<?xml version="1.0" encoding="utf-8"?>'
               '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
               '<head><meta name="dtb:uid" content="test-1"/></head>'
               '<docTitle><text>中文测试书</text></docTitle>'
               '<navMap><navPoint id="n1" playOrder="1"><navLabel><text>第一章</text></navLabel>'
               '<content src="c1.xhtml"/></navPoint></navMap></ncx>')
    z.writestr("OEBPS/c1.xhtml",
               '<?xml version="1.0" encoding="utf-8"?>'
               '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>第一章</title>'
               '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/></head>'
               f'<body><h1>第一章　中文排版</h1>{paras}</body></html>')

out_cn = C.convert(cn_epub, os.path.join(TMP, "chinese.pdf"), paper="A5",
                   font="宋体", font_size=11, kind="文字书")
check(out_cn["pages"] >= 2, "中文 epub 转出来了", f"{out_cn['pages']} 页")
cn_png = os.path.join(os.path.dirname(png), "convert-chinese.png")
with pymupdf.open(out_cn["out"]) as doc:
    doc[0].get_pixmap(dpi=130).save(cn_png)
print("  中文首页出图:", cn_png)

print("\n" + ("真实转换全部通过" if not FAIL else f"失败 {len(FAIL)} 项：" + "；".join(FAIL)))
sys.exit(1 if FAIL else 0)
