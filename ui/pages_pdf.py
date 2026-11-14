"""PDF 处理三页：合并 / 分拆 / 加页码。都不做拼版，只动页序和页数。"""
from __future__ import annotations

import os

import pymupdf as fitz

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton)
from core import pdfops
from . import theme
from .page_base import ToolPage, TMP
from .widgets import (Card, ChipGroup, FileCard, Hint, OutlinePanel, SectionLabel, Stepper, submit)


class MergePage(ToolPage):
    title = "PDF 合并"
    crumb = "书籍制作工具 / 文件"
    action_text = "开始合并"

    def build_left(self):
        self.files: list[str] = []
        card = Card()
        card.lay.addWidget(SectionLabel("文件顺序"))
        self.list = QListWidget()
        self.list.setMinimumHeight(240)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setDragEnabled(True)
        self.list.setAcceptDrops(True)
        self.list.setDropIndicatorShown(True)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setCursor(Qt.OpenHandCursor)
        self.list.setDragEnabled(True)
        self.list.setToolTip("按住任意一行上下拖动即可排序")
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        self.list.setStyleSheet(
            f"QListWidget{{background:#FCFAF5;border:1px solid {theme.LINE};border-radius:6px;"
            f"font-size:10.5pt;color:{theme.INK};outline:0;}}"
            f"QListWidget::item{{padding:7px 8px;border-bottom:1px solid {theme.LINE2};}}"
            f"QListWidget::item:selected{{background:{theme.RED_SOFT};color:{theme.INK};}}")
        card.lay.addWidget(self.list)
        row = QHBoxLayout()
        self.small_btns = []
        for text, fn in (("添加", self.add_files), ("上移", lambda: self.move(-1)),
                         ("下移", lambda: self.move(1)), ("移除", self.remove)):
            b = QPushButton(text)
            if text == "添加":
                b.setObjectName("AddBtn")
            b.clicked.connect(fn)
            b.setEnabled(text == "添加")
            row.addWidget(b)
            self.small_btns.append((text, b))
        card.lay.addLayout(row)
        card.lay.addWidget(Hint("拖动任意一行上下排序；也可以用下面的按钮微调。合并顺序 = 列表顺序"))
        self.add_card(card)

        self.stats_card(("文件", "总页数", "预计"))
        self.set_stats(0, "—", "—")

        self.thumbs.setParent(None)
        self.outline = OutlinePanel("合并后的顺序")
        self.outline.currentChanged.connect(self._show_item)
        self.right = self.outline
        self.layout().addWidget(self.outline)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择 PDF", os.path.expanduser("~"),
                                                "PDF (*.pdf)")
        for p in paths:
            if p not in self.files:
                self.files.append(p)
        self._refresh_list()

    def _refresh_list(self):
        self.list.clear()
        total = 0
        for i, p in enumerate(self.files):
            try:
                with fitz.open(p) as d:
                    n = len(d)
            except Exception:
                n = 0
            total += n
            it = QListWidgetItem(f"≡   {i+1}. {os.path.basename(p)}   ·  {n} 页", self.list)
            it.setData(Qt.UserRole, p)
            it.setData(Qt.UserRole + 1, n)
            it.setToolTip(p)
        self.set_stats(len(self.files), total or "—", f"{total} 页")
        for text, b in self.small_btns:
            if text != "添加":
                b.setEnabled(bool(self.files))
        if not self.files:
            self.preview_caption.setText("把 PDF 拖进来，或点左侧「添加」")
        self._rebuild_outline()
        try:
            self.main.refresh_action_state()
        except Exception:
            pass
        if self.files:
            self.preview.show_pdf(self.files[0], 0)
            self.preview_caption.setText("第一个文件的首面")
        self.thumbs.list.clear()

    def _on_rows_moved(self, *args):
        """拖动结束后，按控件里的新顺序回写文件列表。"""
        new = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            path = it.data(Qt.UserRole)
            if path:
                new.append(path)
        if new and new != self.files:
            self.files = new
        total = 0
        for i in range(self.list.count()):
            it = self.list.item(i)
            path = it.data(Qt.UserRole)
            n = it.data(Qt.UserRole + 1) or 0
            total += n
            it.setText(f"≡   {i+1}. {os.path.basename(path)}   ·  {n} 页")
        self.set_stats(len(self.files), total or "—", f"{total} 页")
        try:
            self.main.refresh_action_state()
        except Exception:
            pass

    def _rebuild_outline(self):
        items, cur = [], 1
        for p in self.files:
            try:
                with fitz.open(p) as d:
                    n = len(d)
            except Exception:
                n = 0
            if n:
                items.append((p, 0, os.path.basename(p)[:18],
                              f"合并后第 {cur}–{cur + n - 1} 页"))
            cur += n
        self.outline.set_items(items)
        if items:
            self.outline.list.setCurrentRow(0)
            self._show_item(0)

    def _show_item(self, i: int):
        cur = self.outline.current()
        if not cur:
            return
        path, pno = cur
        self.preview.show_pdf(path, pno)
        it = self.outline.list.currentItem()
        sub = it.text().split("\n")[-1] if it else ""
        self.preview_caption.setText(
            f"第 {i+1} / {self.outline.list.count()} 个文件 · {sub}")
        self.main.set_status(sub)

    def move(self, d):
        i = self.list.currentRow()
        j = i + d
        if 0 <= i < len(self.files) and 0 <= j < len(self.files):
            self.files[i], self.files[j] = self.files[j], self.files[i]
            self._refresh_list()
            self.list.setCurrentRow(j)

    def remove(self):
        i = self.list.currentRow()
        if 0 <= i < len(self.files):
            self.files.pop(i)
            self._refresh_list()

    def run(self):
        if not self.files:
            return self.status("先添加 PDF")
        out, _ = QFileDialog.getSaveFileName(self, "保存合并结果", "合并结果.pdf", "PDF (*.pdf)")
        if not out:
            return
        self.main.busy(True)
        files = list(self.files)
        self._job = submit(lambda cb: dict(pdfops.merge_pdfs(files, out), path=out),
               on_progress=lambda a, b: self.main.progress(a, b),
               on_done=lambda st: self._done(st), on_fail=self.main.fail)

    def _done(self, st):
        self.main.busy(False)
        self.out_path = st["path"]
        self.preview.show_pdf(self.out_path, 0)
        self.thumbs.load(self.out_path)
        self.main.set_status(f"合并完成：{st['pages']} 页")
        self.main.offer_open(self.out_path)


