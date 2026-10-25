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
os.environ["LOCALAPPDATA"] = TMP
os.environ["BOOKTOOL_SETTINGS"] = "BookToolTest"   # 不读你真实设置里的书脊厚度          # 书架 / 缩略图 / 日志都落临时目录，不污染真实状态
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

print("\n=== 9.5) 书脊：默认 12.5mm、字号不许超出书脊宽度 ===")
w.goto(w.page_index["cover"])
APP.processEvents()
cover_page = w.pages[w.page_index["cover"]]
check(float(cover_page.spine.value()) == 12.5, "默认厚度 = 12.5mm",
      str(cover_page.spine.value()))
w_mm, h_mm = int(cover_page.w.value()), int(cover_page.h.value())
want_idx = 0 if (w_mm, h_mm) == (105, 148) else 1
check(cover_page.preset.index() == want_idx, "开本选中项和实际宽高一致",
      f"{w_mm}×{h_mm} / 选中 #{cover_page.preset.index()}")
check("25pt" in cover_page.spine_note.text(), "提示写明 12.5mm 最多 25pt",
      cover_page.spine_note.text())
cover_page.spine_edit.setText("忍者物语 第一卷")
APP.processEvents()
cover_page.pages_count.set_value(400)          # 老版本会据此改厚度
cover_page.paper_gsm.setCurrentIndex(2)
APP.processEvents()
spin(lambda: False, timeout=0.3)
check(float(cover_page.spine.value()) == 12.5, "改页数/纸张不再改厚度",
      str(cover_page.spine.value()))
check(cover_page.spine_edit.text() == "忍者物语 第一卷", "有厚度时书脊文字照常印",
      repr(cover_page.spine_edit.text()))

# 字号超宽：3mm 的脊最多 6pt，界面直接把 40pt 压回来
cover_page.spine_pt.set_value(40)
APP.processEvents()
spin(lambda: False, timeout=0.3)
check(float(cover_page.spine_pt.value()) <= 25.0, "12.5mm 的书脊字号不超过 25pt",
      str(cover_page.spine_pt.value()))
cover_page.spine.set_value(3)
APP.processEvents()
spin(lambda: False, timeout=0.3)
check(float(cover_page.spine_pt.value()) == 6.0, "厚 3mm 时字号压到 6pt",
      str(cover_page.spine_pt.value()))
check("6pt" in cover_page.spine_note.text(), "提示写明 3mm 最多 6pt",
      cover_page.spine_note.text())

# 渲染层也拦一道（不靠界面）
from core import cover as cover_core
img = cover_core.render_cover(148, 210, 3, spine_text="忍者物语", spine_pt=40,
                              dpi=120, vertical=True)
check(img.info.get("spine_pt_clamped") is True, "渲染时把超宽字号压下来",
      f"实际 {img.info.get('spine_pt')}pt")
check(float(img.info.get("spine_pt") or 0) <= 6.2, "压下来的字号符合 3mm 书脊",
      str(img.info.get("spine_pt")))
img2 = cover_core.render_cover(148, 210, 3, spine_text="忍者物语", spine_pt=40,
                               dpi=120, vertical=False)
check(float(img2.info.get("spine_pt") or 0) <= 6.2, "横排书脊同样受限制",
      str(img2.info.get("spine_pt")))

# 厚度归 0 → 不印书脊文字（原有行为保留）
cover_page.spine.set_value(0)
APP.processEvents()
spin(lambda: False, timeout=0.3)
check(cover_page.spine_edit.text() == "\u200b", "厚度 0 时书脊文字不印",
      repr(cover_page.spine_edit.text()))

print("\n=== 10) 打印计划 + 清理中间产物 ===")
from core import printplan
from core.shelf import cleanup as CLEAN

# 生产线 on_show 会按成品算一份计划写进 bookshelf
w.goto(w.page_index["pipeline"])
pipe.set_project(p.id)
pipe.on_show()
APP.processEvents()
p7 = shelf.store.load().by_id(p.id)
plan = p7.print_plan or {}
check(bool(plan) and int(plan.get("sheets") or 0) > 0,
      "打印计划已写进这本书", printplan.summary(plan))
check(len(plan.get("signatures") or []) >= 1,
      "计划里有帖明细", f"{len(plan.get('signatures') or [])} 帖")
if plan.get("signatures"):
    check(plan["sheets"] == sum(s["sheets"] for s in plan["signatures"]),
          "帖张数加起来 = 总张数", f"{plan['sheets']}")
check(not printplan.is_stale(plan, p7), "刚算的计划不算过期")

