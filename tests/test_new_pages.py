"""新页面（书架 / 生产线 / 分割 / 转换）在 Windows 上的端到端自测。

全程离屏，不弹任何对话框、不碰真打印机：
1. 造一本 40 页的 A5 测试书（书脊/页脚/章扉都在，便于肉眼确认）
2. 把整本拖进「书架」→ 有系列、有卷
3. 进「生产线」→ 七步状态
4. 「分割」→ 原稿旁边真的多出 封面素材 / 封底素材 / 正文 三个 PDF
5. 封面联动 → 封面图 / 封底图两个槽都有值
6. 12 个页面全部切一遍 + 首页卡片点进去都落在对的页
7. 打开书架的 shelf.json 回读
"""
from pathlib import Path
import json
import os
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="btwin-")
os.environ["LOCALAPPDATA"] = TMP          # 书架 / 缩略图 / 日志都落临时目录，不污染真实状态
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf
from PySide6.QtWidgets import QApplication

from ui.app import MainWindow

APP = QApplication([])
MM = 72 / 25.4
FAIL = []


def check(cond, what, extra=""):
    print(("  ✔ " if cond else "  ✘ ") + what + (f"  {extra}" if extra else ""))
    if not cond:
        FAIL.append(what)
    return cond


def make_book(folder, name="忍者物语 第01卷", pages=40):
    """造一本 A5 的测试书：目录页 + 章扉 + 正文，每页有大页号。"""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".pdf")
    doc = pymupdf.open()
    w, h = 148 * MM, 210 * MM
    for i in range(pages):
        page = doc.new_page(width=w, height=h)
        page.draw_rect(pymupdf.Rect(20, 20, w - 20, h - 20), color=(0.1, 0.1, 0.1), width=0.8)
        page.insert_text((28, 46), f"第 {i + 1} 面", fontsize=22, fontname="china-s")
        page.insert_text((28, 70), f"{name} · 测试内容 {i + 1}", fontsize=11, fontname="china-s")
        page.insert_text((w - 60, h - 26), str(i + 1), fontsize=14, fontname="china-s")
    doc.set_toc([[1, "第一章", 1], [1, "第二章", 20]])
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