# ------------------------------------------------------------------ 分拆


class SplitPage(ToolPage):
    title = "PDF 分拆"
    crumb = "书籍制作工具 / 文件"
    action_text = "开始分拆"

    def build_left(self):
        self.file = FileCard()
        self.file.picked.connect(self.file_loaded)
        self.add_card(self.file)

        c = Card()
        c.lay.addWidget(SectionLabel("怎么分"))
        self.mode = ChipGroup(["按页数", "按份数", "页码范围"])
        self.mode.changed.connect(self._mode_changed)
        c.lay.addWidget(self.mode)

        self.n = Stepper(20, 1, 9999, 1, "页")
        self.n.valueChanged.connect(self._n_changed)
        self.row_n = self.add_row(c.lay, "每份页数", self.n)
        self.n_label = self.row_n.findChild(QLabel)

        from PySide6.QtWidgets import QLineEdit
        self.ranges = QLineEdit()
        self.ranges.setPlaceholderText("例如 1-20, 21-50, 51-")
        self.ranges.textChanged.connect(lambda _=0: self._recalc())
        self.row_ranges = self.add_row(c.lay, "页码区间", self.ranges)
        self.row_ranges.setVisible(False)

        self.mode_hint = Hint("每 20 页存成一个文件")
        c.lay.addWidget(self.mode_hint)
        self.add_card(c)

        self.stats_card(("份数", "总页数", "每份约"))
        self.set_stats("—", "—", "—")

        self.thumbs.setParent(None)
        self.outline = OutlinePanel("将生成的份")
        self.outline.currentChanged.connect(self._show_part)
        self.right = self.outline
        self.layout().addWidget(self.outline)

    def _n_changed(self, _v=0):
        i = self.mode.index()
        if i == 0:
            self.mode_hint.setText(f"每 {int(self.n.value())} 页存成一个文件")
        elif i == 1:
            self.mode_hint.setText(f"平均分成 {int(self.n.value())} 份")
        self._recalc()

    def _mode_changed(self, i=0):
        if not hasattr(self, "_n_memo"):
            self._n_memo = {0: 20, 1: 2}
            self._last_mode = 0
        if self._last_mode in (0, 1):
            self._n_memo[self._last_mode] = self.n.value()

        self.row_n.setVisible(i in (0, 1))
        self.row_ranges.setVisible(i == 2)
        if i == 0:                       # 按页数：每 N 页一个文件
            self.n_label.setText("每份页数")
            self.n.set_range(1, 9999, 1)
            self.n.set_suffix("页")
            self.n.set_value(self._n_memo.get(0, 20))
            self.mode_hint.setText(f"每 {int(self.n.value())} 页存成一个文件")
        elif i == 1:                     # 按份数：均分成 N 份
            self.n_label.setText("分成几份")
            self.n.set_range(1, 999, 1)
            self.n.set_suffix("份")
            self.n.set_value(self._n_memo.get(1, 2))
            self.mode_hint.setText(f"平均分成 {int(self.n.value())} 份")
        else:
            self.mode_hint.setText("自定义页码：「起始-结束」，最后一份可留空（如 51-）")
        self._last_mode = i
        self._recalc()

    def file_loaded(self, path):
        self._recalc()
        if path:
            self.preview.show_pdf(path, 0)
            self.preview_caption.setText("原稿第 1 页")

    def _total(self):
        if not self.file.path:
            return 0
        try:
            with fitz.open(self.file.path) as d:
                return len(d)
        except Exception:
            return 0

    def _plan(self):
        """返回 [(start, end)]，0 基、闭区间。"""
        total = self._total()
        if total <= 0:
            return []
        mode = self.mode.index()
        if mode == 0:
            step = max(1, int(self.n.value()))
            return [(i, min(i + step - 1, total - 1)) for i in range(0, total, step)]
        if mode == 1:
            parts = max(1, int(self.n.value()))
            parts = min(parts, total)
            base, rem = divmod(total, parts)
            out, cur = [], 0
            for k in range(parts):
                size = base + (1 if k < rem else 0)
                if size:
                    out.append((cur, cur + size - 1))
                    cur += size
            return out
        plan = []
        for chunk in self.ranges.text().replace("，", ",").split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "-" in chunk:
                a, b = chunk.split("-", 1)
                try:
                    start = int(a) if a.strip() else 1
                    end = int(b) if b.strip() else total
                except ValueError:
                    continue
            else:
                try:
                    start = end = int(chunk)
                except ValueError:
                    continue
            start = max(1, min(start, total))
            end = max(start, min(end, total))
            plan.append((start - 1, end - 1))
        return plan

    def _recalc(self):
        total = self._total()
        plan = self._plan()
        if total:
            sizes = [b - a + 1 for a, b in plan] if plan else []
            if sizes and max(sizes) - min(sizes) <= 1:
                third = f"约 {round(total / len(sizes))} 页"
            elif sizes and len(set(sizes)) == 1:
                third = f"{sizes[0]} 页"
            else:
                third = "不等"
            self.set_stats(len(plan), total, third)
            if self.mode.index() != 2:
                self.stat_hint.setText(f"将生成 {len(plan)} 个文件")
            if plan:
                items = [(self.file.path, a, f"第 {k+1} 部分",
                          f"p{a+1}–{b+1} · {b - a + 1} 页")
                         for k, (a, b) in enumerate(plan)]
                self.outline.set_items(items)
                self.outline.list.setCurrentRow(0)
                self._show_part(0)
        else:
            self.set_stats("—", "—", "—")

    def _show_part(self, i: int):
        cur = self.outline.current()
        if not cur:
            return
        path, pno = cur
        self.preview.show_pdf(path, pno)
        n = self.outline.list.count()
        self.preview_caption.setText(f"第 {i+1} / {n} 部分的首面 · 点右侧切换")

    def run(self):
        if not self.file.path:
            return self.status("先选一个 PDF")
        plan = self._plan()
        if not plan:
            return self.main.fail("没有可分的页码范围")
        src = self.file.path
        base = os.path.splitext(src)[0]
        self.main.busy(True)
        self.status("正在分拆…")

        def job(cb):
            out = []
            doc = fitz.open(src)
            try:
                for k, (a, b) in enumerate(plan):
                    part = fitz.open()
                    part.insert_pdf(doc, from_page=a, to_page=b)
                    path = self.main.out_path_for(src, f"-第{k+1}部分-p{a+1}-{b+1}.pdf")
                    part.save(path, garbage=1, deflate=True)
                    part.close()
                    out.append(path)
                    if cb:
                        cb(k + 1, len(plan))
            finally:
                doc.close()
            return {"files": out, "count": len(out), "path": out[0] if out else ""}

        self._job = submit(job, on_progress=self.main.progress,
                           on_done=self._done, on_fail=self.main.fail)

    def _done(self, st):
        self.main.busy(False)
        self.out_path = st["path"]
        self.set_stats(st["count"], "—", "—")
        self.main.set_status(f"已生成 {st['count']} 个文件，存在原文件旁边")
        self.main.offer_open(st["path"])


