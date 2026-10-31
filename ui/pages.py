"""六个功能页。布局与设计稿一致：左参数 / 中预览 / 右缩略图。"""
from __future__ import annotations

import logging
import math
import os
import tempfile

import pymupdf as fitz
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox,
                               QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton, QScrollArea,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from core import cover as cover_core
from core import pdfops
from . import icons, theme


def margin_note(st: dict, want: float) -> str:
    """页面比例和格子比例对不上时，实际边距会比设定值大 —— 别让界面装没事。

    只有偏差超过 0.25mm 才提示，避免 0.1mm 的取整噪声。
    """
    m = (st or {}).get("margins_mm")
    if not m:
        return ""
    vals = (m.get("top", 0.0), m.get("bottom", 0.0), m.get("left", 0.0), m.get("right", 0.0))
    if max(abs(v - want) for v in vals) <= 0.25:
        return ""
    up = max(0.0, max(vals[0], vals[1]) - want)
    side = max(0.0, max(vals[2], vals[3]) - want)
    if up >= side:
        return (f" · 实际边距 上/下 {vals[0]:.1f}mm、左/右 {vals[2]:.1f}mm"
                f"（页面比例固定，套不进 {want:g}mm 的那一边会多一点）")
    return (f" · 实际边距 左/右 {vals[2]:.1f}mm、上/下 {vals[0]:.1f}mm"
            f"（页面比例固定，套不进 {want:g}mm 的那一边会多一点）")
from .widgets import (CANCEL, Card, ChipGroup, Collapsible, FileCard, Hint, ImagePicker,
                      OutlinePanel, PreviewView, SectionLabel, Stepper, ThumbPanel,
                      submit)

TMP = os.path.join(tempfile.gettempdir(), "booktool")


# ------------------------------------------------------------------ 基类
class ToolPage(QWidget):
    title = "工具"
    crumb = "书籍制作工具"
    action_text = "开始"
    secondary_text = ""

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.out_path = ""
        os.makedirs(TMP, exist_ok=True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 0)
        lay.setSpacing(18)

        # 左：参数
        self.left_body = QWidget()
        self.left_lay = QVBoxLayout(self.left_body)
        self.left_lay.setContentsMargins(0, 0, 8, 0)
        self.left_lay.setSpacing(12)
        self.left_lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.left_body)
        scroll.setFixedWidth(372)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(scroll)

        # 中：预览
        self.center = QFrame()
        self.center.setObjectName("Panel")
        cl = QVBoxLayout(self.center)
        cl.setContentsMargins(1, 1, 1, 1)
        cl.setSpacing(0)
        self.preview = PreviewView()
        cl.addWidget(self.preview, 1)
        self.preview_caption = QLabel("")
        self.preview_caption.setStyleSheet(f"color:{theme.INK2};font-size:11px;")
        self.preview_caption.setAlignment(Qt.AlignCenter)
        self.preview_caption.setFixedHeight(22)
        cl.addWidget(self.preview_caption)

        # 原稿浏览条（需要"从第几页开始"的页面才显示）
        self.src_bar = QWidget()
        sb = QHBoxLayout(self.src_bar)
        sb.setContentsMargins(8, 0, 8, 6)
        sb.setSpacing(6)
        self.btn_src = QPushButton("看原稿")
        self.btn_src.setCheckable(True)
        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        for b in (self.btn_prev, self.btn_next):
            b.setFixedWidth(30)
        self.lab_src = QLabel("—")
        self.lab_src.setObjectName("Hint")
        self.btn_use = QPushButton("以此页为起始")
        self.btn_use.setObjectName("AddBtn")
        sb.addWidget(self.btn_src)
        sb.addStretch(1)
        sb.addWidget(self.btn_prev)
        sb.addWidget(self.lab_src)
        sb.addWidget(self.btn_next)
        sb.addWidget(self.btn_use)
        self.src_bar.setVisible(False)
        cl.addWidget(self.src_bar)
        lay.addWidget(self.center, 1)

        # 右：缩略图（可在子类替换）
        self.thumbs = ThumbPanel()
        self.thumbs.pageClicked.connect(self._on_thumb)
        self.right = self.thumbs
        lay.addWidget(self.right)

        self.build_left()

    # -- 布局辅助
    def add_card(self, widget: QWidget):
        # 始终插在已有卡片之后、弹性空白之前（避免被挤到栏底）
        if not hasattr(self, "_card_count"):
            self._card_count = 0
        self.left_lay.insertWidget(self._card_count, widget)
        self._card_count += 1
        return widget

    def add_collapsible(self, title: str, summary: str = "") -> QVBoxLayout:
        c = Collapsible(title, summary)
        self.add_card(c)
        return c.body_lay

    def add_row(self, parent_lay, label: str, widget: QWidget):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        k = QLabel(label)
        k.setObjectName("Kv")
        k.setFixedWidth(84)
        h.addWidget(k)
        h.addStretch(1)
        h.addWidget(widget)
        parent_lay.addWidget(row)
        return row

    def stats_card(self, labels=("帖 (册)", "张 A4", "空白页")):
        card = Card()
        lab = SectionLabel("预计产出")
        card.lay.addWidget(lab)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.stat_vals = []
        for name in labels:
            col = QVBoxLayout()
            col.setSpacing(1)
            v = QLabel("—")
            v.setObjectName("BigNum")
            k = QLabel(name)
            k.setObjectName("NumLabel")
            col.addWidget(v)
            col.addWidget(k)
            row.addLayout(col)
            self.stat_vals.append(v)
        card.lay.addLayout(row)
        self.stat_hint = Hint("")
        card.lay.addWidget(self.stat_hint)
        self.left_lay.addWidget(card)   # 直接追加：位于弹性空白之后，钉在栏底
        return card

    def set_stats(self, *values):
        for lab, v in zip(self.stat_vals, values):
            lab.setText(str(v))

    def status(self, text: str):
        self.main.set_status(text)

    def build_left(self):
        pass

    # ---- 点右侧缩略图 → 中间预览这一张 ----
    def _on_thumb(self, i: int):
        # 缩略图是哪份文件生成的，就翻那份文件的第 i 页，避免“点了不动”
        src = (getattr(self.thumbs, "last_path", "") or getattr(self, "_last_preview", "")
               or getattr(self, "out_path", ""))
        if not src or not os.path.exists(src):
            return
        self.preview.show_pdf(src, i, fold=getattr(self, "_last_fold", False))
        unit = getattr(self, "_thumb_unit", "张纸")
        self.preview_caption.setText(f"第 {i + 1} {unit}")

    def refresh_preview(self):
        pass

    def run(self):
        pass

    def file_loaded(self, path: str):
        self.refresh_preview()

    def enable_source_nav(self, total: int):
        self.src_total = max(1, total)
        self.src_page = 0
        self.src_bar.setVisible(True)
        if getattr(self, "_src_hooked", False):
            for sig in (self.btn_src.toggled, self.btn_prev.clicked,
                        self.btn_next.clicked, self.btn_use.clicked):
                try:
                    sig.disconnect()
                except Exception:
                    pass
        self._src_hooked = True
        self.btn_src.toggled.connect(self._toggle_src)
        self.btn_prev.clicked.connect(lambda: self._step_src(-1))
        self.btn_next.clicked.connect(lambda: self._step_src(1))
        self.btn_use.clicked.connect(self._use_src)
        self._update_src_label()

    def _toggle_src(self, on):
        if on:
            self._show_src()
        else:
            self.refresh_preview()

    def _step_src(self, d):
        self.src_page = max(0, min(self.src_total - 1, self.src_page + d))
        if not self.btn_src.isChecked():
            self.btn_src.setChecked(True)
        self._show_src()

    def _show_src(self):
        path = getattr(getattr(self, "file", None), "path", "")
        if not path:
            return
        self.preview.show_pdf(path, self.src_page)
        self.preview_caption.setText(
            f"原稿第 {self.src_page + 1} / {self.src_total} 页 —— 看好了点右边「以此页为起始」")
        self._update_src_label()

    def _update_src_label(self):
        self.lab_src.setText(f"{self.src_page + 1} / {self.src_total}")

    def _use_src(self):
        self.on_use_page(self.src_page + 1)
        self.btn_src.setChecked(False)

    def on_use_page(self, page: int):
        pass

    def setting_widgets(self) -> dict:
        """需要记住的控件：名字 → 控件（要求有 value() 或 isChecked()）。"""
        return {}

    def save_settings(self, s):
        from PySide6.QtWidgets import QButtonGroup
        for name, w in self.setting_widgets().items():
            key = f"tool/{self.__class__.__name__}/{name}"
            if isinstance(w, QButtonGroup):
                s.setValue(key, w.checkedId())
            elif isinstance(w, QComboBox):
                s.setValue(key, w.currentIndex())
            elif hasattr(w, "value"):
                s.setValue(key, w.value())
            elif hasattr(w, "isChecked"):
                s.setValue(key, w.isChecked())
            elif hasattr(w, "index"):
                s.setValue(key, w.index())

    def load_settings(self, s):
        from PySide6.QtWidgets import QButtonGroup
        for name, w in self.setting_widgets().items():
            key = f"tool/{self.__class__.__name__}/{name}"
            val = s.value(key)
            if val is None:
                continue
            try:
                if isinstance(w, QButtonGroup):
                    btn = w.button(int(val))
                    if btn:
                        btn.setChecked(True)
                elif isinstance(w, QComboBox):
                    w.setCurrentIndex(int(val))
                elif hasattr(w, "set_value"):
                    w.set_value(float(val))
                elif hasattr(w, "setChecked"):
                    w.setChecked(str(val).lower() in ("true", "1"))
                elif hasattr(w, "set_index"):
                    w.set_index(int(val))
            except Exception:
                pass

    def is_active(self) -> bool:
        return self.main.stack.currentWidget() is self

    def on_show(self):
        self.schedule_preview()

    def _settings_signature(self):
        sig = []
        for name, w in self.setting_widgets().items():
            try:
                if hasattr(w, "checkedId"):
                    sig.append(w.checkedId())
                elif hasattr(w, "value"):
                    sig.append(round(float(w.value()), 3))
                elif hasattr(w, "isChecked"):
                    sig.append(bool(w.isChecked()))
                elif hasattr(w, "index"):
                    sig.append(w.index())
                elif hasattr(w, "currentIndex"):
                    sig.append(w.currentIndex())
                elif hasattr(w, "text"):
                    sig.append(w.text())
            except Exception:
                sig.append("?")
        return tuple(sig)

    def preview_key(self):
        path = getattr(getattr(self, "file", None), "path", "")
        try:
            mt = os.path.getmtime(path) if path else 0
        except OSError:
            mt = 0
        return (path, round(mt, 3)) + self._settings_signature()

    def note_preview(self):
        self._preview_key = self.preview_key()

    def schedule_preview(self):
        """切页时先让界面画出来，参数没变就直接不重算。"""
        if self.preview_key() == getattr(self, "_preview_key", None):
            return
        QTimer.singleShot(120, self._run_preview_once)

    def _run_preview_once(self):
        if not self.is_active():
            return
        if self.preview_key() == getattr(self, "_preview_key", None):
            return
        self.note_preview()
        self.refresh_preview()

    def require_file(self) -> bool:
        path = getattr(getattr(self, "file", None), "path", "") if hasattr(self, "file") else ""
        return bool(path)


