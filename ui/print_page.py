"""打印页：把「打印」做成一等公民——选任意 PDF（原稿或成品），预览要打的页，直接送印。"""
from __future__ import annotations

import os

import pymupdf as fitz
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QWidget)

from core import printpdf
from . import theme
from .pages import ToolPage
from .print_dialog import _parse_ranges
from .widgets import Card, ChipGroup, FileCard, Hint, SectionLabel, Stepper


class PrintPage(ToolPage):
    title = "打印"
    crumb = "书籍制作工具 / 输出"
    action_text = "开始打印"

    def build_left(self):
        self.file = FileCard()
        self.file.picked.connect(self.file_loaded)
        self.add_card(self.file)
        self.total = 0

        pr = Card()
        pr.lay.addWidget(SectionLabel("打印机"))
        self.printer = QComboBox()
        self.printer.setFixedHeight(32)
        self._fill_printers()
        self.printer.currentIndexChanged.connect(lambda _=0: self._side_changed())
        pr.lay.addWidget(self.printer)
        btn = QPushButton("重新读取打印机")
        btn.clicked.connect(self._fill_printers)
        pr.lay.addWidget(btn)
        self.note = Hint("")
        self.note.setWordWrap(True)
        pr.lay.addWidget(self.note)
        self.add_card(pr)

        out = Card()
        out.lay.addWidget(SectionLabel("份数与纸张"))
        self.copies = Stepper(1, 1, 50, 1, "份")
        self.add_row(out.lay, "份数", self.copies)
        self.paper = QComboBox()
        self.paper.addItems(["A4", "A3", "A5"])
        self.paper.setFixedWidth(132)
        self.add_row(out.lay, "纸张", self.paper)
        self.copies.valueChanged.connect(lambda _=0: self._refresh())
        self.paper.currentIndexChanged.connect(lambda _=0: self._refresh())
        self.add_card(out)

        side = Card()
        side.lay.addWidget(SectionLabel("单双面"))
        self.side = ChipGroup(["单面", "双面"])
        self.side.changed.connect(lambda _=0: self._side_changed())
        side.lay.addWidget(self.side)
        self.flip = ChipGroup(["短边（上下翻）", "长边（左右翻）"])
        self.flip.changed.connect(lambda _=0: self._refresh())
        self.add_row(side.lay, "翻面方向", self.flip)
        self.add_card(side)

        rng = Card()
        rng.lay.addWidget(SectionLabel("打印范围"))
        self.range_mode = ChipGroup(["全部", "部分"])
        self.range_mode.changed.connect(lambda _=0: self._range_changed())
        rng.lay.addWidget(self.range_mode)
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("按面填，例如 5-10,12")
        self.range_edit.textChanged.connect(self._range_typed)
        rng.lay.addWidget(self.range_edit)
        self.range_hint = Hint("")
        self.range_hint.setWordWrap(True)
        rng.lay.addWidget(self.range_hint)
        self.add_card(rng)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh_preview)
        self._side_changed()

    def setting_widgets(self):
        return {"份数": self.copies, "纸张": self.paper,
                "单双面": self.side, "翻面": self.flip, "范围": self.range_mode}

    # ---------- 打印机 ----------
    def _fill_printers(self):
        cur = self.printer.currentText()
        self.printer.blockSignals(True)
        self.printer.clear()
        names = printpdf.printers()
        default = printpdf.default_printer()
        self.printer.addItems(names or ["（没找到打印机）"])
        if cur and cur in names:
            self.printer.setCurrentText(cur)
        elif default in names:
            self.printer.setCurrentText(default)
        self.printer.blockSignals(False)
        if hasattr(self, "side"):
            self._side_changed()

    def _duplex(self) -> bool:
        return self.side.index() == 1

    def _side_changed(self):
        self.flip.setEnabled(self._duplex())
        name = self.printer.currentText()
        ok = printpdf.supports_duplex(name) if name and not name.startswith("（") else False
        if ok:
            self.note.setText("✓ 这台打印机支持自动双面，选双面时由打印机自己翻面。")
            self.note.setStyleSheet("color:#2E7D32;font-size:11px;")
        else:
            self.note.setText("✕ 这台打印机不支持自动双面；选双面会分两遍打，"
                              "中间提示你按方向翻纸。")
            self.note.setStyleSheet(f"color:{theme.RED};font-size:11px;")
        self._refresh()

    # ---------- 文件 ----------
    def file_loaded(self, path):
        try:
            with fitz.open(path) as d:
                self.total = len(d)
                r = d[0].rect
                landscape = r.width > r.height
        except Exception:
            self.total = 0
            landscape = False
        # 横向 A4 基本就是小册子成品，默认双面短边；竖向按普通文档单面
        self.side.set_index(1 if landscape else 0)
        self.flip.set_index(0 if landscape else 1)
        self._side_changed()
        self.range_edit.setPlaceholderText(
            f"按面填，例如 5-10,12（共 {self.total} 面）")
        self._refresh()

    # ---------- 范围 ----------
    def _range_changed(self):
        if getattr(self, "_syncing", False):
            return
        if self.range_mode.index() == 1 and not self.range_edit.text().strip():
            self.range_edit.setFocus()
        self._refresh()

    def _range_typed(self, text: str):
        """在「全部」状态下直接输入页码 → 自动切到「部分」。"""
        if getattr(self, "_syncing", False):
            return
        want_part = bool(text.strip())
        if want_part != (self.range_mode.index() == 1):
            self._syncing = True
            try:
                self.range_mode.set_index(1 if want_part else 0)
            finally:
                self._syncing = False
        self._refresh()

    def selected_pages(self) -> list:
        if not self.total:
            return []
        if self.range_mode.index() == 0:
            return list(range(1, self.total + 1))
        try:
            groups = _parse_ranges(self.range_edit.text(), self.total)
        except ValueError:
            return []
        pages = []
        for a, b in groups:
            pages.extend(range(a, b + 1))
        return pages

    def page_range(self) -> str:
        if self.range_mode.index() == 0:
            return ""
        try:
            groups = _parse_ranges(self.range_edit.text(), self.total)
        except ValueError:
            return ""
        return ",".join(f"{a}" if a == b else f"{a}-{b}" for a, b in groups)

    def _refresh(self):
        pages = self.selected_pages()
        if not self.file.path or not pages:
            self.range_hint.setText("选一个 PDF，再填要打的页")
            return
        a, b = pages[0], pages[-1]
        span = f"第 {a} 面" if a == b else f"第 {a}–{b} 面"
        extra = f"，共 {len(pages)} 面"
        if self._duplex():
            s1, s2 = (a + 1) // 2, (b + 1) // 2
            sheets = f"第 {s1} 张纸" if s1 == s2 else f"第 {s1}–{s2} 张纸"
            self.range_hint.setText(f"{span}{extra} → {sheets}")
        else:
            self.range_hint.setText(f"{span}{extra}")
        self._timer.start(200)

    # ---------- 预览 ----------
    def refresh_preview(self):
        if not self.is_active() or not self.file.path:
            return
        pages = self.selected_pages()
        if not pages:
            self.preview_caption.setText("范围没填对，右侧红字会提示" if self.range_mode.index() else "")
            return
        p = pages[0]
        try:
            self.preview.show_pdf(self.file.path, p - 1)
        except Exception as e:
            self.status(f"预览失败：{e}")
            return
        self._last_preview = self.file.path
        try:
            self.thumbs.load_pages(self.file.path, pages[:24], total=self.total)
        except Exception:
            pass
        pos = ""
        if self._duplex():
            pos = f" · 第 {(p + 1) // 2} 张纸 {'正面' if p % 2 else '背面'}"
        self.preview_caption.setText(f"第 {p} 面{pos}　（将要打印 {len(pages)} 面）")

    def _on_thumb(self, i: int):
        """打印页的缩略图只列了选中的几面，序号要映射回真实面号。"""
        pages = self.selected_pages()
        if not pages or i >= len(pages):
            return
        p = pages[i]
        try:
            self.preview.show_pdf(self.file.path, p - 1)
        except Exception:
            return
        pos = f" · 第 {(p + 1) // 2} 张纸 {'正面' if p % 2 else '背面'}" if self._duplex() else ""
        self.preview_caption.setText(f"第 {p} 面{pos}")

    # ---------- 从别的工具页带文件过来 ----------
    def load_target(self, path: str):
        """带着拼好的文件跳过来：沿用上次的打印选项，只换文件。"""
        self.file.set_path(path, emit=False)
        self._last_preview = path
        landscape = False
        try:
            with fitz.open(path) as d:
                self.total = len(d)
                landscape = d[0].rect.width > d[0].rect.height
        except Exception:
            self.total = 0
        self.range_edit.setPlaceholderText(
            f"按面填，例如 5-10,12（共 {self.total} 面）")
        # 拼好的小册子是横向的 → 双面短边；普通文档 → 单面
        self.side.set_index(1 if landscape else 0)
        self.flip.set_index(0 if landscape else 1)
        self._side_changed()

    # ---------- 执行 ----------
    def run(self):
        if not self.file.path:
            return self.status("先选一个 PDF")
        if not self.total:
            return self.status("这个文件读不出来")
        if self.range_mode.index() == 1:
            try:
                _parse_ranges(self.range_edit.text(), self.total)
            except ValueError as e:
                return self.status(str(e))
        if not printpdf.available():
            return self.main.fail("打印组件缺失：请重新解压整个文件夹（不要只拷 exe）")

        # 大任务确认：一键打整本 800 页太危险，超过 30 页先问一句
        plan = self.total if self.range_mode.index() == 0 else len(
            _parse_ranges(self.range_edit.text(), self.total))
        plan *= int(self.copies.value())
        if plan > 30:
            if QMessageBox.question(
                    self, "确认送印",
                    f"这次要送印 {plan} 页。\n\n"
                    "整本送印会消耗同样多的纸和墨，确认要开始吗？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No) != QMessageBox.Yes:
                return self.status("已取消，什么都没有打印")
        args = dict(
            printer="" if self.printer.currentText() == printpdf.default_printer()
            else self.printer.currentText(),
            copies=int(self.copies.value()),
            duplex=("short" if self.flip.index() == 0 else "long") if self._duplex() else "none",
            paper=self.paper.currentText(),
            first_page_only=False,
            pages=self.page_range(),
            flip="short" if self.flip.index() == 0 else "long",
        )
        self.main.start_print(self.file.path, args)