# ------------------------------------------------------------------ 加页码


class NumberPage(ToolPage):
    title = "加页码"
    crumb = "书籍制作工具 / 页面"
    action_text = "生成带页码的 PDF"

    def build_left(self):
        self.file = FileCard()
        self.file.picked.connect(self.file_loaded)
        self.add_card(self.file)

        c = Card()
        c.lay.addWidget(SectionLabel("位置"))
        self.pos = ChipGroup(["底部居中", "底部外侧", "顶部外侧"])
        self.pos.changed.connect(lambda _=0: self._changed())
        c.lay.addWidget(self.pos)
        self.mirror = QCheckBox("奇偶页镜像（右装订用）")
        self.mirror.stateChanged.connect(lambda _=0: self._changed())
        c.lay.addWidget(self.mirror)
        self.add_card(c)

        f = Card()
        f.lay.addWidget(SectionLabel("格式"))
        self.fmt = ChipGroup(["1", "第 1 页", "1 / 总页数", "— 1 —"])
        self.fmt.changed.connect(lambda _=0: self._changed())
        f.lay.addWidget(self.fmt)
        self.start_page = Stepper(1, 1, 9999, 1, "页")
        self.start_page.valueChanged.connect(lambda _=0: self._changed())
        self.add_row(f.lay, "起始页码", self.start_page)
        self.skip = Stepper(0, 0, 999, 1, "页")
        self.skip.valueChanged.connect(lambda _=0: self._changed())
        self.add_row(f.lay, "跳过前几页", self.skip)
        f.lay.addWidget(Hint("封面不编号就把「跳过前几页」设成 1"))
        self.add_card(f)

        d = Card()
        d.lay.addWidget(SectionLabel("字号与边距"))
        self.size = Stepper(10, 5, 40, 1, "pt")
        self.size.valueChanged.connect(lambda _=0: self._changed())
        self.add_row(d.lay, "字号", self.size)
        self.margin = Stepper(12, 2, 60, 1, "mm")
        self.margin.valueChanged.connect(lambda _=0: self._changed())
        self.add_row(d.lay, "距边", self.margin)
        self.add_card(d)

        self.stats_card(("总页数", "编号页", "起始"))
        self.set_stats("—", "—", "—")

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh_preview)

    def _changed(self):
        self._timer.start(350)

    def _fmt_text(self):
        return ["{n}", "第 {n} 页", "{n} / {total}", "— {n} —"][self.fmt.index()]

    def refresh_preview(self):
        if not self.is_active() or not self.file.path:
            return
        self.note_preview()
        if self.btn_src.isChecked():
            return
        try:
            out = os.path.join(TMP, "preview_num.pdf")
            with fitz.open(self.file.path) as _d:
                total = len(_d)
            # 预览只编号前 6 页，200 页稿子切页不再卡 1.8 秒
            pdfops.add_page_numbers_preview(
                self.file.path, out, limit=6, start=int(self.start_page.value()),
                fmt=self._fmt_text(),
                pos=["bottom-center", "bottom-outer", "top-outer"][self.pos.index()],
                font_size=self.size.value(), margin_mm=self.margin.value(),
                mirror=self.mirror.isChecked(), skip=int(self.skip.value()))
            show = 1 if total > 1 else 0
            self._last_preview = out
            self._last_fold = False
            self._thumb_unit = "页"
            self.preview.show_pdf(out, show)
            self.thumbs.load(out, limit=12, dpi=20)
            self.set_stats(total, max(0, total - int(self.skip.value())),
                           int(self.start_page.value()))
            self.preview_caption.setText(
                f"第 {show + 1} 页（页码 {int(self.start_page.value()) + max(0, show - int(self.skip.value()))}）")
        except Exception as e:
            self.status(f"预览失败：{e}")

    def file_loaded(self, path):
        try:
            with fitz.open(path) as d:
                self.enable_source_nav(len(d))
        except Exception:
            pass
        self.refresh_preview()

    def setting_widgets(self):
        return {"位置": self.pos, "格式": self.fmt, "起始": self.start_page,
                "跳过": self.skip, "字号": self.size, "距边": self.margin,
                "镜像": self.mirror}

    def run(self):
        if not self.file.path:
            return self.status("先选一个 PDF")
        out = self.main.out_path_for(self.file.path, "-加页码.pdf")
        self.main.busy(True)
        args = dict(start=int(self.start_page.value()), fmt=self._fmt_text(),
                    pos=["bottom-center", "bottom-outer", "top-outer"][self.pos.index()],
                    font_size=self.size.value(), margin_mm=self.margin.value(),
                    mirror=self.mirror.isChecked(), skip=int(self.skip.value()))
        self._job = submit(lambda cb: dict(pdfops.add_page_numbers(
            self.file.path, out, progress=cb, **args), path=out),
            on_progress=self.main.progress,
            on_done=self._done, on_fail=self.main.fail)

    def _done(self, st):
        self.main.busy(False)
        self.out_path = st["path"]
        self.preview.show_pdf(self.out_path, 1 if st["pages"] > 1 else 0)
        self.thumbs.load(self.out_path)
        self.set_stats(st["pages"], st["numbered"], int(self.start_page.value()))
        self.main.set_status(f"完成：{st['numbered']} 页加了页码")
        self.main.offer_open(self.out_path)
