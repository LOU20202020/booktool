"""拍「打印记账」的样子：书架详情里的打印次数/张数、生产线第⑥步变成完成。

不碰真打印机：把 core.printpdf.print_pdf 换成假的，只让记账那条线跑起来。
出图：%TEMP%\\shots\\new-print-shelf.png / new-print-pipeline.png
"""
from pathlib import Path
import os
import sys
import tempfile
import time

os.environ.pop("QT_QPA_PLATFORM", None)   # 用真平台插件，offscreen 解析不到中文字体
TMP = os.environ.get("TEMP", tempfile.gettempdir())
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
    for i in range(pages):
        page = doc.new_page(width=w, height=h)
        page.draw_rect(pymupdf.Rect(18, 18, w - 18, h - 18), color=(0.1, 0.1, 0.1), width=0.7)
        page.insert_text((30, 60), f"第 {i + 1} 面", fontsize=24, fontname="china-s")
        page.insert_text((30, 88), f"{name} · 演示正文", fontsize=11, fontname="china-s")
    doc.set_toc([[1, "第一话", 1]])
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


def spin(cond, timeout=40.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        APP.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def shot(w, name, pause=0.6):
    for _ in range(4):
        APP.processEvents()
        time.sleep(pause / 4)
    path = os.path.join(OUT, f"new-{name}.png")
    w.grab().save(path)
    print("shot", name, "->", path)


bookdir = os.path.join(TMP, "btshot-print", "单行本")
src = make_book(bookdir)

w = MainWindow()
w.resize(1440, 900)
w.show()
w.move(-3200, -3200)
APP.processEvents()

w.shelf_page.add_folder(bookdir)
APP.processEvents()
proj = w.shelf_page.shelf.projects[0]

# 分割 → 造排版产物 → 生产线认领
w.split_tool_page.set_source(src)
w.split_tool_page.sp_front.set_value(2)
w.split_tool_page.sp_tail.set_value(2)
w.split_tool_page.run()
spin(lambda: bool(w.split_tool_page.out))
body = w.split_tool_page.out.get("body", "")
layout = os.path.join(bookdir, "忍者物语 第01卷-小册子.pdf")
if body:
    import shutil
    shutil.copyfile(body, layout)
w.pipeline_page.set_project(proj.id)
w.pipeline_page.on_show()
APP.processEvents()

# 假送印：双面、2 份 → 应该记 36 张纸
from core import printpdf as pp
pp.print_pdf = lambda *a, **k: "HP LaserJet Tank MFP 2606dw"
pp.supports_duplex = lambda *a, **k: True
before = len(w.shelf_page.store.load().by_id(proj.id).prints)
w.start_print(layout, dict(printer="", copies=2, duplex="short", paper="A4",
                           first_page_only=False, pages="", flip="short"))
spin(lambda: len(w.shelf_page.store.load().by_id(proj.id).prints) > before, timeout=20)

# 书架
w.shelf_page.refresh()
w.goto(w.page_index["shelf"])
w.shelf_page._show_detail(w.shelf_page.shelf.by_id(proj.id))
shot(w, "print-shelf")

# 生产线
w.pipeline_page.set_project(proj.id)
w.goto(w.page_index["pipeline"])
w.pipeline_page.on_show()
w.pipeline_page.goto_step(6)
shot(w, "print-pipeline")

p = w.shelf_page.store.load().by_id(proj.id)
print("\n步骤状态:", {i: p.step_state(i) for i in range(1, 8)})
print("打印记录:", [(e.tag, e.sheets, e.job, e.sample) for e in p.prints])
print("书架状态:", p.status)
