"""每个页面的基类与公用件：ToolPage、边距提示、临时目录。"""
from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget)
from . import theme
from .widgets import (CANCEL, Card, ChipGroup, Collapsible, FileCard, Hint, ImagePicker, OutlinePanel, PreviewView, SectionLabel, Stepper, ThumbPanel, submit)


TMP = os.path.join(tempfile.gettempdir(), "booktool")


def margin_note(st: dict, want: float) -> str:
    """页面比例和格子比例对不上时，实际边距会比设定值大 —— 别让界面装没事。

    现在内边贴中线、余量全留在外口，所以四边本来就不等距：这里报外口 + 中缝。
    """
    m = (st or {}).get("margins_mm")
    if not m:
        return ""
    if "outer_v" in m and "outer_h" in m:
        if max(m["outer_v"], m["outer_h"]) - want <= 0.25:
            return ""
        return (f" · 外口 上/下 {m['outer_v']:.1f}mm、左/右 {m['outer_h']:.1f}mm，"
                f"中缝每边 {m['inner']:.1f}mm（页面比例不合，余量都留给外口裁掉）")
    vals = (m.get("top", 0.0), m.get("bottom", 0.0), m.get("left", 0.0), m.get("right", 0.0))
    if max(abs(v - want) for v in vals) <= 0.25:
        return ""
    return (f" · 实际边距 上/下 {max(vals[0], vals[1]):.1f}mm、左/右 {max(vals[2], vals[3]):.1f}mm")
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
