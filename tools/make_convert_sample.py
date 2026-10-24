"""准备两份真实电子书给打包版自检用：中文 epub + 由它转出的 mobi。"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import convert as C

OUT = os.path.join(tempfile.gettempdir(), "convtest")
os.makedirs(OUT, exist_ok=True)
epub = os.path.join(OUT, "中文测试书.epub")
mobi = os.path.join(OUT, "中文测试书.mobi")

paras = "".join(
    f"<p>第 {i + 1} 段：把电子书转成能打印的 PDF。这里用来验中文、标点，。；：！？"
    f"和数字 0123456789 在转换后是否正常。</p>" for i in range(80))
with zipfile.ZipFile(epub, "w") as z:
    z.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
    z.writestr("META-INF/container.xml",
               '<?xml version="1.0"?><container version="1.0" '
               'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
               '<rootfile full-path="OEBPS/content.opf" '
               'media-type="application/oebps-package+xml"/></rootfiles></container>')
    z.writestr("OEBPS/content.opf",
               '<?xml version="1.0" encoding="utf-8"?><package '
               'xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">'
               '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
               '<dc:title>中文测试书</dc:title><dc:creator>LOU0122</dc:creator>'
               '<dc:language>zh-CN</dc:language><dc:identifier id="id">t1</dc:identifier>'
               '</metadata><manifest>'
               '<item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>'
               '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
               '</manifest><spine toc="ncx"><itemref idref="c1"/></spine></package>')
    z.writestr("OEBPS/toc.ncx",
               '<?xml version="1.0" encoding="utf-8"?>'
               '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
               '<head><meta name="dtb:uid" content="t1"/></head>'
               '<docTitle><text>中文测试书</text></docTitle><navMap>'
               '<navPoint id="n1" playOrder="1"><navLabel><text>第一章</text></navLabel>'
               '<content src="c1.xhtml"/></navPoint></navMap></ncx>')
    z.writestr("OEBPS/c1.xhtml",
               '<?xml version="1.0" encoding="utf-8"?><html '
               'xmlns="http://www.w3.org/1999/xhtml"><head><title>第一章</title>'
               '<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>'
               f'</head><body><h1>第一章　中文排版</h1>{paras}</body></html>')

print("epub:", epub, os.path.getsize(epub), "字节")

exe = C.binary()
if not exe:
    print("没有 Calibre，只能给 epub 用（程序内部还是需要 Calibre）")
    sys.exit(0)
proc = subprocess.run([exe, epub, mobi], capture_output=True, text=True,
                      encoding="utf-8", errors="replace")
print("mobi:", mobi, os.path.getsize(mobi) if os.path.exists(mobi) else proc.stderr[-200:])