def spin(cond, timeout=30.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        APP.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


print("\n=== 1) 造测试书 + 启动主窗口 ===")
bookdir = os.path.join(TMP, "单行本测试")
src = make_book(bookdir)
print("  原稿:", src, f"{os.path.getsize(src) / 1024:.0f} KB")

w = MainWindow()
w.resize(1440, 900)
w.show()
APP.processEvents()

print("\n=== 2) 书架：拖一个文件夹进去 ===")
shelf = w.shelf_page
n = shelf.add_folder(bookdir)
check(n == 1, "认出一本", f"n={n}")
p = shelf.shelf.projects[0]
check(p.source and p.source.path.endswith(".pdf"), "原稿已登记", os.path.basename(p.source.path))
check(bool(shelf.shelf.series), "系列已建立", [s.name for s in shelf.shelf.series])
print("  卷号解析:", p.index, "| 名称:", p.name)

print("\n=== 3) 生产线：七步状态 ===")
pipe = w.pipeline_page
ok = pipe.set_project(p.id)
check(ok, "选中这本书")
APP.processEvents()
states = {i: p.step_state(i)[0] for i in range(1, 8)}
print("  状态:", states)
check(states[1] == "done", "第①步 导入 = done")

print("\n=== 4) 分割：生出 封面素材 / 封底素材 / 正文 ===")
w.goto(w.page_index["cut"])
cut = w.split_tool_page
APP.processEvents()
cut.set_source(src)
APP.processEvents()
cut.sp_front.set_value(2)
cut.sp_tail.set_value(2)
cut.run()
done = spin(lambda: bool(cut.out), timeout=60)
check(done, "分割完成", cut.out.get("body", "") if cut.out else "超时")
for tag, key in (("封面素材", "cover"), ("封底素材", "back"), ("正文", "body")):
    path = cut.out.get(key) or ""
    check(bool(path) and os.path.exists(path), f"{tag} 文件存在",
          f"{os.path.basename(path)} {os.path.getsize(path) / 1024:.0f} KB" if path else "缺失")
if cut.out:
    with pymupdf.open(cut.out["body"]) as d:
        body_pages = d.page_count
    with pymupdf.open(cut.out["cover"]) as d:
        cover_pages = d.page_count
    with pymupdf.open(src) as d:
        total = d.page_count
    check(body_pages == total - 4 and cover_pages == 2,
          "页数对得上", f"原稿 {total} = 封面 2 + 正文 {body_pages} + 封底 2")

print("\n=== 5) 生产线状态跟着走 ===")
pipe.on_show()
APP.processEvents()
p2 = shelf.store.load().by_id(p.id) or p
print("  状态:", {i: p2.step_state(i)[0] for i in range(1, 8)})

print("\n=== 6) 封面联动：素材进图槽 ===")
from ui import cover_link
filled = cover_link.fill_cover(w, cover=cut.out.get("cover", ""), back=cut.out.get("back", ""))
check(bool(filled), "有槽位被填上", str(filled))
cover = w.pages[w.page_index["cover"]]
w.goto(w.page_index["cover"])
APP.processEvents()
check(getattr(cover, "front_img", None) is not None and bool(cover.front_img.path),
      "封面图槽有路径", os.path.basename(cover.front_img.path or ""))
check(getattr(cover, "_right_rail", None) is not None, "右栏关闭把手已挂上")

print("\n=== 6.5) 打印记账：打完第⑥步要变完成 ===")
# 先造一份"排版产物"（真实流程里是小册子页生成的），生产线会自动重扫目录认领它
import shutil as _sh
layout_path = os.path.join(bookdir, "忍者物语 第01卷-小册子.pdf")
_sh.copyfile(cut.out["body"], layout_path)
pipe.on_show()
APP.processEvents()
p3 = shelf.store.load().by_id(p.id)
print("  ⑤ 排版 =", p3.step_state(5)[0], "| ⑥ 打印 =", p3.step_state(6)[0])
check(p3.step_state(5)[0] == "done", "排版产物被生产线自动认领")

# 不碰真打印机：把送印函数换成假的，只验证"记账"这条线
from core import printpdf as _pp
_real_print, _real_duplex = _pp.print_pdf, _pp.supports_duplex
_pp.print_pdf = lambda *a, **k: "测试打印机"
_pp.supports_duplex = lambda *a, **k: True
try:
    before = len(shelf.store.load().by_id(p.id).prints)
    w.start_print(layout_path, dict(printer="", copies=2, duplex="short",
                                    paper="A4", first_page_only=False,
                                    pages="", flip="short"))
    done = spin(lambda: len(shelf.store.load().by_id(p.id).prints) > before, timeout=20)
    check(done, "送印成功写进打印账")
    p4 = shelf.store.load().by_id(p.id)
    ev = p4.prints[-1]
    print("  记录:", ev.at, "|", ev.tag, "|", ev.sheets, "张 |", ev.job, "| 样张", ev.sample)
    check(ev.tag == "duplex" and ev.sheets == 36 and ev.job == "测试打印机",
          "记账内容对（36 面双面 × 2 份 = 36 张纸）", f"{ev.tag}/{ev.sheets}")
    check(p4.step_state(6)[0] == "done", "⑥ 打印 = done", p4.step_state(6)[1])
    check(p4.status == "已打印", "书架状态 = 已打印", p4.status)

    # 只打样张：账上留痕，但不算这一步做完
    before = len(p4.prints)
    w.start_print(layout_path, dict(printer="", copies=1, duplex="none", paper="A4",
                                    first_page_only=False, pages="", flip="short"),
                  sample=True)
    spin(lambda: len(shelf.store.load().by_id(p.id).prints) > before, timeout=20)
    p5 = shelf.store.load().by_id(p.id)
    check(p5.prints[-1].sample and len(p5.real_prints) == 1,
          "样张记账但不计入完成", f"总 {len(p5.prints)} 条 / 真打 {len(p5.real_prints)} 条")

    # 排版文件改过 → 应标"需重跑"
    future = time.time() + 30
    os.utime(layout_path, (future, future))
    p6 = shelf.store.load().by_id(p.id)
    check(p6.step_state(6)[0] == "stale", "排版改过后 ⑥ = stale", p6.step_state(6)[1])
finally:
    _pp.print_pdf, _pp.supports_duplex = _real_print, _real_duplex

print("\n=== 7) 12 个页面全切一遍 ===")
for key, idx in w.page_index.items():
    w.goto(idx)
    APP.processEvents()
    page = w.pages[idx]
    print(f"  {idx:>2} {w.title.text():<6} {type(page).__name__:<14} 主按钮={w.primary.text()} 状态={w.status_lab.text()[:34]}")

print("\n=== 8) 首页卡片都落在对的页 ===")
from ui.home import TOOLS
from ui.home import ToolCard
cards = w.home.findChildren(ToolCard)
check(len(cards) == len(TOOLS), "卡片数 = 工具数", f"{len(cards)} / {len(TOOLS)}")
for (key, name, _desc), card in zip(TOOLS, cards):
    target = w.pages[card.index]
    want = w.page_index.get(key)
    ok = card.index == want
    print(f"  {name:<6} → 第 {card.index} 页 {type(target).__name__:<14} {'✔' if ok else '✘ 应该是 ' + str(want)}")
    if not ok:
        FAIL.append("卡片 " + name)

print("\n=== 9) 书架数据落盘 ===")
shelf_json = os.path.join(TMP, "XPlus", "BookTool", "shelf.json")
ok = os.path.exists(shelf_json)
check(ok, "shelf.json 已写出", shelf_json)
if ok:
    data = json.load(open(shelf_json, encoding="utf-8"))
    print("  系列:", len(data.get("series", [])), "| 书:", len(data.get("projects", [])))

print("\n=== 10) 打印页仍能列出打印机 ===")
from core import printpdf
try:
    printers = printpdf.printers()
    print("  打印机:", printers or "（这台机没装打印机）")
except Exception as e:
    print("  列打印机失败:", e)

print("\n" + ("全部通过" if not FAIL else f"失败 {len(FAIL)} 项：" + "；".join(FAIL)))
sys.exit(1 if FAIL else 0)
