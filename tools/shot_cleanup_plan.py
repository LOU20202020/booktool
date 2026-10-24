"""拍「清理中间产物」对话框和「打印计划」节点。

出图：%TEMP%\\shots\\cleanup-dialog.png / plan-node.png
"""
from pathlib import Path
import os
import sys
import tempfile
import time

os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["BOOKTOOL_SETTINGS"] = "BookToolCleanShot"
TMP = os.environ.get("TEMP", tempfile.gettempdir())
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf
from PySide6.QtWidgets import QApplication

from ui.app import MainWindow
from ui.shelf_page import _CleanupDialog

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


bookdir = os.path.join(TMP, "btshot-clean", "单行本")
src = make_book(bookdir)

w = MainWindow()
w.resize(1440, 900)
w.show()
w.move(-3200, -3200)
APP.processEvents()

w.shelf_page.add_folder(bookdir)
APP.processEvents()
proj = w.shelf_page.shelf.projects[0]

# 分割 + 造两份排版产物（一份当"当前成品"，一份当"旧的 -2"） → 清理清单才有内容
w.split_tool_page.set_source(src)
w.split_tool_page.sp_front.set_value(2)
w.split_tool_page.sp_tail.set_value(2)
w.split_tool_page.run()
spin(lambda: bool(w.split_tool_page.out))
body = w.split_tool_page.out.get("body", "")
import shutil
layout = os.path.join(bookdir, "忍者物语 第01卷-小册子.pdf")
shutil.copyfile(body, layout)
shutil.copyfile(body, os.path.join(bookdir, "忍者物语 第01卷-小册子-2.pdf"))

w.pipeline_page.set_project(proj.id)
w.goto(w.page_index["pipeline"])
w.pipeline_page.on_show()
w.pipeline_page.goto_step(6)
for _ in range(6):
    APP.processEvents()
    time.sleep(0.12)
p = w.shelf_page.store.load().by_id(proj.id)
path = os.path.join(OUT, "plan-node.png")
w.grab().save(path)
print("shot plan ->", path)
print("计划:", (p.print_plan or {}).get("signatures"), "张:", (p.print_plan or {}).get("sheets"))

# 清理对话框
w.goto(w.page_index["shelf"])
w.shelf_page.refresh()
p = w.shelf_page.store.load().by_id(proj.id)
dlg = _CleanupDialog(p, w)
dlg.show()
for _ in range(6):
    APP.processEvents()
    time.sleep(0.12)
path = os.path.join(OUT, "cleanup-dialog.png")
dlg.grab().save(path)
print("shot cleanup ->", path, "| 清单", len(dlg.items), "个文件")
dlg.close()
