"""渲染自测：自绘的东西必须真的画出像素来。

为什么单开一个文件：其余测试只验「页面能打开、控件里有文字」。
把画布拆文件时漏了 STATE_STYLE 的 import，节点一个都画不出来，
ui_smoke 与 test_new_pages 却全绿 —— 因为没人看像素。

做法很笨但管用：
1. 真画一帧（`grab()`），数不同颜色。只有背景色 = 什么都没画。
2. `grab()` 用 try/except 包住：PySide6 会把 paint 里的异常抛回调用方
   （试过在文件描述符层接 stderr，Windows 上抓不到，别走那条路）。

不需要打印机、不需要外部引擎，所以能进 CI。
"""
from __future__ import annotations

import os
import sys

from _check import Checker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_C = Checker()
check = _C.check

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.shelf.model import ST_BLOCKED, ST_DONE, ST_SKIP, ST_STALE, ST_TODO, STEPS  # noqa: E402
from ui.pipeline_canvas import _Canvas, _NodeItem  # noqa: E402

APP = QApplication.instance() or QApplication([])


def distinct_colors(img, grid: int = 28) -> int:
    """在图上按网格采样，数不同颜色 —— 只有背景色就是「什么都没画」。"""
    w, h = img.width(), img.height()
    if w <= 0 or h <= 0:
        return 0
    seen = set()
    for x in range(0, w, max(1, w // grid)):
        for y in range(0, h, max(1, h // grid)):
            seen.add(img.pixel(x, y))
    return len(seen)


def render(canvas):
    """画一帧，返回 (图片, 异常描述或空串)。"""
    err = ""
    img = None
    try:
        canvas.show()
        for _ in range(3):
            APP.processEvents()
        img = canvas.grab().toImage()
        APP.processEvents()
    except Exception as exc:                     # noqa: BLE001 —— 这里就是要抓住一切
        err = f"{type(exc).__name__}: {exc}"
    finally:
        canvas.close()
    return img, err


def main() -> int:
    # ---------------- 生产线画布：七道工序 ----------------
    canvas = _Canvas()
    canvas.resize(900, 320)
    for step in STEPS:
        canvas._scene.addItem(_NodeItem(step, ST_TODO, "产物", "状态"))
    check("画布：七个节点都进了场景", len(canvas._scene.items()) >= len(STEPS),
          f"scene 里有 {len(canvas._scene.items())} 个 item")

    img, err = render(canvas)
    check("画布：paint 期间没有异常", not err, err[:90])
    colors = distinct_colors(img) if img is not None else 0
    check("画布：画出来的不是空白", colors > 3,
          f"{img.width() if img else 0}x{img.height() if img else 0}，{colors} 种颜色")

    # 每种状态都单独画一遍：paint 里按状态查表，缺一种 key 就是画不出来
    for state, label in ((ST_DONE, "完成"), (ST_STALE, "需重跑"), (ST_SKIP, "跳过"),
                         (ST_BLOCKED, "缺输入")):
        one = _Canvas()
        one.resize(320, 200)
        one._scene.addItem(_NodeItem(STEPS[0], state, "产物", "状态"))
        img2, err2 = render(one)
        check(f"画布：状态「{label}」画得出来",
              not err2 and img2 is not None and distinct_colors(img2) > 3, err2[:70])

    return _C.finish("✅ 渲染全部通过")


if __name__ == "__main__":
    sys.exit(main())
