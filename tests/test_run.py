"""端到端：通过 UI 真正跑一遍四个无对话框的功能页。

页面顺序由 ui/app.py 的 NAV_PAGES 决定，这里一律按 key 取下标，
加页面/换位置都不用改这个文件。
"""
from pathlib import Path
import os, sys, time, tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication
from ui.app import MainWindow

app = QApplication(sys.argv)
w = MainWindow()
w.show(); w.move(-3200, -3200)
app.processEvents()

TMP = tempfile.gettempdir()
sample = os.path.join(TMP, "_t206.pdf")


def idx_of(key):
    return w.page_index[key]


def wait_done(page, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        app.processEvents()
        if getattr(page, "out_path", ""):
            return True
        time.sleep(0.03)
    return False


def run_page(key, name):
    idx = idx_of(key)
    w.goto(idx)
    app.processEvents()
    page = w.pages[idx]
    page.file.set_path(sample)
    app.processEvents()
    time.sleep(0.6)
    app.processEvents()
    print(f"\n== {name} ==")
    print("  预览:", page.preview_caption.text(), "| 统计:", [v.text() for v in page.stat_vals])
    page.run()
    ok = wait_done(page)
    out = getattr(page, "out_path", "")
    print("  完成:", ok, "| 状态:", w.status_lab.text())
    print("  输出:", out, "存在:", bool(out) and os.path.exists(out),
          (os.path.getsize(out) / 1e6 if out and os.path.exists(out) else 0), "MB")


run_page("booklet", "小册子")
run_page("stack", "四堆叠放")
run_page("fourup", "4合1")

# 合并：程序化加文件（跳过文件对话框只测核心）
w.goto(idx_of("merge"))
mp = w.pages[idx_of("merge")]
mp.files = [sample, os.path.join(TMP, "_out_4up.pdf")]
mp._refresh_list()
print("\n== 合并 ==\n  列表:", [v.text() for v in mp.stat_vals])
from core import pdfops
st = pdfops.merge_pdfs(mp.files, os.path.join(TMP, "_merge_ui.pdf"))
print("  合并结果:", st)

# 封面：直接调用渲染（对话框在 run() 里）
w.goto(idx_of("cover"))
cp = w.pages[idx_of("cover")]
cp.refresh_preview()
print("\n== 封面 ==\n  统计:", [v.text() for v in cp.stat_vals], "| 状态:", w.status_lab.text())
cp._render(120).save(os.path.join(TMP, "_cover_ui.png"))
print("  渲染 PNG OK")

# 新页：书架 / 生产线 / 分割 / 转换 能不能正常切进去（不真跑，只看契约）
for key in ("shelf", "pipeline", "cut", "convert"):
    w.goto(idx_of(key))
    app.processEvents()
    p = w.pages[idx_of(key)]
    print(f"\n== {key} ==\n  类: {type(p).__name__} | 标题: {w.title.text()} | "
          f"主按钮: {w.primary.text()} | 状态: {w.status_lab.text()}")
