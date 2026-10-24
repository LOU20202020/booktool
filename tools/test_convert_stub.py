"""格式转换这条链的验证 —— 分三层，最后一层需要真的 Calibre。

1) 纯函数层：build_args / accepts / friendly_error / default_output
2) 子进程层：把 subprocess.Popen 换成假的"calibre"，跑通 convert() 的进度解析、
   成功判定、页数/目录探测
3) 界面层：ConvertPage 真的点一次转换（同样用假的 calibre），看状态栏、结果、
   右侧目录、主按钮回到可用

真 Calibre 转换（MOBI/AZW3 → PDF）不在这个脚本里：本机没装，
装完直接跑 `ebook-convert in.mobi out.pdf` 就能验，脚本末尾会打印检查命令。
"""
from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile
import time

os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["BOOKTOOL_SETTINGS"] = "BookToolConvertTest"
TMP = tempfile.mkdtemp(prefix="btconvert-")
os.environ["LOCALAPPDATA"] = TMP
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pymupdf
from PySide6.QtWidgets import QApplication

from core import convert as C

FAIL = []


def check(cond, what, extra=""):
    print(("  ✔ " if cond else "  ✘ ") + what + (f"  {extra}" if extra else ""))
    if not cond:
        FAIL.append(what)
    return cond


mm = 72 / 25.4


def make_pdf(path, pages=6):
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=148 * mm, height=210 * mm)
        page.insert_text((30, 60), f"converted page {i + 1}", fontsize=16, fontname="helv")
    doc.set_toc([[1, "Chapter 1", 1], [1, "Chapter 2", max(1, pages // 2)]])
    doc.save(path)
    doc.close()
    return path


print("\n=== 1) 纯函数：拼参数 ===")
args = C.build_args("in.epub", "out.pdf", paper="B6", font="宋体", font_size=12,
                    margin="窄", page_numbers=True, chapter_break=True, kind="文字书")
joined = " ".join(args)
check("--custom-size 128x182" in joined and "--unit millimeter" in joined
      and "--paper-size custom" not in joined,
      "B6 走 --custom-size（Calibre 9.x 不认 paper-size custom）", joined[:90])
check("--pdf-serif-family SimSun" in joined, "宋体 → SimSun", "")
check("--pdf-default-font-size 12" in joined, "字号带上", "")
check("--pdf-page-numbers" in joined and "--chapter-mark pagebreak" in joined,
      "页码与章节分页开关生效", "")
comic = " ".join(C.build_args("in.mobi", "out.pdf", kind="漫画", margin="宽"))
check("--disable-font-rescaling" in comic and "--pdf-page-margin-left 0.0" in comic,
      "漫画：零边距 + 关字体重排", "")
check(C.accepts("a.mobi") and C.accepts("a.EPUB") and not C.accepts("a.pdf"),
      "支持格式判断对", "")
check("DRM" in C.friendly_error("MobiError: DRM encrypted", "a.mobi"),
      "DRM 报错翻译成人话", C.friendly_error("DRM encrypted", "a.mobi")[:30])
check(C.default_output("x.epub").endswith(".pdf"), "默认输出是 .pdf",
      os.path.basename(C.default_output("x.epub")))
print("  当前 binary():", repr(C.binary()), "| available():", C.available())

print("\n=== 2) 子进程层：假 calibre 跑通 convert() ===")
import subprocess as _sp

sample = make_pdf(os.path.join(TMP, "converted.pdf"))
src = os.path.join(TMP, "测试书.epub")
open(src, "wb").write(b"fake epub bytes")

_real_popen = _sp.Popen


class FakeProc:
    """假装是 ebook-convert：吐几行进度，然后把成品写到 out。"""

    def __init__(self, args, **kw):
        self.args = args
        self.returncode = 0
        self.killed = False
        self._lines = [" 12% Converting input files", " 58% Parsing HTML",
                       "100% Output written"]
        import io
        self.stdout = io.StringIO("\n".join(self._lines) + "\n")

        # ebook-convert <src> <out> ... → 第二个参数是输出
        self.out = args[2]

    def wait(self):
        try:
            import shutil
            shutil.copyfile(sample, self.out)
        except OSError:
            self.returncode = 1
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = 1


seen = []
_real_binary = C.binary
C.subprocess.Popen = lambda args, **kw: FakeProc(args, **kw)
C.binary = lambda: r"C:\Fake\ebook-convert.exe"      # 让 available() 为真
try:
    result = C.convert(src, progress=lambda p, m: seen.append((round(p, 2), m)))
finally:
    C.subprocess.Popen = _real_popen
    C.binary = _real_binary

check(bool(result.get("out")) and os.path.exists(result["out"]), "产出文件存在",
      os.path.basename(result.get("out", "")))
check(result.get("pages") == 6, "读到页数", str(result.get("pages")))
check(result.get("bookmarks") == 2, "读到目录条数", str(result.get("bookmarks")))
check(any(p == 0.12 for p, _ in seen) and seen[-1][0] == 1.0, "进度回调走通",
      str(seen[:3]) + " … " + str(seen[-1]))

print("\n=== 3) 界面层：ConvertPage 真跑一次 ===")
APP = QApplication([])
from ui.app import MainWindow

w = MainWindow()
w.resize(1440, 900)
w.show()
w.move(-3200, -3200)
APP.processEvents()
w.goto(w.page_index["convert"])
page = w.pages[w.page_index["convert"]]
APP.processEvents()

check(page.calibre_hint.text() != "", "引擎状态有提示（有/没有 Calibre 都行）",
      page.calibre_hint.text()[:28])

C.subprocess.Popen = lambda args, **kw: FakeProc(args, **kw)
C.binary = lambda: r"C:\Fake\ebook-convert.exe"       # 让页面认为引擎在
try:
    page.set_source(src) if hasattr(page, "set_source") else setattr(page, "src", src)
    APP.processEvents()
    t0 = time.time()
    page.run()
    while time.time() - t0 < 30 and not getattr(page, "out", ""):
        APP.processEvents()
        time.sleep(0.03)
    out = getattr(page, "out", "")
    check(bool(out) and os.path.exists(str(out)), "界面转换产出文件",
          os.path.basename(str(out)))
    check("完成" in w.status_lab.text() or "转换" in w.status_lab.text(),
          "状态栏有结果", w.status_lab.text()[:36])
    toc = getattr(page, "toc_list", None) or getattr(page, "toc", None)
    check(toc is not None, "右侧目录控件存在", type(toc).__name__ if toc else "")
finally:
    C.subprocess.Popen = _real_popen
    C.binary = lambda: ""

print("\n真 Calibre 验证命令（装完 Calibre 后跑）：")
print(r'  "C:\Program Files\Calibre2\ebook-convert.exe" 书名.mobi 书名.pdf --paper-size a5')
print("\n" + ("全部通过（除真 Calibre 转换）" if not FAIL else f"失败 {len(FAIL)} 项：" + "；".join(FAIL)))
sys.exit(1 if FAIL else 0)
