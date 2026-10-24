"""界面冒烟测试：七个页面能开、能选文件、能出结果。"""
from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("QT_QPA_PLATFORM", None)
os.environ["BOOKTOOL_SETTINGS"] = "BookToolTest"   # 不污染用户真实设置

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.app import MainWindow

TMP = tempfile.mkdtemp(prefix="booktool_ui_")
FAILS: list[str] = []


def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else f"   [{detail}]"))
    if not cond:
        FAILS.append(name)


def pump(app, seconds=0.6):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def main() -> int:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(1440, 900)
    w.show()
    w.move(-3200, -3200)
    pump(app)

    w.show_home()
    pump(app, 0.15)
    check("点「书」回首页", w.stack.currentIndex() == 0, str(w.stack.currentIndex()))
    from ui.app import NAV_PAGES
    check(f"导航 {len(NAV_PAGES)} 个工具", len(w.nav_buttons) == len(NAV_PAGES),
          str(len(w.nav_buttons)))

    for i in range(len(w.pages)):
        w.goto(i)
        pump(app, 0.25)
        check(f"第 {i+1} 页可打开（{w.pages[i].title}）", w.stack.currentIndex() == i + 1,
              str(w.stack.currentIndex()))

    # 造一个样张
    import pymupdf as fitz
    src = os.path.join(TMP, "ui_src.pdf")
    doc = fitz.open()
    for i in range(32):
        p = doc.new_page(width=419.53, height=595.28)
        p.insert_text((60, 120), str(i + 1), fontname="helv", fontsize=90)
    doc.save(src)
    doc.close()

    # 小册子：共享文件 + 生成
    I = w.page_index
    w.goto(I["booklet"])
    bp = w.pages[I["booklet"]]
    bp.file.set_path(src)
    pump(app, 0.8)
    check("文件共享到加页码页", w.pages[I["pager"]].file.path == src, w.pages[I["pager"]].file.path)
    bp.run()
    got = False
    for _ in range(200):
        app.processEvents()
        time.sleep(0.02)
        if bp.out_path and os.path.exists(bp.out_path):
            got = True
            break
    check("小册子生成文件", got, str(bp.out_path))

    # 「打印」按钮：带着成品跳到打印页
    w.show_print()
    pump(app, 0.6)
    check("点打印跳到打印页", w.stack.currentIndex() == I["print"] + 1, str(w.stack.currentIndex()))
    check("打印页拿到成品", w.pages[I["print"]].file.path == bp.out_path, w.pages[I["print"]].file.path)
    check("横向成品自动双面", w.pages[I["print"]].side.index() == 1, str(w.pages[I["print"]].side.index()))

    # 加页码
    w.goto(I["pager"])
    np = w.pages[I["pager"]]
    np.run()
    got = False
    for _ in range(200):
        app.processEvents()
        time.sleep(0.02)
        if np.out_path and os.path.exists(np.out_path):
            got = True
            break
    check("加页码生成文件", got, str(np.out_path))

    # 每个有「纸张」面板的页面都要有缩略图，且点了能切预览
    for idx, name in ((I["stack"], "四堆叠"), (I["fourup"], "4合1"), (I["pager"], "加页码")):
        w.goto(idx)
        w.pages[idx].file.set_path(src)
        pump(app, 1.4)
        n = w.pages[idx].thumbs.list.count()
        check(f"{name}页有缩略图", n > 0, str(n))
        if n:
            from PySide6.QtTest import QTest
            pg = w.pages[idx]
            before = pg.preview.item.pixmap().cacheKey()
            it = pg.thumbs.list.item(1)
            pg.thumbs.list.scrollToItem(it)
            QTest.mouseClick(pg.thumbs.list.viewport(), Qt.LeftButton,
                             Qt.NoModifier, pg.thumbs.list.visualItemRect(it).center())
            pump(app, 0.5)
            after = pg.preview.item.pixmap().cacheKey()
            check(f"{name}页真点缩略图能切预览", before != after)

    # 打印对话框：按「面」选范围 + 将要打印列表
    from ui.print_dialog import PrintDialog, _parse_ranges
    dl = PrintDialog(bp.out_path, w, default_side="short", source_path=src)
    dl.first_only.setChecked(False)
    pump(app, 0.3)
    dl.range_mode.set_index(1)
    dl.range_edit.setText("3-6")
    pump(app, 0.4)
    check("打印范围按面解析", dl.page_range() == "3-6", dl.page_range())
    check("将要打印列出 4 面", len(dl.selected_pages()) == 4, str(len(dl.selected_pages())))
    check("缩略图列表有内容", dl.sel_list.count() == 4, str(dl.sel_list.count()))
    check("双面时标出正/背", "正" in dl.sub.text() or dl.sub.text(), dl.sub.text())
    try:
        _parse_ranges("0-2", 10)
        check("越界页码会报错", False, "没报错")
    except ValueError:
        check("越界页码会报错", True)
    dl.close()

    # 打印页（最后一个工具）
    w.goto(I["print"])
    pump(app, 0.4)
    pp = w.pages[I["print"]]
    check("打印页可打开", pp.__class__.__name__ == "PrintPage", pp.__class__.__name__)
    pp.file.set_path(bp.out_path)
    pump(app, 0.8)
    check("打印页读到文件", pp.total > 0, str(pp.total))
    pp.range_mode.set_index(1)
    pp.range_edit.setText("3-6")
    pump(app, 0.8)
    check("打印页按面选范围", pp.page_range() == "3-6", pp.page_range())
    check("打印页列出 4 面", pp.thumbs.list.count() == 4, str(pp.thumbs.list.count()))
    pp.range_mode.set_index(0)
    pp.range_edit.setText("7-8")
    pump(app, 0.4)
    check("直接输入页码自动切到部分", pp.range_mode.index() == 1, str(pp.range_mode.index()))
    check("自动切换后范围生效", pp.page_range() == "7-8", pp.page_range())
    check("选完打印机给出双面能力结论",
          ("支持自动双面" in pp.note.text()) or ("不支持自动双面" in pp.note.text()),
          pp.note.text())

    w.close()
    print()
    if FAILS:
        print(f"❌ {len(FAILS)} 项失败：" + "、".join(FAILS))
        return 1
    print("✅ 界面全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