# 清理：先验证不删的东西
p7.final = layout_path
items_f = CLEAN.candidates(p7, keep_body=True)
check(all(os.path.abspath(i.path) != os.path.abspath(layout_path) for i in items_f),
      "定稿不参与清理")
if p7.items:
    p7.items[0].manual = True
    manual_path = os.path.abspath(p7.items[0].path)
    items_f2 = CLEAN.candidates(p7, keep_body=True)
    check(all(os.path.abspath(i.path) != manual_path for i in items_f2),
          "手动加入的不参与清理")
    p7.items[0].manual = False
p7.final = None
check(not any(i.kind == "body" for i in CLEAN.candidates(p7, keep_body=True)),
      "默认不把正文算进清理清单")
check(any(i.kind == "body" for i in CLEAN.candidates(p7, keep_body=False)),
      "取消勾选后正文才可清理")

items = CLEAN.candidates(p7, keep_body=True)
before_size = CLEAN.total_size(items)
res = CLEAN.delete(p7, items)
check(res["freed"] == before_size, "释放体积和清单一致", CLEAN.human_size(res["freed"]))
check(not res["failed"], "没有删失败的文件", str(res["failed"])[:60])
check(all(not os.path.exists(x) for x in res["deleted"]), "文件真的从磁盘消失")
check(os.path.exists(cut.out["body"]), "正文保留住了")
sh = shelf.store.load()
sh.projects = [p7 if x.id == p7.id else x for x in sh.projects]
shelf.store.save(sh)
p8 = shelf.store.load().by_id(p.id)
check(p8 is not None, "清理后书架还能正常读出来")
check(all(os.path.exists(i.path) for i in p8.items), "书架里不再挂着已删文件",
      f"{len(p8.items)} 项")
check(not any(os.path.abspath(i.path) in {os.path.abspath(x) for x in res["deleted"]}
              for i in p8.items), "删除的文件没留在 items 里")

print("\n=== 11) 拖放：把文件拖到预览画布上也要认 ===")
from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent


def _deepest_drop_target(page):
    node = page.childAt(QPoint(page.width() // 2, page.height() // 2))
    while node is not None:
        if node.acceptDrops():
            return node
        node = node.parentWidget()
    return None


def _drop_on(page, path):
    tgt = _deepest_drop_target(page) or page
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path)])
    pos = QPoint(tgt.width() // 2, tgt.height() // 2)
    QApplication.sendEvent(tgt, QDragEnterEvent(pos, Qt.CopyAction, mime,
                                               Qt.LeftButton, Qt.NoModifier))
    QApplication.sendEvent(tgt, QDropEvent(pos, Qt.CopyAction, mime,
                                           Qt.LeftButton, Qt.NoModifier))
    APP.processEvents()
    return tgt


# 转换页：mobi 拖到画布 → 源文件被填上（这就是用户报的"拖进去没反应"）
w.goto(w.page_index["convert"])
APP.processEvents()
conv = w.pages[w.page_index["convert"]]
conv.src = ""
mobi_path = os.path.join(os.environ.get("TEMP", TMP), "convtest", "中文测试书.mobi")
if os.path.exists(mobi_path):
    tgt = _drop_on(conv, mobi_path)
    check(bool(conv.src), "mobi 拖到画布被认出",
          f"{type(tgt).__name__} → {os.path.basename(conv.src) if conv.src else '未变'}")
    check(conv.src_name.text().endswith(".mobi"), "界面上的文件名也更新了",
          conv.src_name.text()[:30])
    check(w.primary.isEnabled(), "拖完主按钮立刻可点（之前是灰的）",
          f"{w.primary.text()} / enabled={w.primary.isEnabled()}")
else:
    print("  （跳过：没有 mobi 样张）")

# 小册子页：PDF 拖到画布 → 主窗口接手，当前文稿被设置
w.goto(w.page_index["booklet"])
APP.processEvents()
booklet = w.pages[w.page_index["booklet"]]
old = booklet.file.path
tgt = _drop_on(booklet, src)
check(booklet.file.path.endswith(os.path.basename(src)),
      "PDF 拖到画布被主窗口接住",
      f"{type(tgt).__name__} → {os.path.basename(booklet.file.path or '')}")
check(booklet.file.path != old or booklet.file.path == src, "文件路径确实换成了拖进来的那份")
check(w.primary.isEnabled(), "PDF 拖进来后主按钮也可点", w.primary.text())

print("\n" + ("全部通过" if not FAIL else f"失败 {len(FAIL)} 项：" + "；".join(FAIL)))
sys.exit(1 if FAIL else 0)
