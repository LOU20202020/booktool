"""复现：把 mobi 拖进「格式转换」页，到底有没有反应。

模拟 Qt 的拖放事件（dragEnter → drop），分别投给：
  ① 页面本身
  ② 光标真正所在的子控件（预览画布 / 源文件卡片 / 目录列表）——这是真实拖放走的路径
"""
from pathlib import Path
import os
import sys
import tempfile

os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["BOOKTOOL_SETTINGS"] = "BookToolDragTest"
TMP = os.environ.get("TEMP", tempfile.gettempdir())
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication

from ui.app import MainWindow

mobi = os.path.join(TMP, "convtest", "中文测试书.mobi")
if not os.path.exists(mobi):
    print("缺样张，先跑 tools/make_convert_sample.py")
    sys.exit(2)

APP = QApplication([])
w = MainWindow()
w.resize(1440, 900)
w.show()
w.move(-3200, -3200)
APP.processEvents()
w.goto(w.page_index["convert"])
APP.processEvents()
page = w.pages[w.page_index["convert"]]


def mime_for(path):
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(path)])
    return m


def try_drop_on(target, label):
    page.src = ""            # 清空，看这次有没有被填上
    APP.processEvents()
    m = mime_for(mobi)
    center = QPoint(target.width() // 2, target.height() // 2)
    enter = QDragEnterEvent(center, Qt.CopyAction, m, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(target, enter)
    accepted = enter.isAccepted()
    drop = QDropEvent(center, Qt.CopyAction, m, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(target, drop)
    APP.processEvents()
    print(f"  {label:<28} enter={accepted!s:<5} src={'SET ' + os.path.basename(page.src) if page.src else '未变'}")


print("\n=== 拖放模拟 ===")
print("页面 acceptDrops:", page.acceptDrops())
try_drop_on(page, "页面本身（ConvertPage）")
for name in ("canvas", "preview", "src_name", "btn_pick", "toc", "list"):
    child = getattr(page, name, None)
    if child is not None and hasattr(child, "width"):
        try_drop_on(child, f"子控件 {name}")

# 光标落在哪：取页面中心点命中的控件链
center = QPoint(page.width() // 2, page.height() // 2)
hit = page.childAt(center)
chain = []
while hit is not None:
    chain.append(f"{type(hit).__name__}(drops={hit.acceptDrops()})")
    hit = hit.parentWidget() if hit is not page else None
print("\n页面中心点命中的控件链：", " → ".join(chain) or "（无）")

print("\n=== 真实拖放的落点判定（Qt 规则：从最深的子控件往上找第一个 acceptDrops 的）===")
node = page.childAt(center)
receiver = None
while node is not None:
    if node.acceptDrops():
        receiver = node
        break
    node = node.parentWidget()
print("Qt 会交给：", type(receiver).__name__ if receiver else "（顶层窗口 MainWindow）")

print("\n=== 关键用例：把事件投给 Qt 真正会交给的那个子控件 ===")
if receiver is not None and receiver is not page:
    page.src = ""
    APP.processEvents()
    m = mime_for(mobi)
    c = QPoint(receiver.width() // 2, receiver.height() // 2)
    e = QDragEnterEvent(c, Qt.CopyAction, m, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(receiver, e)
    d = QDropEvent(c, Qt.CopyAction, m, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(receiver, d)
    APP.processEvents()
    ok = bool(page.src)
    print(f"  投给 {type(receiver).__name__}(viewport)：enter={e.isAccepted()} "
          f"src={'SET ' + os.path.basename(page.src) if ok else '未变（还是没反应）'}")
    if not ok:
        print("  ✘ 拖放仍被这个子控件吃掉")
    else:
        print("  ✔ 拖放已被转回页面，mobi 能识别")
else:
    print("  页面中心没有抢拖放的子控件")
