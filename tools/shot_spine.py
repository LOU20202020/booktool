"""拍封面页「书脊只认实测」的三种状态。

出图：%TEMP%\\shots\\spine-0.png（没填厚度）/ spine-12.png（填了 12.5mm）
"""
from pathlib import Path
import os
import sys
import tempfile
import time

os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["BOOKTOOL_SETTINGS"] = "BookToolSpineShot"
TMP = os.environ.get("TEMP", tempfile.gettempdir())
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication

from ui.app import MainWindow

OUT = os.path.join(TMP, "shots")
os.makedirs(OUT, exist_ok=True)
APP = QApplication([])

w = MainWindow()
w.resize(1440, 900)
w.show()
w.move(-3200, -3200)
APP.processEvents()

cover = w.pages[w.page_index["cover"]]
w.goto(w.page_index["cover"])
for _ in range(6):
    APP.processEvents()
    time.sleep(0.1)


def shot(name):
    for _ in range(4):
        APP.processEvents()
        time.sleep(0.15)
    path = os.path.join(OUT, f"spine-{name}.png")
    w.grab().save(path)
    print("shot", name, "->", path)


# 1) 默认 12.5mm：书脊有字、提示写明字号上限
cover.spine_edit.setText("忍者物语 第一卷")
cover.spine.set_value(12.5)
shot("12")

# 2) 压到 3mm：字号自动压到 6pt，不许压到封面
cover.spine.set_value(3)
shot("3")

# 3) 归 0：不印书脊文字
cover.spine.set_value(0)
shot("0")

print("\n厚度:", cover.spine.value(), "| 书脊文字:", repr(cover.spine_edit.text()),
      "| 提示:", cover.spine_note.text())
