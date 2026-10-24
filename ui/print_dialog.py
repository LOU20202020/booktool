"""打印对话框：按「面」选范围、先看要打哪些页，再送印。"""
from __future__ import annotations

import os
import re

import pymupdf as fitz
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from core import printpdf
from . import theme
from .widgets import ChipGroup, Stepper


def _parse_ranges(text: str, total: int) -> list[tuple[int, int]]:
    """'5-10,12' → [(5,10),(12,12)]；越界或格式错抛 ValueError。"""
    out: list[tuple[int, int]] = []
    for part in re.split(r"[,，\s]+", text.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:\s*[-–~]\s*(\d+))?", part)
        if not m:
            raise ValueError(f"「{part}」看不懂，写成 5-10 或 12 这样")
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        if a > b:
            a, b = b, a
        if a < 1 or b > total:
            raise ValueError(f"「{part}」超出范围（共 {total} 面）")
        out.append((a, b))
    if not out:
        raise ValueError("请输入要打印的面，比如 5-10,12")
    return out


class PrintDialog(QDialog):
    MAX_THUMBS = 16

    def __init__(self, pdf_path: str, parent=None, default_side: str = "short",
                 source_path: str = ""):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.source_path = source_path
        self.setWindowTitle("打印")
        self.setMinimumWidth(660)
        self.setStyleSheet(f"""
            QDialog {{ background:{theme.SURFACE}; }}
            QLabel {{ color:{theme.INK}; font-size:13px; }}
            QComboBox {{ background:#FFFFFF; border:1px solid {theme.LINE};
                        border-radius:6px; padding:6px 8px; min-height:22px; }}
            QCheckBox {{ color:{theme.INK}; font-size:13px; }}
            QListWidget {{ background:#FBFAF6; border:1px solid {theme.LINE};
                          border-radius:8px; }}
            QPushButton#Go {{ background:{theme.RED}; color:#FBF7F0; border:0;
                             border-radius:7px; padding:9px 28px; font-weight:600; }}
            QPushButton#Cancel {{ background:#FFFFFF; color:{theme.INK};
                                 border:1px solid {theme.LINE}; border-radius:7px;
                                 padding:9px 22px; }}
            QPushButton#Cancel:hover {{ border-color:{theme.RED}; color:{theme.RED}; }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(9)

        title = QLabel("打印")
        title.setStyleSheet(f"font-family:'{theme.FONT_HEAD}';font-size:20px;"
                            f"letter-spacing:2px;")
        lay.addWidget(title)

        top = QHBoxLayout()
        top.setSpacing(14)
        self.thumb = QLabel()
        self.thumb.setFixedSize(132, 94)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet(f"background:#FFFFFF;border:1px solid {theme.LINE};"
                                 "border-radius:6px;")
        top.addWidget(self.thumb)
        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        self.summary = QLabel("")
        self.summary.setStyleSheet(f"color:{theme.INK};font-size:13px;")
        self.summary.setWordWrap(True)
        info_col.addWidget(self.summary)
        self.sub = QLabel("")
        self.sub.setStyleSheet("color:#7A7365;font-size:12px;")
        self.sub.setWordWrap(True)
        info_col.addWidget(self.sub)
        info_col.addStretch(1)
        top.addLayout(info_col, 1)
        lay.addLayout(top)

        row0 = QHBoxLayout()
        lab0 = QLabel("打印内容")
        lab0.setFixedWidth(64)
        row0.addWidget(lab0)
        self.what = QComboBox()
        self.what.addItem("成品（已拼版）")
        if source_path:
            self.what.addItem("原稿（未拼版）")
        self.what.currentIndexChanged.connect(lambda _=0: self._reload())
        row0.addWidget(self.what, 1)
        lay.addLayout(row0)

        row = QHBoxLayout()
        lab = QLabel("打印机")
        lab.setFixedWidth(64)
        row.addWidget(lab)
        self.printer = QComboBox()
        default = printpdf.default_printer()
        names = printpdf.printers()
        if default and default not in names:
            names.insert(0, default)
        self.printer.addItems(names or ["（没找到打印机）"])
        if default in names:
            self.printer.setCurrentText(default)
        self.printer.currentIndexChanged.connect(lambda _=0: self._sync_side())
        row.addWidget(self.printer, 1)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        lab2 = QLabel("份数")
        lab2.setFixedWidth(64)
        row2.addWidget(lab2)
        self.copies = Stepper(1, 1, 50, 1, "份")
        row2.addWidget(self.copies)
        row2.addSpacing(14)
        row2.addWidget(QLabel("纸张"))
        self.paper = QComboBox()
        self.paper.addItems(["A4", "A3", "A5"])
        self.paper.setFixedWidth(96)
        row2.addWidget(self.paper)
        row2.addStretch(1)
        lay.addLayout(row2)

        lay.addWidget(QLabel("单双面"))
        self.side = ChipGroup(["单面", "双面"])
        self.side.set_index(0 if default_side == "none" else 1)
        self.side.changed.connect(lambda _=0: self._sync_side())
        lay.addWidget(self.side)

        self.flip_row = QWidget()
        fl = QHBoxLayout(self.flip_row)
        fl.setContentsMargins(0, 2, 0, 2)
        lab3 = QLabel("翻面方向")
        lab3.setFixedWidth(64)
        fl.addWidget(lab3)
        self.flip = ChipGroup(["短边（上下翻）", "长边（左右翻）"])
        self.flip.set_index(0 if default_side != "long" else 1)
        self.flip.changed.connect(lambda _=0: self._update_summary())
        fl.addWidget(self.flip, 1)
        lay.addWidget(self.flip_row)

        self.duplex_note = QLabel("")
        self.duplex_note.setWordWrap(True)
        self.duplex_note.setStyleSheet("color:#7A7365;font-size:12px;")
        lay.addWidget(self.duplex_note)

        # 按「面」选范围
        self.range_row = QWidget()
        rr = QHBoxLayout(self.range_row)
        rr.setContentsMargins(0, 2, 0, 2)
        self.range_label = QLabel("打印面数")
        self.range_label.setFixedWidth(64)
        rr.addWidget(self.range_label)
        self.range_mode = ChipGroup(["全部", "部分"])
        self.range_mode.set_index(0)
        self.range_mode.changed.connect(lambda _=0: self._sync_range())
        rr.addWidget(self.range_mode)
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("例如 5-10,12")
        self.range_edit.setMinimumWidth(170)
        self.range_edit.setStyleSheet(
            f"QLineEdit{{background:#FFFFFF;border:1px solid {theme.LINE};"
            f"border-radius:6px;padding:5px 8px;color:{theme.INK};}}"
            f"QLineEdit:disabled{{background:#F7F4EE;color:#A39A8C;}}")
        self.range_edit.textChanged.connect(lambda _=0: self._schedule_preview())
        rr.addWidget(self.range_edit, 1)
        lay.addWidget(self.range_row)

        # 到底打哪些页
        self.sel_title = QLabel("将要打印")
        self.sel_title.setStyleSheet(f"color:{theme.INK2};font-size:12px;")
        lay.addWidget(self.sel_title)
        self.sel_list = QListWidget()
        self.sel_list.setViewMode(QListWidget.IconMode)
        self.sel_list.setFlow(QListWidget.LeftToRight)
        self.sel_list.setWrapping(True)
        self.sel_list.setResizeMode(QListWidget.Adjust)
        self.sel_list.setMovement(QListWidget.Static)
        self.sel_list.setIconSize(QSize(56, 76))
        self.sel_list.setGridSize(QSize(68, 104))
        self.sel_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.sel_list.setFixedHeight(124)
        self.sel_list.setStyleSheet("QListWidget{background:#FBFAF6;border:1px solid "
                                    f"{theme.LINE};border-radius:8px;font-size:9px;"
                                    "padding:4px;}")
        lay.addWidget(self.sel_list)

        self.first_only = QCheckBox("只印 1 张样张（确认方向后再整本打）")
        self.first_only.setChecked(True)
        self.first_only.stateChanged.connect(lambda _=0: self._sync_range())
        lay.addWidget(self.first_only)

        self.source_pages = self._count(source_path) if source_path else 0
        self.result_pages = self._count(pdf_path)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._render_selection)

        btns = QHBoxLayout()
        self.err = QLabel("")
        self.err.setStyleSheet(f"color:{theme.RED};font-size:12px;")
        btns.addWidget(self.err, 1)
        cancel = QPushButton("取消")
        cancel.setObjectName("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        go = QPushButton("打印")
        go.setObjectName("Go")
        go.clicked.connect(self._go)
        btns.addWidget(go)
        lay.addLayout(btns)

        self._reload()

    # ---------- 基础 ----------
    @staticmethod
    def _count(path: str) -> int:
        try:
            with fitz.open(path) as d:
                return len(d)
        except Exception:
            return 0

    def target(self) -> str:
        return self.source_path if (self.source_path and self.what.currentIndex() == 1) else self.pdf_path

    def pages_total(self) -> int:
        return self.source_pages if self.target() == self.source_path else self.result_pages

    def duplex(self) -> bool:
        return self.side.index() == 1

    def sheets(self) -> int:
        n = self.pages_total()
        return (n + 1) // 2 if self.duplex() else n

    # ---------- 联动 ----------
    def _reload(self):
        if self.what.currentIndex() == 1:
            self.side.set_index(0)
        self.range_edit.setPlaceholderText(f"例如 5-10,12（共 {self.pages_total()} 面）")
        self._sync_side()
        self._sync_range()

    def _sync_side(self):
        self.flip_row.setVisible(self.duplex())
        self.duplex_note.setVisible(self.duplex())
        if self.duplex():
            if printpdf.supports_duplex(self.printer.currentText()):
                self.duplex_note.setText("这台打印机支持自动双面，翻面由打印机自己完成。")
            else:
                self.duplex_note.setText("这台打印机不支持自动双面：会分两遍打，"
                                         "中间弹窗提示你按上面的方向翻纸。")
        self._update_summary()
        self._schedule_preview()

    def _sync_range(self):
        if getattr(self, "_syncing", False):     # set_index 会再发 changed，必须防重入
            return
        self._syncing = True
        try:
            if self.first_only.isChecked():
                self.range_mode.set_index(0)
                self.range_mode.setEnabled(False)
                self.range_edit.setEnabled(False)
            else:
                self.range_mode.setEnabled(True)
                self.range_edit.setEnabled(self.range_mode.index() == 1)
        finally:
            self._syncing = False
        self._schedule_preview()

    def _schedule_preview(self):
        self._update_summary()
        self._timer.start(180)

    # ---------- 范围 ----------
    def _groups(self) -> list[tuple[int, int]]:
        if self.range_mode.index() == 0:
            return [(1, self.pages_total())]
        return _parse_ranges(self.range_edit.text(), self.pages_total())

    def page_range(self) -> str:
        """给 SumatraPDF 的页码范围；'' 表示全部。"""
        if self.range_mode.index() == 0 or self.first_only.isChecked():
            return ""
        groups = _parse_ranges(self.range_edit.text(), self.pages_total())
        return ",".join(f"{a}" if a == b else f"{a}-{b}" for a, b in groups)

    def selected_pages(self) -> list[int]:
        pages: list[int] = []
        try:
            groups = self._groups()
        except ValueError:
            return []
        for a, b in groups:
            pages.extend(range(a, b + 1))
        if self.first_only.isChecked():
            return pages[:1]
        return pages

    # ---------- 显示 ----------
    def _update_summary(self):
        n = self.pages_total()
        mode = "双面·" + ("短边" if self.flip.index() == 0 else "长边") + "翻转" if self.duplex() else "单面"
        self.summary.setText(" · ".join([f"{n} 面", f"{self.sheets()} 张", mode,
                                         self.paper.currentText(),
                                         f"{int(self.copies.value())} 份"]))
        pages = self.selected_pages()
        if not pages:
            self.sub.setText("页码写法有误，下面红字会提示")
            return
        a, b = pages[0], pages[-1]
        span = f"第 {a} 面" if a == b else f"第 {a}–{b} 面"
        if len(pages) != b - a + 1:
            span += f"（含空档，共 {len(pages)} 面）"
        else:
            span += f"（共 {len(pages)} 面）"
        if self.duplex():
            s1, s2 = (pages[0] + 1) // 2, (pages[-1] + 1) // 2
            sheets = f"第 {s1} 张纸" if s1 == s2 else f"第 {s1}–{s2} 张纸"
            self.sub.setText(f"{span} → {sheets}；本页正背面按短边/长边翻转成对打印")
        else:
            self.sub.setText(span)

    def _render_selection(self):
        try:
            pages = self.selected_pages()
        except ValueError:
            pages = []
        self.sel_list.clear()
        if not pages:
            self.sel_title.setText("将要打印：—")
            return
        show = pages[:self.MAX_THUMBS]
        hidden = len(pages) - len(show)
        self.sel_title.setText(f"将要打印 {len(pages)} 面"
                               + (f"（下面示前 {len(show)} 面）" if hidden > 0 else ""))
        try:
            doc = fitz.open(self.target())
        except Exception:
            return
        try:
            for p in show:
                if p - 1 >= len(doc):
                    break
                pix = doc[p - 1].get_pixmap(dpi=16)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                             QImage.Format_RGB888).copy()
                it = QListWidgetItem()
                it.setIcon(QPixmap.fromImage(img))
                label = str(p)
                if self.duplex():
                    label += "\n正" if p % 2 else "\n背"
                it.setText(label)
                it.setToolTip(f"第 {p} 面")
                self.sel_list.addItem(it)
        finally:
            doc.close()
        self._update_thumb()

    def _update_thumb(self):
        try:
            with fitz.open(self.target()) as d:
                p = (self.selected_pages() or [1])[0]
                pix = d[max(0, min(p - 1, len(d) - 1))].get_pixmap(dpi=34)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                             QImage.Format_RGB888).copy()
            pm = QPixmap.fromImage(img).scaled(self.thumb.width() - 6,
                                               self.thumb.height() - 6,
                                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.thumb.setPixmap(pm)
        except Exception:
            self.thumb.setText("—")

    # ---------- 结果 ----------
    def _go(self):
        if not self.printer.currentText() or self.printer.currentText().startswith("（"):
            self.err.setText("没找到打印机")
            return
        try:
            self.page_range()
        except ValueError as e:
            self.err.setText(str(e))
            return
        self.err.setText("")
        self.accept()

    def result_args(self) -> dict:
        picked = self.printer.currentText()
        if picked == printpdf.default_printer():
            picked = ""
        return dict(
            printer=picked,
            copies=int(self.copies.value()),
            duplex="none" if not self.duplex()
            else ("short" if self.flip.index() == 0 else "long"),
            paper=self.paper.currentText(),
            first_page_only=self.first_only.isChecked(),
            pages=self.page_range(),
            flip="short" if self.flip.index() == 0 else "long",
            target=self.target(),
        )
