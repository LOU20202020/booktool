"""宣传片录制驱动：驱动真实的 MainWindow 走一遍典型操作，同时用 ffmpeg 录屏。

用法（录制由外部 ffmpeg 负责，见 record.py）：
    python promo/demo.py

动作序列按真实鼠标（QCursor 移动 + QTest 点击）执行，关键节拍写进 promo/beats.json。
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("BOOKTOOL_SETTINGS", "BookToolDemo")

import pymupdf as fitz  # noqa: E402
from PySide6.QtCore import QEventLoop, QPoint, QSettings, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QCursor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.app import MainWindow  # noqa: E402

SAMPLE = os.environ.get(
    "DEMO_PDF", r"C:\Users\LOU0122\Downloads\廖雪峰Java教程-打印版.pdf")
BEATS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "beats.json")


class Demo:
    def __init__(self, win: MainWindow):
        self.w = win
        self.t0 = None
        self.beats: list[tuple[str, float]] = []

    # ---------------- 基础动作 ----------------
    def mark(self, name: str):
        if self.t0 is None:
            self.t0 = QTest.qWait  # 占位，真正时间在 run() 里
        import time
        self.beats.append((name, round(time.time() - self.start, 2)))
        print(f"[{self.beats[-1][1]:6.2f}] {name}", flush=True)

    def wait(self, seconds: float):
        loop = QEventLoop()
        QTimer.singleShot(int(seconds * 1000), loop.quit)
        loop.exec()

    def glide(self, point: QPoint, seconds: float = 0.55):
        """让真实光标平滑移过去，录屏里能看见鼠标在走。"""
        start = QCursor.pos()
        steps = max(8, int(seconds * 60))
        for i in range(1, steps + 1):
            t = i / steps
            ease = t * t * (3 - 2 * t)          # smoothstep
            QCursor.setPos(QPoint(
                int(start.x() + (point.x() - start.x()) * ease),
                int(start.y() + (point.y() - start.y()) * ease)))
            QApplication.processEvents()
            QTest.qWait(1000 // 60)
        QCursor.setPos(point)
        QApplication.processEvents()

    def goto_widget(self, widget, seconds: float = 0.55, click: bool = True):
        if widget is None:
            return
        centre = widget.mapToGlobal(widget.rect().center())
        self.glide(centre, seconds)
        self.wait(0.18)
        if click:
            QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, widget.rect().center())
            self.wait(0.25)

    def type_number(self, edit, value: str):
        self.goto_widget(edit, 0.45)
        edit.setFocus()
        QTest.keyClick(edit, Qt.Key_A, Qt.ControlModifier)
        for ch in value:
            QTest.keyClick(edit, ch)
            QTest.qWait(90)
        QTest.keyClick(edit, Qt.Key_Return)
        self.wait(0.3)

    # ---------------- 剧本 ----------------
    def run(self):
        import time
        self.start = time.time()
        w = self.w

        QApplication.processEvents()
        self.mark("home")

        # --- 1. 首页停一下，光标从右下角起来
        QCursor.setPos(w.mapToGlobal(QPoint(w.width() - 80, w.height() - 60)))
        self.wait(2.2)

        # --- 2. 进入小册子
        self.goto_widget(w.nav_buttons[0], 0.75)
        self.mark("booklet_page")
        bp = w.pages[0]
        bp.file.set_path(SAMPLE)
        self.wait(1.4)
        self.mark("file_loaded")

        # --- 3. 点开始拼版
        self.goto_widget(w.primary, 0.6)
        self.mark("click_impose")
        # 等真实作业完成（进度条走完 + 按钮复位）
        deadline = time.time() + 90
        while time.time() < deadline:
            QApplication.processEvents()
            if bp.out_path:
                break
            QTest.qWait(40)
        self.mark("imposed")
        self.wait(2.4)

        # --- 4. 点右侧缩略图翻预览（两次）
        thumbs = bp.thumbs.list
        if thumbs.count() > 3:
            self.goto_widget(thumbs.viewport(), 0.5, click=False)
            for row in (2, 5):
                item = thumbs.item(row) or thumbs.item(0)
                rect = thumbs.visualItemRect(item)
                thumbs.scrollToItem(item)
                pt = thumbs.viewport().mapToGlobal(rect.center())
                self.glide(pt, 0.45)
                QTest.mouseClick(thumbs.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())
                self.wait(0.9)
        self.mark("thumbs")

        # --- 5. 封面：改页数，看书脊自动算
        self.goto_widget(w.nav_buttons[1], 0.65)
        self.mark("cover_page")
        self.wait(0.9)
        cp = w.pages[1]
        self.type_number(cp.pages_count.edit, "204")
        self.mark("spine_calc")
        self.wait(1.8)

        # --- 6. 打印页：带着拼好的文件跳过去，再点开打印设置看范围
        self.goto_widget(w.nav_buttons[7], 0.65)
        self.mark("print_page")
        self.wait(2.6)   # 只拍界面，绝不点打印（那个按钮会直接送印）

        # --- 7. 回首页收尾
        self.goto_widget(w.logo_btn, 0.6)
        self.mark("home_again")
        self.wait(2.0)

        self.mark("end")
        with open(BEATS, "w", encoding="utf-8") as f:
            json.dump(self.beats, f, ensure_ascii=False, indent=1)
        print("beats →", BEATS, flush=True)
        self.w.close()
        QApplication.quit()


def main():
    app = QApplication(sys.argv)
    # 必须先写设置再建窗口，否则会弹首次欢迎对话框挡住录制
    s = QSettings("XPlus", os.environ["BOOKTOOL_SETTINGS"])
    s.setValue("seen_welcome", True)
    s.sync()
    win = MainWindow()
    win.setWindowTitle("BookTool Demo")
    win.resize(1680, 1000)
    win.move(120, 60)
    win.show()
    win.raise_()
    win.activateWindow()

    demo = Demo(win)
    flag = os.path.join(os.path.dirname(os.path.abspath(__file__)), "go.flag")

    def wait_flag():
        """窗口就绪后写 ready.flag；外部开录后再建 go.flag，动作才真正开始。"""
        import time as _t
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ready.flag"), "w") as fh:
            fh.write("1")
        deadline = _t.time() + 120
        while not os.path.exists(flag) and _t.time() < deadline:
            QApplication.processEvents()
            QTest.qWait(60)
        demo.run()

    # 先让窗口画完再开始，避免第一帧发白
    QTimer.singleShot(1200, wait_flag)
    app.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
