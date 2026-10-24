"""给合并后的新版界面拍几张图（离屏，不打扰正在用的程序）。

出图在 %TEMP%\\shots\\new-*.png：
  new-home      首页（12 张工具卡）
  new-shelf     书架（导入一本之后）
  new-pipeline  生产线（七节点）
  new-cover     封面页（右栏 + 收起把手 + 图槽已填）
  new-convert   格式转换（没装 Calibre 时的提示）
  new-rail-off  封面页右栏收起后
"""
from pathlib import Path
import os
import sys
import tempfile
import time

# 用真的 windows 平台插件（离屏跑），offscreen 插件在这台机上解析不到中文字体 → 会出方块
os.environ.pop("QT_QPA_PLATFORM", None)

TMP = os.environ.get("TEMP", tempfile.gettempdir())
# 注意：不要改 LOCALAPPDATA——改了 Qt 找不到字体缓存，中文会渲染成方块
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf
from PySide6.QtWidgets import QApplication

from ui.app import MainWindow

OUT = os.path.join(TMP, "shots")
os.makedirs(OUT, exist_ok=True)

APP = QApplication([])
MM = 72 / 25.4


def make_book(folder, name="忍者物语 第01卷", pages=40):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".pdf")
    doc = pymupdf.open()
    w, h = 148 * MM, 210 * MM
    accent = (0.70, 0.23, 0.18)
    for i in range(pages):
        page = doc.new_page(width=w, height=h)
        page.draw_rect(pymupdf.Rect(18, 18, w - 18, h - 18), color=(0.1, 0.1, 0.1), width=0.7)
        page.draw_rect(pymupdf.Rect(26, 26, w - 26, 96), color=accent, width=1.2)
        page.insert_text((32, 118), f"第 {i + 1} 面", fontsize=26, fontname="china-s")
        page.insert_text((32, 142), f"{name} · 第 {i + 1} 页正文占位", fontsize=10.5,
                         fontname="china-s")
        page.insert_text((w - 58, h - 26), str(i + 1), fontsize=13, fontname="china-s")
    doc.set_toc([[1, "第一话", 1], [1, "第二话", 20]])
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


def spin(cond, timeout=30.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        APP.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def shot(w, name):
    APP.processEvents()
    for _ in range(3):
        APP.processEvents()
        time.sleep(0.12)
    path = os.path.join(OUT, f"new-{name}.png")
    w.grab().save(path)
    print("shot", name, "->", path)


bookdir = os.path.join(TMP, "btshot-book", "单行本")
src = make_book(bookdir)

w = MainWindow()
w.resize(1440, 900)
w.show()
w.move(-3200, -3200)          # 挪到屏幕外，别打扰正在用的程序
APP.processEvents()

# 1) 首页
w.show_home()
shot(w, "home")

# 2) 书架
shelf = w.shelf_page
w.goto(w.page_index["shelf"])
shelf.add_folder(bookdir)
APP.processEvents()
shelf.refresh_list()
shot(w, "shelf")

# 3) 生产线
p = shelf.shelf.projects[0]
w.goto(w.page_index["pipeline"])
w.pipeline_page.set_project(p.id)
APP.processEvents()
shot(w, "pipeline")

# 4) 封面（先填图，再看右栏）
from ui import cover_link
res = None


def run_split():
    global res
    w.goto(w.page_index["cut"])
    cut = w.split_tool_page
    cut.set_source(src)
    cut.sp_front.set_value(2)
    cut.sp_tail.set_value(2)
    cut.run()
    spin(lambda: bool(cut.out), timeout=60)
    return cut.out


res = run_split()
if res:
    cover_link.fill_cover(w, cover=res.get("cover", ""), back=res.get("back", ""))
w.goto(w.page_index["cover"])
APP.processEvents()
shot(w, "cover")

# 5) 右栏收起
cover = w.pages[w.page_index["cover"]]
rail = getattr(cover, "_right_rail", None)
if rail is not None:
    rail.set_collapsed(True)
    shot(w, "rail-off")

# 6) 格式转换
w.goto(w.page_index["convert"])
APP.processEvents()
shot(w, "convert")

print("\n出图目录:", OUT)