# ------------------------------------------------------------------ 小册子
class BookletPage(ToolPage):
    title = "小册子打印"
    crumb = "书籍制作工具 / 排版"
    action_text = "开始拼版"

    def build_left(self):
        self.file = FileCard()
        self.file.picked.connect(self.file_loaded)
        self.add_card(self.file)

        self.batch_btn = QPushButton("批量：整个文件夹…")
        self.batch_btn.setToolTip("把文件夹里所有 PDF 按当前参数各拼一本")
        self.batch_btn.clicked.connect(self.run_batch)
        self.file.lay.addWidget(self.batch_btn)

        presets = Card()
        presets.lay.addWidget(SectionLabel("预设"))
        self.preset = ChipGroup(["骑马钉", "胶装分册", "自定义"])
        self.preset.changed.connect(self._on_preset)
        presets.lay.addWidget(self.preset)
        self.preset_hint = Hint("每册 20 面（5 张纸）")
        presets.lay.addWidget(self.preset_hint)
        self.add_card(presets)

        basic = Card()
        basic.lay.addWidget(SectionLabel("基本"))
        self.pages_per_sig = Stepper(20, 4, 200, 4, "面")
        self.pages_per_sig.valueChanged.connect(self._sig_changed)
        self.add_row(basic.lay, "每册页数", self.pages_per_sig)
        basic.lay.addWidget(Hint("4 的倍数；填 20 就是每册 5 张纸"))

        self.start_page = Stepper(1, 1, 9999, 1, "页")
        self.start_page.valueChanged.connect(lambda _=0: self._params_changed())
        self.add_row(basic.lay, "从第几页开始", self.start_page)
        self.start_hint = Hint("从第 1 页开始；点预览下方「看原稿」可以翻着选")
        basic.lay.addWidget(self.start_hint)
        self.binding = ChipGroup(["左边装订", "右边装订"])
        self.binding.changed.connect(lambda _=0: self._params_changed())
        basic.lay.addWidget(self.binding)

        basic.lay.addWidget(SectionLabel("成书规格"))
        self.book_size = ChipGroup(["A5（A4 对折）", "A6（对折后横切）"])
        self.book_size.changed.connect(self._size_changed)
        basic.lay.addWidget(self.book_size)
        self.size_hint = Hint("A4 一张 = 2 面 A5；对折即成一册")
        basic.lay.addWidget(self.size_hint)
        self.scale_hint = Hint("")
        self.scale_hint.setWordWrap(True)
        basic.lay.addWidget(self.scale_hint)
        self.add_card(basic)

        adv_lay = self.add_collapsible("高级设置", "缩放 · 页边距 · 起始页 · 镜像")
        self.mode = QComboBox()
        self.mode.addItems(["等比适应", "等比填满", "拉伸填满"])
        self.mode.setFixedWidth(132)
        self.mode.currentIndexChanged.connect(lambda _=0: self._params_changed())
        self.add_row(adv_lay, "页面缩放", self.mode)
        self.margin = Stepper(0, 0, 30, 0.5, "mm", 1)
        self.margin.valueChanged.connect(lambda _=0: self._params_changed())
        self.add_row(adv_lay, "页边距", self.margin)
        self.skip = Stepper(0, 0, 999, 1, "页")
        self.skip.valueChanged.connect(lambda _=0: self._params_changed())
        self.add_row(adv_lay, "跳过前几页", self.skip)
        self.mirror = QCheckBox("整体镜像（印出来左右反了才勾）")
        self.mirror.stateChanged.connect(lambda _=0: self._params_changed())
        adv_lay.addWidget(self.mirror)
        tip = Card()
        tip.lay.addWidget(SectionLabel("打印提示"))
        tip.lay.addWidget(Hint("双面打印 · 短边翻转 · 缩放 100%\n"
                               "沿中线对折，左半张往后翻，书脊在左\n"
                               "先打 1 张验：正面左 = 本册末页，右 = 第 1 页"))
        self.add_card(tip)

        self.stats_card()
        self.set_stats("—", "—", "—")
        self.stat_hint.setText("选一个 PDF 就会自动排页")

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._preview_now)

    def _on_preset(self, i):
        if getattr(self, "_lock", False):
            return
        self._lock = True
        try:
            if i == 0:
                self.pages_per_sig.set_value(20)
                self.preset_hint.setText("每册 20 面（5 张纸），骑马钉")
            elif i == 1:
                self.pages_per_sig.set_value(40)
                self.preset_hint.setText("每册 40 面（10 张纸），胶装分册")
            else:
                self.preset_hint.setText("直接在「每册页数」里填，要 4 的倍数")
                self.pages_per_sig.edit.setFocus()
                self.pages_per_sig.edit.selectAll()
        finally:
            self._lock = False
        self._params_changed()

    def _size_changed(self, _i=0):
        if self.book_size.index() == 1:
            self.size_hint.setText("A4 一张出 2 份 A6：先对折、再沿中线横切，两张各自装订")
        else:
            self.size_hint.setText("A4 一张 = 2 面 A5；对折即成一册")
        self._params_changed()

    def setting_widgets(self):
        return {"每册页数": self.pages_per_sig, "起始页": self.start_page,
                "装订": self.binding, "成书": self.book_size,
                "缩放": self.mode, "页边距": self.margin, "镜像": self.mirror}

    def _sig_changed(self, _v=0):
        if getattr(self, "_lock", False):
            return
        self._lock = True
        try:
            n = int(self.pages_per_sig.value())
            if n % 4:                      # 自动吸附到 4 的倍数
                n = max(4, int(round(n / 4.0)) * 4)
                self.pages_per_sig.set_value(n)
            if n == 20:
                self.preset.set_index(0)
                self.preset_hint.setText("每册 20 面（5 张纸），骑马钉")
            elif n == 40:
                self.preset.set_index(1)
                self.preset_hint.setText("每册 40 面（10 张纸），胶装分册")
            else:
                self.preset.set_index(2)
                self.preset_hint.setText(f"自定义：每册 {n} 面（{n // 4} 张纸）")
        finally:
            self._lock = False
        self._params_changed()

    def _params_changed(self):
        n = int(self.start_page.value())
        self.start_hint.setText(
            f"从第 {n} 页开始排版" + (f"，前 {n - 1} 页不参与" if n > 1 else "（全书）")
            + "；点预览下方「看原稿」可以翻着选")
        self._update_stats()
        self._timer.start(420)

    def _update_stats(self):
        if not self.file.path:
            return
        try:
            with fitz.open(self.file.path) as d:
                n = len(d)
        except Exception:
            return
        self._update_scale_hint(n)
        per_sig = max(1, int(self.pages_per_sig.value()) // 4)
        plan = pdfops.booklet_plan(n, per_sig, max(0, int(self.start_page.value()) - 1), 1)
        sheets = sum(len(p["sheets"]) for p in plan)
        blanks = sum(1 for p in plan for s in p["sheets"]
                     for x in s if x is None or x > p["count"])
        shown_sheets = math.ceil(sheets / 2) if self.book_size.index() == 1 else sheets
        self.set_stats(len(plan), shown_sheets, blanks)
        if plan:
            self.stat_hint.setText(
                f"每帖页数：{' / '.join(str(p['count']) for p in plan[:6])}"
                + (" …" if len(plan) > 6 else "")
                + f"　预计 {max(1, sheets * 0.02):.1f} 秒")
        else:
            self.stat_hint.setText("没有可排的页面")

    def refresh_preview(self):
        """切回本页、或文件被别人换掉时也要重画。"""
        self._preview_now()

    def _update_scale_hint(self, pages: int):
        """告诉用户原稿会被缩到多少——这是最容易印完才发现的问题。"""
        try:
            with fitz.open(self.file.path) as d:
                r = d[0].rect
                src_w, src_h = r.width, r.height
                if d[0].rotation % 180:
                    src_w, src_h = src_h, src_w
        except Exception:
            return
        target = (297.64, 419.53) if self.book_size.index() == 1 else (419.53, 595.28)
        m = self.margin.value() * 72 / 25.4 * 2
        cw, ch = target[0] - m, target[1] - m
        scale = min(cw / src_w, ch / src_h) if src_w and src_h else 1.0
        mm = lambda v: v * 25.4 / 72
        name = lambda w, h: ("A4" if abs(mm(w) - 210) < 4 and abs(mm(h) - 297) < 4 else
                             "A5" if abs(mm(w) - 148) < 4 and abs(mm(h) - 210) < 4 else
                             "A6" if abs(mm(w) - 105) < 4 and abs(mm(h) - 148) < 4 else
                             f"{mm(w):.0f}×{mm(h):.0f}mm")
        book = "A6" if self.book_size.index() == 1 else "A5"
        if scale >= 0.98:
            self.scale_hint.setText(f"原稿 {name(src_w, src_h)} → 成品 {book}：1:1，内容不缩放")
            self.scale_hint.setStyleSheet("color:#7A7365;")
        else:
            pct = round(scale * 100)
            self.scale_hint.setText(
                f"注意：原稿 {name(src_w, src_h)} → 成品 {book}，内容会缩到 {pct}%；"
                f"正文 10pt 印出来约 {10 * scale:.1f}pt。想保持原大，请按 {book} 尺寸重排原稿。")
            self.scale_hint.setStyleSheet(f"color:{theme.RED};")

    def _preview_now(self):
        if not self.is_active() or not self.file.path:
            return
        if self.btn_src.isChecked():
            return
        self.note_preview()
        self._update_stats()
        path = self.file.path
        try:
            with fitz.open(path) as d:
                n = len(d)
            if n > 600:
                # 页数太多不做整本拼版预览，但原稿缩略图照样给，点了也能翻
                self._last_preview = path
                self._last_fold = False
                self._thumb_unit = "页（原稿）"
                self.preview.show_pdf(path, 0)
                self.thumbs.load(path, limit=12, dpi=20)
                self.preview_caption.setText(
                    f"原稿第 1 页（{n} 页太多，只做原稿预览；点右侧可翻页）")
                return
            out = os.path.join(TMP, "preview_booklet.pdf")
            is_a6 = self.book_size.index() == 1
            pdfops.impose_booklet(path, out, max(1, int(self.pages_per_sig.value()) // 4),
                                  "left" if self.binding.index() == 0 else "right",
                                  self.mirror.isChecked(), ["contain", "cover", "stretch"][self.mode.currentIndex()],
                                  self.margin.value(), max(0, int(self.start_page.value()) - 1),
                                  book_size="A6" if is_a6 else "A5")
            self.preview.show_pdf(out, 0, fold=not is_a6)
            self._last_preview = out
            self._last_fold = not is_a6
            self.thumbs.load(out, limit=12, dpi=20)
            self.preview_caption.setText(
                "第 1 张纸 · 正面（上下各一份 A6，沿中线横切）" if is_a6
                else "第 1 张纸 · 正面（左侧 = 本册末页）")
        except Exception as e:
            self.status(f"预览失败：{e}")

    def file_loaded(self, path):
        try:
            with fitz.open(path) as d:
                self.enable_source_nav(len(d))
        except Exception:
            pass
        self._update_stats()
        self._timer.start(120)

    def on_use_page(self, page: int):
        self.start_page.set_value(page)

    def run(self):
        if not self.file.path:
            self.status("先选一个 PDF")
            return
        src = self.file.path
        out = self.main.out_path_for(src, "-小册子.pdf")
        args = dict(max_sheets=max(1, int(self.pages_per_sig.value()) // 4),
                    binding="left" if self.binding.index() == 0 else "right",
                    mirror=self.mirror.isChecked(),
                    mode=["contain", "cover", "stretch"][self.mode.currentIndex()],
                    margin_mm=self.margin.value(),
                    skip=max(0, int(self.start_page.value()) - 1),
                    book_size="A6" if self.book_size.index() == 1 else "A5")
        self.main.busy(True)
        self.status("正在拼版…")

        def job(cb):
            st = pdfops.impose_booklet(src, out, progress=cb, **args)
            st["path"] = out
            return st

        self._job = submit(job,
               on_progress=self.main.progress,
               on_done=lambda st: self._done(st),
               on_fail=self.main.fail)

    def _params(self) -> dict:
        return dict(max_sheets=max(1, int(self.pages_per_sig.value()) // 4),
                    binding="left" if self.binding.index() == 0 else "right",
                    mirror=self.mirror.isChecked(),
                    mode=["contain", "cover", "stretch"][self.mode.currentIndex()],
                    margin_mm=self.margin.value(),
                    skip=max(0, int(self.start_page.value()) - 1),
                    book_size="A6" if self.book_size.index() == 1 else "A5")

    def run_batch(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        folder = QFileDialog.getExistingDirectory(self, "选择放 PDF 的文件夹")
        if not folder:
            return
        pdfs = sorted(f for f in os.listdir(folder)
                      if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(folder, f)))
        if not pdfs:
            return self.status("这个文件夹里没有 PDF")
        if QMessageBox.question(self, "批量拼版",
                                f"共 {len(pdfs)} 个 PDF，按当前参数各拼一本？",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        args = self._params()
        done, failed = [], []

        def job(cb):
            for i, name in enumerate(pdfs, 1):
                if CANCEL.is_set():
                    break
                src = os.path.join(folder, name)
                out = self.main.out_path_for(src, "-小册子.pdf")
                try:
                    pdfops.impose_booklet(src, out, **args)
                    done.append(out)
                except Exception as e:  # noqa: BLE001
                    logging.getLogger(__name__).exception("批量失败：%s", name)
                    failed.append(f"{name}：{e}")
                cb(i, len(pdfs))
            return {"done": done, "failed": failed}

        self.main.busy(True)
        self.status(f"批量拼版 0/{len(pdfs)}…")
        self._batch_job = submit(job,
               on_progress=lambda d, t: self.status(f"批量拼版 {d}/{t}…"),
               on_done=self._batch_done,
               on_fail=self.main.fail)

    def _batch_done(self, res):
        self.main.busy(False)
        msg = f"完成 {len(res['done'])} 本"
        if res["failed"]:
            msg += f"，失败 {len(res['failed'])} 个"
            logging.error("批量失败：%s", "; ".join(res["failed"]))
        self.status(msg)
        self.main.set_status(msg)
        if res["done"]:
            self.main.offer_open(res["done"][0])

    def _done(self, st):
        self.main.busy(False)
        self.out_path = st["path"]
        self._last_preview = self.out_path
        self._last_fold = st.get("size") != "A6"
        self.preview.show_pdf(self.out_path, 0, fold=st.get("size") != "A6")
        self.thumbs.load(self.out_path)
        self.preview_caption.setText("第 1 张纸 · 正面")
        self.main.set_status(
            f"完成：{st['signatures']} 帖 / {st['sheets']} 张 "
            f"{'A6 双份' if st.get('size') == 'A6' else ''} / 空白 {st['blanks']} 页".replace("  /", "/")
            + margin_note(st, self.margin.value()))
        self.main.offer_open(self.out_path)


# ------------------------------------------------------------------ 封面
class CoverPage(ToolPage):
    title = "封面制作"
    crumb = "书籍制作工具 / 设计"
    action_text = "生成封面"
    # 封面不靠输入文件：开本、书名、配色都是自己填的，纯文字封面也必须能生成。
    # 原来继承 ToolPage.require_file（没 file 就当没准备好），主按钮永远是灰的。
    always_ready = True

    def on_show(self):
        super().on_show()
        # 图槽会把整条文件名铺在标签上，长名字撑爆左栏 → 压成省略号
        try:
            from .cover_link import tidy_labels
            tidy_labels(self)
        except Exception:
            pass
        # 右栏一键收起（收起=连功能一起收起，封面只留图）
        try:
            from .right_rail import attach_page_right_rail
            rail = getattr(self, "_right_rail", None)
            if rail is None:
                attach_page_right_rail(self)
            else:
                rail.reposition()
        except Exception:
            pass

    # ---------------- 左栏：开本 / 图片 / 输出 ----------------
    def build_left(self):
        size = Card()
        size.lay.addWidget(SectionLabel("开本"))
        self.preset = ChipGroup(["A6 105×148", "A5 148×210"])
        self.preset.changed.connect(self._preset_changed)
        size.lay.addWidget(self.preset)
        self.w = Stepper(148, 50, 400, 1, "mm")
        self.h = Stepper(210, 50, 500, 1, "mm")
        self.spine = Stepper(12.5, 0, 80, 0.5, "mm", 1)
        # 默认尺寸是 148×210（A5），开本选中项要跟上；blockSignals 避免此时就回调
        self.preset.blockSignals(True)
        self.preset.set_index(1)
        self.preset.blockSignals(False)
        for lab, w in (("成品宽度", self.w), ("成品高度", self.h), ("书脊厚度", self.spine)):
            w.valueChanged.connect(lambda _=0: self._changed())
            self.add_row(size.lay, lab, w)
        self._spine_text_saved = ""
        self.spine.valueChanged.connect(lambda _=0: self._sync_spine_text())

        # 书脊厚度只认实测值：以前按「总页数 × 克重」估算，实际差 1–2mm 很常见，
        # 填错的后果是书脊文字压到封面/封底上。估算用的几个控件保留（配置键不变、
        # 老设置照样能读），但不再出现在界面上，也不会再改写「书脊厚度」。
        self.pages_count = Stepper(200, 0, 2000, 4, "页")
        self.paper_gsm = QComboBox()
        self.paper_gsm.addItems(list(cover_core.PAPER_THICK.keys()))
        self.paper_gsm.setCurrentIndex(1)
        self.spine_hint = Hint("")
        self.spine_note = Hint("厚度按成品量（书芯压紧后），填 0 则不印书脊文字。")
        size.lay.addWidget(self.spine_note)
        self.add_card(size)

        imgs = Card()
        imgs.lay.addWidget(SectionLabel("已设计好的图（优先）"))
        self.front_img = ImagePicker("封面图")
        self.spine_img = ImagePicker("书脊图")
        self.back_img = ImagePicker("封底图")
        for picker in (self.front_img, self.spine_img, self.back_img):
            picker.btn.clicked.connect(lambda _=0, pk=picker: self._after_pick(pk))
            imgs.lay.addWidget(picker)
        imgs.lay.addWidget(SectionLabel("图片怎么放进版面"))
        self.fit_mode = ChipGroup(["等比适应", "等比填满", "拉伸填满"])
        self.fit_mode.changed.connect(lambda _=0: self._changed())
        imgs.lay.addWidget(self.fit_mode)
        imgs.lay.addWidget(Hint("等比适应：整张图都留，边上补底色（不会裁掉内容）\n"
                                "等比填满：铺满不留边，超出部分裁掉\n"
                                "拉伸填满：硬拉到版面比例，会变形"))
        self.add_card(imgs)

        out = Card()
        out.lay.addWidget(SectionLabel("输出方式"))
        self.sheet_mode = ChipGroup(["A4 居中打印", "仅封面图（1:1）"])
        self.sheet_mode.changed.connect(lambda _=0: self._changed())
        out.lay.addWidget(self.sheet_mode)
        self.sheet_hint = Hint("A4 横向纸上居中；放不下会等比缩小，四周留 5mm 安全边距。")
        self.sheet_hint.setWordWrap(True)
        out.lay.addWidget(self.sheet_hint)

        self.bleed = Stepper(3, 0, 10, 1, "mm")
        self.bleed.valueChanged.connect(lambda _=0: self._changed())
        self.add_row(out.lay, "出血", self.bleed)
        self.dpi = QComboBox()
        self.dpi.addItems(["300 dpi", "600 dpi"])
        self.dpi.currentIndexChanged.connect(lambda _=0: self._changed())
        self.add_row(out.lay, "分辨率", self.dpi)
        self.barcode = QCheckBox("封底留条码位")
        self.barcode.setChecked(True)
        self.barcode.stateChanged.connect(lambda _=0: self._changed())
        out.lay.addWidget(self.barcode)
        self.marks = QCheckBox("裁切 / 折页辅助线")
        self.marks.setChecked(True)
        self.marks.setToolTip("四角裁切线 + 书脊两条折线，只画在出血区，成品裁掉就没了")
        self.marks.stateChanged.connect(lambda _=0: self._changed())
        out.lay.addWidget(self.marks)
        out.lay.addWidget(Hint("辅助线只画在出血区：裁切后看不见，也不会压到画面。"))
        self.add_card(out)

        self.stats_card(("展开宽", "展开高", "像素"))
        self.set_stats("—", "—", "—")

        # ---------------- 右栏：设计 ----------------
        self._build_right()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh_preview)
        self._sync_spine_text()

    def _build_right(self):
        from PySide6.QtWidgets import QLineEdit, QPlainTextEdit

        self.thumbs.setParent(None)

        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 8, 0)
        outer.setSpacing(12)
        outer.addStretch(1)

        def card(title, rows):
            c = Card()
            c.lay.addWidget(SectionLabel(title))
            for item in rows:
                if isinstance(item, tuple):
                    lab, w, *rest = item
                    line = QHBoxLayout()
                    line.setContentsMargins(0, 0, 0, 0)
                    line.setSpacing(8)
                    lb = QLabel(lab)
                    lb.setFixedWidth(72)
                    line.addWidget(lb)
                    line.addWidget(w, 1)
                    c.lay.addLayout(line)
                    if rest:
                        c.lay.addWidget(rest[0])
                else:
                    c.lay.addWidget(item)
            outer.insertWidget(outer.count() - 1, c)
            return c

        self.template = ChipGroup(["竖排文学", "教材技术", "极简留白", "满图压字"])
        self.template.changed.connect(lambda _=0: self._changed())
        self.palette = ChipGroup(list(cover_core.PALETTES.keys()))
        self.palette.changed.connect(lambda _=0: self._changed())
        card("版式", [self.template])
        card("配色", [self.palette])

        self.title_edit = QLineEdit("认 JAVA（上）")
        self.sub_edit = QLineEdit("从一行代码开始")
        self.author_edit = QLineEdit("LOU0122 著")
        self.series_edit = QLineEdit()
        self.series_edit.setPlaceholderText("系列名（可留空）")
        self.pub_edit = QLineEdit()
        self.pub_edit.setPlaceholderText("出版社 / 品牌（可留空）")
        for w in (self.title_edit, self.sub_edit, self.author_edit,
                  self.series_edit, self.pub_edit):
            w.textChanged.connect(lambda _=0: self._changed())

        self.font_box = QComboBox()
        self.font_box.addItems(["黑体", "宋体", "微软雅黑", "楷体"])
        self.font_box.currentIndexChanged.connect(lambda _=0: self._changed())
        self.title_color = "#1E1B18"
        self.color_btn = QPushButton("选颜色")
        self.color_btn.clicked.connect(self._pick_color)

        self.back_edit = QPlainTextEdit()
        self.back_edit.setPlaceholderText("封底文字（会自动换行，可留空）")
        self.back_edit.setFixedHeight(72)
        self.back_edit.textChanged.connect(lambda: self._changed())

        card("封面文字", [
            ("书名", self.title_edit),
            ("副标题", self.sub_edit),
            ("作者", self.author_edit),
            ("系列", self.series_edit),
            ("出版", self.pub_edit),
            ("字体", self.font_box),
            ("颜色", self.color_btn),
            self.back_edit,
        ])

        self.spine_edit = QLineEdit()
        self.spine_edit.setPlaceholderText("留空就用书名")
        self.spine_edit.textChanged.connect(lambda _=0: self._changed())
        self.spine_pt = Stepper(16, 6, 60, 1, "pt")
        self.spine_pt.valueChanged.connect(lambda _=0: self._changed())
        self.vertical = QCheckBox("竖排")
        self.vertical.setChecked(True)
        self.vertical.stateChanged.connect(lambda _=0: self._changed())
        card("书脊", [("文字", self.spine_edit), ("字号", self.spine_pt), self.vertical])

        tip = Card()
        tip.lay.addWidget(SectionLabel("提示"))
        tip.lay.addWidget(Hint("导入现成的封面图会盖住版式文字——图已经设计好时，"
                               "把书名等文字留空最干净。\n"
                               "图可以是图片，也可以是 PDF 的某一页。"))
        outer.insertWidget(outer.count() - 1, tip)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        scroll.setFixedWidth(340)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.layout().addWidget(scroll)

    # ---------------- 交互 ----------------
    def _after_pick(self, picker):
        self._changed()

    def setting_widgets(self):
        return {"宽": self.w, "高": self.h, "书脊": self.spine, "出血": self.bleed,
                "字号": self.spine_pt, "竖排": self.vertical, "字体": self.font_box,
                "裁切线": self.marks, "分辨率": self.dpi, "图片模式": self.fit_mode,
                "输出方式": self.sheet_mode,
                "版式": self.template, "配色": self.palette,
                "页数": self.pages_count, "纸张": self.paper_gsm, "条码": self.barcode}

    def _auto_spine(self):
        """按页数估算书脊已停用：厚度只认实测值（见 build_left 里的说明）。"""
        return

    def _sync_spine_text(self):
        """厚度为 0 时把书脊文字置成零宽空格。

        原程序在 0 宽的脊上照样排书脊文字，字会压到封面/封底上；要么填厚度，
        要么不印字，没有第三种。
        """
        if not hasattr(self, "spine_edit") or not hasattr(self, "spine_note"):
            return
        try:
            value = float(self.spine.value() or 0)
        except (TypeError, ValueError):
            value = 0.0
        current = self.spine_edit.text()
        blank = "\u200b"
        if value <= 0:
            if current.strip() and current != blank:
                self._spine_text_saved = current
            if current != blank:
                self.spine_edit.setText(blank)
            self.spine_note.setText("厚度填 0：书脊上不印字。量好实测厚度再填，字会回来。")
        else:
            if current == blank:
                self.spine_edit.setText(getattr(self, "_spine_text_saved", ""))
            self.spine_note.setText("厚度按成品量（书芯压紧后）。")
        self._limit_spine_pt(value)
        self._changed()

    def _limit_spine_pt(self, spine_mm=None) -> None:
        """字号不能大过这条脊：超了字就会压到封面/封底上。

        上限 = 书脊宽 × 0.72 换算成 pt（和 core.cover.max_spine_pt 同一套算法）。
        界面把字号步进器的上限跟着厚度走；已经超了的直接调回上限，并在提示里说明。
        """
        if not hasattr(self, "spine_pt") or not hasattr(self, "spine_note"):
            return
        try:
            mm = float(self.spine.value() if spine_mm is None else spine_mm)
        except (TypeError, ValueError):
            mm = 0.0
        if mm <= 0:
            self.spine_pt.set_range(6, 60)
            return
        limit = max(6, int(cover_core.max_spine_pt(mm)))
        self.spine_pt.set_range(6, limit)
        clamped = float(self.spine_pt.value()) > limit
        if clamped:
            self.spine_pt.set_value(limit)
        note = f"厚度按成品量（书芯压紧后）；{mm:g}mm 的书脊，字号最多 {limit}pt。"
        if clamped:
            note = f"字号超出书脊宽度，已调到 {limit}pt（{mm:g}mm 的脊最多这么多）。"
        self.spine_note.setText(note)

    def load_settings(self, s):
        super().load_settings(s)
        try:
            # 升级一次性迁移：老版本那个厚度是按页数估出来的，统一换成常用实测值 12.5mm
            if not s.value("ui/spine_default_v2"):
                s.setValue("tool/CoverPage/书脊", 12.5)
                s.setValue("ui/spine_default_v2", 1)
                s.setValue("ui/spine_manual", 1)
                s.sync()
                self.spine.set_value(12.5)
        except Exception:
            pass
        self._sync_spine_text()
        self._sync_preset_chip()

    def _sync_preset_chip(self) -> None:
        """开本选中项跟着实际宽高走（宽高是存过的，开本不存，容易和数字不一致）。"""
        if not hasattr(self, "preset"):
            return
        try:
            w, h = int(self.w.value()), int(self.h.value())
        except (TypeError, ValueError):
            return
        if (w, h) == (105, 148):
            idx = 0
        elif (w, h) == (148, 210):
            idx = 1
        else:
            return
        self.preset.blockSignals(True)
        self.preset.set_index(idx)
        self.preset.blockSignals(False)

    def _pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(self.title_color), self, "书名颜色")
        if c.isValid():
            self.title_color = c.name()
            self.color_btn.setStyleSheet(
                f"text-align:left; padding-left:10px; border-left:4px solid {self.title_color};")
            self._changed()

    def _preset_changed(self, i):
        w, h = [(105, 148), (148, 210)][i]
        self.w.set_value(w)
        self.h.set_value(h)
        self._changed()

    def _changed(self):
        if hasattr(self, "_timer"):
            self._timer.start(280)

    # ---------------- 渲染 ----------------
    def _render(self, dpi):
        return cover_core.render_cover(
            self.w.value(), self.h.value(), self.spine.value(), self.bleed.value(),
            dpi=dpi,
            title=self.title_edit.text().strip() or ("" if self.front_img.path else "书名"),
            subtitle=self.sub_edit.text(), author=self.author_edit.text(),
            spine_pt=self.spine_pt.value(), vertical=self.vertical.isChecked(),
            spine_text=self.spine_edit.text().strip() or None,
            front_img=self.front_img.path or None,
            back_img=self.back_img.path or None,
            spine_img=self.spine_img.path or None,
            title_font=self.font_box.currentText(),
            template=["classic", "modern", "minimal", "image"][self.template.index()],
            palette=list(cover_core.PALETTES.keys())[self.palette.index()],
            publisher=self.pub_edit.text().strip(),
            series=self.series_edit.text().strip(),
            barcode=self.barcode.isChecked(),
            title_color=self.title_color,
            back_text=self.back_edit.toPlainText(),
            crop_marks=self.marks.isChecked(),
            fit=["contain", "cover", "stretch"][self.fit_mode.index()],
            sheet="a4" if self.sheet_mode.index() == 0 else "cover",
        )

    def refresh_preview(self):
        if not self.is_active():
            return
        self.note_preview()
        try:
            img = self._render(150)
        except Exception as e:
            self.status(f"预览失败：{e}")
            return
        q = QImage(img.tobytes("raw", "RGB"), img.width, img.height,
                   img.width * 3, QImage.Format_RGB888).copy()
        self.preview.set_image(QPixmap.fromImage(q))
        bw = self.w.value() * 2 + self.spine.value() + self.bleed.value() * 2
        bh = self.h.value() + self.bleed.value() * 2
        dpi = 300 if self.dpi.currentIndex() == 0 else 600
        self.set_stats(f"{bw:.0f}", f"{bh:.0f}", f"{int(bw/25.4*dpi)}×{int(bh/25.4*dpi)}")
        if self.sheet_mode.index() == 0:
            bw = self.w.value() * 2 + self.spine.value() + self.bleed.value() * 2
            bh = self.h.value() + self.bleed.value() * 2
            sc = min(1.0, (297 - 10) / bw, (210 - 10) / bh)
            note = "" if sc > 0.995 else f" · 缩到 {sc*100:.0f}%"
            self.preview_caption.setText(f"A4 居中{note} · 实线为裁切/折页线")
            self.sheet_hint.setText(
                "A4 横向纸上居中。" if sc > 0.995 else
                f"封面比 A4 大，已等比缩到 {sc*100:.0f}% 才能整张打出来；"
                "要 1:1 请改选「仅封面图」。")
        else:
            self.preview_caption.setText("展开图：封底 | 书脊 | 封面（含出血）")
            self.sheet_hint.setText("1:1 输出展开图，尺寸就是上面算的成品尺寸加出血。")
        self.main.set_status(f"封面尺寸：{bw:.0f} × {bh:.0f} mm")

    def run(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存封面", "封面.pdf", "PDF (*.pdf)")
        if not path:
            return
        try:
            dpi = 300 if self.dpi.currentIndex() == 0 else 600
            cover_core.save_pdf(self._render(dpi), path, dpi=dpi)
            self.out_path = path
            self.main.set_status(f"已生成：{path}")
            self.main.offer_open(path)
        except Exception as e:
            self.main.fail(str(e))


# ------------------------------------------------------------------ 四堆叠放
class FourStackPage(ToolPage):
    title = "四堆叠放"
    crumb = "书籍制作工具 / 排版"
    action_text = "开始编排"

    def build_left(self):
        self.file = FileCard()
        self.file.picked.connect(self.file_loaded)
        self.add_card(self.file)

        c = Card()
        c.lay.addWidget(SectionLabel("参数"))
        self.binding = ChipGroup(["左边装订", "右边装订"])
        self.binding.changed.connect(lambda _=0: self._changed())
        c.lay.addWidget(self.binding)
        self.mode = QComboBox()
        self.mode.addItems(["等比适应", "等比填满", "拉伸填满"])
        self.mode.setFixedWidth(132)
        self.mode.currentIndexChanged.connect(lambda _=0: self._changed())
        self.add_row(c.lay, "页面缩放", self.mode)
        self.margin = Stepper(0, 0, 30, 0.5, "mm", 1)
        self.margin.valueChanged.connect(lambda _=0: self._changed())
        self.add_row(c.lay, "页边距", self.margin)
        self.start_page = Stepper(1, 1, 9999, 1, "页")
        self.start_page.valueChanged.connect(self._start_changed)
        self.add_row(c.lay, "从第几页开始", self.start_page)
        self.start_hint = Hint("从第 1 页开始")
        c.lay.addWidget(self.start_hint)
        c.lay.addWidget(Hint("每张纸 8 页（A6 ×4）：横竖各一刀，切成 4 叠后按叠序装订"))
        self.scale_hint = Hint("")
        self.scale_hint.setWordWrap(True)
        c.lay.addWidget(self.scale_hint)
        self.add_card(c)

        self.stats_card(("张 A4", "输出面数", "空白格"))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh_preview)

    def _start_changed(self, _v=0):
        n = int(self.start_page.value())
        self.start_hint.setText(
            f"从第 {n} 页开始" + (f"，前 {n - 1} 页不参与" if n > 1 else "（全书）"))
        self._changed()

    def file_loaded(self, path):
        try:
            with fitz.open(path) as d:
                self.enable_source_nav(len(d))
                self._update_scale_hint(d[0])
        except Exception:
            pass
        self.refresh_preview()

    def _update_scale_hint(self, page):
        """A6 格子只有 A4 的一半，明说会缩多少。"""
        try:
            r = page.rect
            w, h = (r.height, r.width) if page.rotation % 180 else (r.width, r.height)
        except Exception:
            return
        m = self.margin.value() * 72 / 25.4 * 2
        cw, ch = 297.64 - m, 419.53 - m
        scale = min(cw / w, ch / h) if w and h else 1.0
        mm = lambda v: v * 25.4 / 72
        if scale >= 0.98:
            self.scale_hint.setText(f"原稿 {mm(w):.0f}×{mm(h):.0f}mm → A6 格：1:1，不缩放")
            self.scale_hint.setStyleSheet("color:#7A7365;")
        else:
            self.scale_hint.setText(
                f"注意：原稿 {mm(w):.0f}×{mm(h):.0f}mm → A6 格，内容会缩到 {round(scale*100)}%；"
                f"正文 10pt 印出来约 {10*scale:.1f}pt。")
            self.scale_hint.setStyleSheet("color:#B23A2E;")

    def on_use_page(self, page: int):
        self.start_page.set_value(page)

    def setting_widgets(self):
        return {"装订": self.binding, "缩放": self.mode, "页边距": self.margin,
                "起始页": self.start_page}

    def _changed(self):
        self._timer.start(400)

    def refresh_preview(self):
        if not self.is_active() or not self.file.path:
            return
        self.note_preview()
        if self.btn_src.isChecked():
            return
        try:
            out = os.path.join(TMP, "preview_fs.pdf")
            st = pdfops.impose_fourstack(self.file.path, out,
                                    "left" if self.binding.index() == 0 else "right",
                                    ["contain", "cover", "stretch"][self.mode.currentIndex()],
                                    self.margin.value(), skip=max(0, int(self.start_page.value()) - 1))
            self._last_preview = out
            self._last_fold = False
            self.preview.show_pdf(out, 0)
            self.thumbs.load(out, limit=12, dpi=20)
            with fitz.open(out) as d:
                n = len(d)
            self.set_stats(n // 2, n, "—")
            self.preview_caption.setText("第 1 张纸 · 正面（点右侧缩略图可切换）")
        except Exception as e:
            self.status(f"预览失败：{e}")

    def run(self):
        if not self.file.path:
            return self.status("先选一个 PDF")
        out = self.main.out_path_for(self.file.path, "-四堆叠.pdf")
        self.main.busy(True)
        self._job = submit(lambda cb: dict(pdfops.impose_fourstack(
            self.file.path, out,
            "left" if self.binding.index() == 0 else "right",
            ["contain", "cover", "stretch"][self.mode.currentIndex()],
            self.margin.value(), skip=max(0, int(self.start_page.value()) - 1),
            progress=cb), path=out),
            on_progress=self.main.progress,
            on_done=lambda st: self._done(st), on_fail=self.main.fail)

    def _done(self, st):
        self.main.busy(False)
        self.out_path = st["path"]
        self.preview.show_pdf(self.out_path, 0)
        self.thumbs.load(self.out_path)
        self.set_stats(st["sheets"], st["pages"], st["blanks"])
        self.main.set_status(f"完成：{st['sheets']} 张 / {st['pages']} 面"
                             + margin_note(st, self.margin.value()))
        self.main.offer_open(self.out_path)


# ------------------------------------------------------------------ 4合1
class FourUpPage(ToolPage):
    title = "4 合 1 拼图"
    crumb = "书籍制作工具 / 排版"
    action_text = "开始拼版"

    def build_left(self):
        self.file = FileCard()
        self.file.picked.connect(self.file_loaded)
        self.add_card(self.file)

        c = Card()
        c.lay.addWidget(SectionLabel("排列方式"))
        grid = QGridLayout()
        grid.setSpacing(8)
        self.layout_group = QButtonGroup(self)
        self.layout_group.setExclusive(True)
        for k, mode in enumerate("ABCD"):
            b = QToolButton()
            b.setObjectName("ArrBtn")
            b.setCheckable(True)
            b.setText(f"模式 {mode}")
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIcon(icons.arrangement(mode, theme.INK))
            b.setIconSize(QSize(52, 52))
            b.setFixedHeight(100)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(k == 0)
            self.layout_group.addButton(b, k)
            grid.addWidget(b, k // 2, k % 2)
        self.layout_group.idClicked.connect(lambda _=0: self._changed())
        c.lay.addLayout(grid)
        c.lay.addWidget(Hint("格子里的数字 = 这张纸上该放第几页"))
        self.start = Stepper(1, 1, 9999, 1, "页")
        self.start.valueChanged.connect(self._start_changed)
        self.add_row(c.lay, "从第几页开始", self.start)
        self.start_hint = Hint("从第 1 页开始")
        c.lay.addWidget(self.start_hint)
        self.margin = Stepper(10, 0, 30, 1, "mm")
        self.margin.valueChanged.connect(lambda _=0: self._changed())
        self.add_row(c.lay, "页边距", self.margin)
        self.add_card(c)

        self.stats_card(("张 A4", "输出面数", "空白格"))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh_preview)

    def _start_changed(self, _v=0):
        n = int(self.start.value())
        self.start_hint.setText(
            f"从第 {n} 页开始" + (f"，前 {n - 1} 页不参与" if n > 1 else "（全书）"))
        self._changed()

    def file_loaded(self, path):
        try:
            with fitz.open(path) as d:
                self.enable_source_nav(len(d))
        except Exception:
            pass
        self.refresh_preview()

    def on_use_page(self, page: int):
        self.start.set_value(page)

    def setting_widgets(self):
        return {"排法": self.layout_group, "起始页": self.start, "页边距": self.margin}

    def _changed(self):
        self._timer.start(400)

    def refresh_preview(self):
        if not self.is_active() or not self.file.path:
            return
        self.note_preview()
        if self.btn_src.isChecked():
            return
        try:
            out = os.path.join(TMP, "preview_4up.pdf")
            pdfops.impose_fourup(self.file.path, out, "ABCD"[self.layout_group.checkedId()],
                                 self.margin.value(), int(self.start.value()))
            self._last_preview = out
            self._last_fold = False
            self.preview.show_pdf(out, 0)
            self.thumbs.load(out, limit=12, dpi=20)
            with fitz.open(out) as d:
                n = len(d)
            self.set_stats(n, n, max(0, n * 4 - (len(fitz.open(self.file.path)) - int(self.start.value()) + 1)))
            self.preview_caption.setText("第 1 张 · A4（点右侧缩略图可切换）")
        except Exception as e:
            self.status(f"预览失败：{e}")

    def run(self):
        if not self.file.path:
            return self.status("先选一个 PDF")
        out = self.main.out_path_for(self.file.path, "-4合1.pdf")
        self.main.busy(True)
        self._job = submit(lambda cb: dict(pdfops.impose_fourup(
            self.file.path, out, "ABCD"[self.layout_group.checkedId()],
            self.margin.value(), int(self.start.value()), progress=cb), path=out),
            on_progress=self.main.progress,
            on_done=lambda st: self._done(st), on_fail=self.main.fail)

    def _done(self, st):
        self.main.busy(False)
        self.out_path = st["path"]
        self.preview.show_pdf(self.out_path, 0)
        self.thumbs.load(self.out_path)
        self.main.set_status(f"完成：{st['sheets']} 张 A4" + margin_note(st, self.margin.value()))
        self.main.offer_open(self.out_path)


# ------------------------------------------------------------------ 合并
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
