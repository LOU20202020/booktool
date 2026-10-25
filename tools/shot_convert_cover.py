"""拍「拖进来就显示封面」：转前有封面预览，转后换成第 1 页。

出图：%TEMP%\\shots\\convert-cover.png（转前）/ convert-after.png（转后）
"""
from pathlib import Path
import os
import sys
import tempfile
import time

os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["BOOKTOOL_SETTINGS"] = "BookToolCoverShot"
TMP = os.environ.get("TEMP", tempfile.gettempdir())
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from ui.app import MainWindow

SRC = os.path.join(os.path.expanduser("~"), "Downloads",
                   "火影忍者 第1卷 火影是全世界最好看的漫画,不接受反驳 (岸本齐史) "
                   "(z-library.sk, 1lib.sk, z-lib.sk).mobi")
OUT = os.path.join(TMP, "shots")
os.makedirs(OUT, exist_ok=True)

if not os.path.exists(SRC):
    print("找不到他的 mobi，改用测试样张")
    SRC = os.path.join(TMP, "convtest", "中文测试书.mobi")

APP = QApplication([])
w = MainWindow()
w.resize(1440, 900)
w.show()
w.move(-3200, -3200)
APP.processEvents()
w.goto(w.page_index["convert"])
APP.processEvents()
page = w.pages[w.page_index["convert"]]


def spin(cond, timeout=60.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        APP.processEvents()
        if cond():
            return True
        time.sleep(0.03)
    return False


def shot(name):
    for _ in range(6):
        APP.processEvents()
        time.sleep(0.12)
    path = os.path.join(OUT, name)
    w.grab().save(path)
    print("shot ->", path)


page.set_source(SRC)
spin(lambda: page.preview.item is not None or not page.placeholder.text().startswith("正在"), 20)
print("转前：preview.item =", type(page.preview.item).__name__ if page.preview.item else None,
      "| hint =", page.preview_hint.text(), "| placeholder =", page.placeholder.text()[:30])
shot("convert-cover.png")

page.run()
spin(lambda: bool(page.out), 300)
shot("convert-after.png")
print("转后：", w.status_lab.text(), "| hint =", page.preview_hint.text())
print("主按钮：", w.primary.text(), "可点:", w.primary.isEnabled())
