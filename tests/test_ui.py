from pathlib import Path
import os, sys, time, tempfile
os.environ.pop("QT_QPA_PLATFORM", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from ui.app import MainWindow

app = QApplication(sys.argv)
w = MainWindow()
w.resize(1440, 900)
w.show()
w.move(-3200, -3200)
app.processEvents()

out_dir = os.path.join(tempfile.gettempdir(), "shots")
os.makedirs(out_dir, exist_ok=True)

# 载入一个样张
sample = os.path.join(tempfile.gettempdir(), "_t206.pdf")
for i, page in enumerate(w.pages):
    w.goto(i)
    app.processEvents()
    time.sleep(0.15)
    app.processEvents()
    shot = os.path.join(out_dir, f"page{i}.png")
    w.grab().save(shot)
    print("shot", i, page.title, "->", shot)

# 小册子页加载文件（按 key 取下标，页面顺序变了也不用改这里）
w.goto(w.page_index["booklet"])
bp = w.pages[w.page_index["booklet"]]
if os.path.exists(sample):
    bp.file.set_path(sample)
    app.processEvents()
    time.sleep(1.2)
    app.processEvents()
    w.grab().save(os.path.join(out_dir, "booklet_loaded.png"))
    print("booklet loaded ->", bp.preview_caption.text(), bp.stat_vals[0].text())
