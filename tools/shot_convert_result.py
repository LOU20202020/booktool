"""拍「在软件里真的转完一本书」的样子：预览 + 目录 + 状态栏。

用真 Calibre 转换，出图：%TEMP%\\shots\\convert-done.png
"""
from pathlib import Path
import os
import sys
import tempfile
import time

os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["BOOKTOOL_SETTINGS"] = "BookToolConvShot"
TMP = os.environ.get("TEMP", tempfile.gettempdir())
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from ui.app import MainWindow

OUT = os.path.join(TMP, "shots")
os.makedirs(OUT, exist_ok=True)
APP = QApplication([])

src = os.path.join(TMP, "convtest", "中文测试书.epub")
if not os.path.exists(src):
    print("缺样张：先跑 tools/make_convert_sample.py")
    sys.exit(2)

w = MainWindow()
w.resize(1440, 900)
w.show()
w.move(-3200, -3200)
APP.processEvents()
w.goto(w.page_index["convert"])
page = w.pages[w.page_index["convert"]]
APP.processEvents()

page.set_source(src)
APP.processEvents()
t0 = time.time()
page.run()
while time.time() - t0 < 180 and not page.out:
    APP.processEvents()
    time.sleep(0.03)

for _ in range(8):
    APP.processEvents()
    time.sleep(0.15)

path = os.path.join(OUT, "convert-done.png")
w.grab().save(path)
print("shot ->", path)
print("状态:", w.status_lab.text())
print("输出:", page.out, "| 目录", page.toc.count(), "条")
