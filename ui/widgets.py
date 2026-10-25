"""通用控件：卡片、分段选择、步进器、文件卡、预览画布、缩略图栏、后台任务。"""
from __future__ import annotations

import os

import pymupdf as fitz
from PySide6.QtCore import (QObject, QPoint, QRect, QRunnable, QSize, Qt, QThreadPool,
                            Signal)
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QLayout, QAbstractItemView, QFileDialog, QFrame, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import theme


# ------------------------------------------------------------------ 基础块
class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(16, 14, 16, 14)
        self.lay.setSpacing(10)


class Collapsible(QFrame):
    """可折叠分组：标题 + 右侧摘要，点标题展开。"""

    def __init__(self, title: str, summary: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._open = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.head = QPushButton()
        self.head.setObjectName("CollapseHead")
        self.head.setCursor(Qt.PointingHandCursor)
        self.head.setFixedHeight(42)
        self.head.clicked.connect(self.toggle)
        hl = QHBoxLayout(self.head)
        hl.setContentsMargins(14, 0, 14, 0)
        hl.setSpacing(8)
        self.arrow = QLabel("▸")
        self.arrow.setStyleSheet("color:#8C8275;font-size:10px;")
        self.title = QLabel(title)
        self.title.setStyleSheet(f"font-size:12px;font-weight:600;color:{theme.INK};")
        self.summary = QLabel(summary)
        self.summary.setObjectName("Hint")
        hl.addWidget(self.arrow)
        hl.addWidget(self.title)
        hl.addStretch(1)
        hl.addWidget(self.summary)
        outer.addWidget(self.head)

        self.content = QWidget()
        self.content.setVisible(False)
        self.body_lay = QVBoxLayout(self.content)
        self.body_lay.setContentsMargins(16, 2, 16, 14)
        self.body_lay.setSpacing(8)
        outer.addWidget(self.content)

    def toggle(self):
        self._open = not self._open
        self.content.setVisible(self._open)
        self.arrow.setText("▾" if self._open else "▸")
        self.summary.setVisible(not self._open)


class SectionLabel(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("SectionLabel")


class Hint(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Hint")
        self.setWordWrap(True)


class Chip(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("Chip")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)


class FlowLayout(QLayout):
    """自动换行的横向布局：窄栏里 chip 不再被裁掉。"""

    def __init__(self, parent=None, h_spacing: int = 8, v_spacing: int = 8):
        super().__init__(parent)
        self._items = []
        self._hs, self._vs = h_spacing, v_spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize(0, 0)
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        x, y, line_h = rect.x(), rect.y(), 0
        right = rect.x() + rect.width()
        for it in self._items:
            hint = it.sizeHint()
            if x + hint.width() > right and line_h > 0:
                x = rect.x()
                y += line_h + self._vs
                line_h = 0
            if not test_only:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._hs
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()


class ChipGroup(QWidget):
    """单选一组 chip。"""

    changed = Signal(int)

    def __init__(self, items: list[str], parent=None):
        super().__init__(parent)
        lay = FlowLayout(self)
        self.buttons: list[Chip] = []
        for i, t in enumerate(items):
            b = Chip(t)
            b.clicked.connect(lambda _=False, idx=i: self.set_index(idx))
            lay.addWidget(b)
            self.buttons.append(b)
        self.set_index(0)

    def set_index(self, i: int):
        for k, b in enumerate(self.buttons):
            b.setChecked(k == i)
        self.changed.emit(i)

    def index(self) -> int:
        for i, b in enumerate(self.buttons):
            if b.isChecked():
                return i
        return 0


class Stepper(QWidget):
    """−  [可直接打字]  + ——中间是普通输入框，点进就能改数值。"""

    valueChanged = Signal(float)

    def __init__(self, value: float = 1, minimum: float = 0, maximum: float = 9999,
                 step: float = 1, suffix: str = "", decimals: int = 0, parent=None):
        super().__init__(parent)
        self._v = float(value)
        self._min, self._max, self._step = float(minimum), float(maximum), float(step)
        self._suffix, self._dec = suffix, decimals

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.minus = QPushButton("−")
        self.edit = QLineEdit()
        self.plus = QPushButton("+")
        self.edit.setFixedWidth(92)
        self.edit.setMinimumHeight(28)
        self.edit.setAlignment(Qt.AlignCenter)
        self.edit.setObjectName("StepEdit")
        for b in (self.minus, self.plus):
            b.setFixedSize(26, 28)
            b.setObjectName("StepBtn")
            b.setCursor(Qt.PointingHandCursor)
        for w in (self.minus, self.edit, self.plus):
            lay.addWidget(w)

        self.minus.clicked.connect(lambda: self.set_value(self._v - self._step))
        self.plus.clicked.connect(lambda: self.set_value(self._v + self._step))
        self.edit.editingFinished.connect(self._commit)
        self.setFixedWidth(144)
        self._refresh()

    def _fmt(self) -> str:
        num = f"{self._v:.{self._dec}f}" if self._dec else f"{int(round(self._v))}"
        return num + (f" {self._suffix}" if self._suffix else "")

    def _refresh(self):
        self.edit.setText(self._fmt())

    def _commit(self):
        import re
        m = re.search(r"-?\d+(?:\.\d+)?", self.edit.text())
        if m:
            self.set_value(float(m.group()))
        else:
            self._refresh()

    def set_suffix(self, text: str):
        self._suffix = text
        self._refresh()

    def set_range(self, lo: float, hi: float, step: float = None):
        self._min, self._max = float(lo), float(hi)
        if step is not None:
            self._step = float(step)
        if self._v < self._min:
            self._v = self._min
        if self._v > self._max:
            self._v = self._max
        self._refresh()

    def set_value(self, v):
        v = max(self._min, min(self._max, float(v)))
        self._v = v
        self._refresh()
        self.valueChanged.emit(v)

    def value(self):
        return self._v


class FileCard(Card):
    picked = Signal(str)

    def __init__(self, allow_images: bool = False, parent=None):
        super().__init__(parent)
        self.path = ""
        self.allow_images = allow_images
        self.lay.setContentsMargins(14, 12, 14, 12)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.badge = QLabel("PDF")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedSize(40, 50)
        self.badge.setStyleSheet(
            f"background:{theme.RED_SOFT};border:1px solid #E4C9C3;border-radius:4px;"
            f"color:{theme.RED};font-size:11px;font-weight:700;")
        col = QVBoxLayout()
        col.setSpacing(2)
        self.name = QLabel("把 PDF 拖到这里，或点右侧选择")
        self.name.setStyleSheet(f"font-size:13px;font-weight:600;color:{theme.INK};")
        self.meta = QLabel("支持整本拖入")
        self.meta.setObjectName("Hint")
        col.addWidget(self.name)
        col.addWidget(self.meta)
        self.btn = QPushButton("选择")
        self.btn.setFixedWidth(60)
        self.btn.clicked.connect(self.choose)
        row.addWidget(self.badge)
        row.addLayout(col, 1)
        row.addWidget(self.btn)
        self.lay.addLayout(row)

    def choose(self):
        types = "PDF (*.pdf)"
        if self.allow_images:
            types += ";;图片 (*.png *.jpg *.jpeg *.bmp *.webp)"
        p, _ = QFileDialog.getOpenFileName(self, "选择文件", os.path.expanduser("~"), types)
        if p:
            self.set_path(p)

    def set_path(self, path: str, emit: bool = True):
        self.path = path
        base = os.path.basename(path)
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self.name.font())
        self.name.setText(fm.elidedText(base, Qt.ElideMiddle, 196))
        self.name.setToolTip(path)
        try:
            if path.lower().endswith(".pdf"):
                with fitz.open(path) as d:
                    n = len(d)
                    r = d[0].rect
                self.meta.setText(f"{n} 页 · {os.path.getsize(path)/1e6:.1f} MB · "
                                  f"{r.width/72*25.4:.0f}×{r.height/72*25.4:.0f} mm")
            else:
                self.meta.setText(f"{os.path.getsize(path)/1e6:.1f} MB")
        except Exception as e:
            self.meta.setText(f"读取失败：{e}")
        if emit:
            self.picked.emit(path)


class ImagePicker(QWidget):
    """紧凑的“可选图片”选择行（封面页右栏用）。"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.path = ""
        self._title = title
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.lab = QLabel(title)
        self.lab.setObjectName("Hint")
        self.btn = QPushButton("选择")
        self.btn.setFixedWidth(52)
        self.btn.clicked.connect(self.choose)
        self.clear = QPushButton("×")
        self.clear.setObjectName("ClearBtn")
        self.clear.setFixedSize(22, 22)
        self.clear.setVisible(False)
        self.clear.clicked.connect(self._clear)
        lay.addWidget(self.lab, 1)
        lay.addWidget(self.btn)
        lay.addWidget(self.clear)

    def set_path(self, path):
        """代码里直接设定（测试/恢复用）。"""
        self.path = path
        self.lab.setText(os.path.basename(path) if isinstance(path, str) else "已选 PDF 页")
        self.clear.setVisible(bool(path))

    def choose(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择图片或 PDF", os.path.expanduser("~"),
            "图片或 PDF (*.png *.jpg *.jpeg *.bmp *.webp *.pdf)")
        if not p:
            return
        if p.lower().endswith(".pdf"):
            from PySide6.QtWidgets import QDialog
            from .page_picker import PagePickerDialog
            dlg = PagePickerDialog(p, self)
            if dlg.exec() != QDialog.Accepted:
                return
            self.path = (p, dlg.page)
            self.lab.setText(f"{os.path.basename(p)} · 第 {dlg.page + 1} 页")
        else:
            self.path = p
            self.lab.setText(os.path.basename(p))
        self.lab.setStyleSheet(f"color:{theme.INK};font-size:11px;")
        self.lab.setToolTip(str(self.path))
        self.clear.setVisible(True)

    def _clear(self):
        self.path = ""
        self.lab.setText(self._title)
        self.lab.setStyleSheet("")
        self.clear.setVisible(False)


# ------------------------------------------------------------------ 预览画布
class PreviewView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.item = None
        self.fold_x = None
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setStyleSheet("background: transparent; border: 0;")
        self._bg = QColor("#FFFFFF")

    def show_pdf(self, path: str, page: int = 0, dpi: int = 110, fold: bool = False):
        try:
            with fitz.open(path) as d:
                page = max(0, min(page, len(d) - 1))
                pix = d[page].get_pixmap(dpi=dpi)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                             QImage.Format_RGB888).copy()
        except Exception:
            return
        self.set_image(QPixmap.fromImage(img), fold=fold)

    def set_image(self, pix: QPixmap, fold: bool = False):
        self.scene_.clear()
        self.item = self.scene_.addPixmap(pix)
        self.item.setPos(0, 0)
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            eff = QGraphicsDropShadowEffect()
            eff.setBlurRadius(28)
            eff.setOffset(0, 10)
            eff.setColor(QColor(30, 27, 24, 70))
            self.item.setGraphicsEffect(eff)
        except Exception:
            pass
        self.scene_.setSceneRect(self.item.boundingRect())
        self.fold_x = pix.width() / 2 if fold else None
        self.fit()

    def clear_image(self) -> None:
        """清掉当前画面（换文件时用）。"""
        self.scene_.clear()
        self.item = None
        self.fold_x = None

    def fit(self):
        if self.item:
            self.resetTransform()
            self.fitInView(self.scene_.sceneRect(), Qt.KeepAspectRatio)
            r = self.scene_.sceneRect()
            self.scale(0.86, 0.86)
            self.centerOn(r.center())

    def wheelEvent(self, ev):
        f = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        self.scale(f, f)

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, self._bg)
        pen = QPen(QColor(0, 0, 0, 14))
        pen.setWidth(0)
        painter.setPen(pen)
        step = 32
        x = int(rect.left()) - int(rect.left()) % step
        while x < rect.right():
            painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
            x += step
        y = int(rect.top()) - int(rect.top()) % step
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
            y += step

    def drawForeground(self, painter, rect):
        if self.item is None:
            painter.setPen(QColor(theme.INK3))
            f = painter.font()
            f.setPointSize(11)
            painter.setFont(f)
            painter.drawText(self.viewport().rect(), Qt.AlignCenter,
                             "把 PDF 拖进来，中间就会显示排好的样子")
            return
        if self.fold_x is not None:
            pen = QPen(QColor(theme.RED))
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(int(self.fold_x), 0, int(self.fold_x),
                             int(self.scene_.sceneRect().height()))


# ------------------------------------------------------------------ 缩略图
class ThumbPanel(QFrame):
    pageClicked = Signal(int)      # 点缩略图 → 预览这一张

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.last_path = ""
        self.setFixedWidth(210)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        head = QHBoxLayout()
        self.title = QLabel("纸张")
        self.title.setStyleSheet(f"font-size:11px;font-weight:600;color:{theme.INK2};")
        self.count = QLabel("—")
        self.count.setObjectName("Hint")
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.count)
        lay.addLayout(head)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setIconSize(QSize(80, 108))
        self.list.setSpacing(4)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setStyleSheet("QListWidget{background:transparent;border:0;font-size:9pt;}"
                                "QListWidget::item{border-radius:4px;padding:2px;}"
                                f"QListWidget::item:selected{{outline:1.5px solid {theme.RED};}}")
        self.list.itemClicked.connect(self._emit_row)
        self.list.itemActivated.connect(self._emit_row)
        self.list.setToolTip("点缩略图切换中间的预览")
        lay.addWidget(self.list, 1)
        self.empty = QLabel("生成后在这里显示每张纸")
        self.empty.setObjectName("Hint")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        lay.addWidget(self.empty)

    def _emit_row(self, item):
        if item is not None:
            self.pageClicked.emit(self.list.row(item))

    def load_pages(self, path: str, pages: list, dpi: int = 20, total: int = 0):
        self.last_path = path
        """只显示指定页（用于“将要打印”）。"""
        self.list.clear()
        self.empty.setVisible(False)
        self.count.setText(f"共 {total or len(pages)} 面 · 选 {len(pages)}")
        try:
            doc = fitz.open(path)
        except Exception:
            return
        try:
            for p in pages:
                if p - 1 >= len(doc):
                    break
                pix = doc[p - 1].get_pixmap(dpi=dpi)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                             QImage.Format_RGB888).copy()
                it = QListWidgetItem()
                it.setIcon(QPixmap.fromImage(img))
                it.setText(str(p))
                it.setToolTip(f"第 {p} 面")
                self.list.addItem(it)
        finally:
            doc.close()

    def load(self, path: str, limit: int = 12, dpi: int = 20):
        self.last_path = path
        self.list.clear()
        self.empty.setVisible(False)
        try:
            doc = fitz.open(path)
        except Exception:
            return
        n = min(len(doc), limit)
        self.count.setText(f"共 {len(doc)} 面" + (f"（示 {n}）" if len(doc) > limit else ""))
        for i in range(n):
            pix = doc[i].get_pixmap(dpi=dpi)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                         QImage.Format_RGB888).copy()
            pm = QPixmap.fromImage(img)
            it = QListWidgetItem()
            it.setIcon(pm)
            it.setText(str(i + 1))
            self.list.addItem(it)
        doc.close()


class OutlinePanel(QFrame):
    """文件/分段的清单：每条带首页缩略图、标题、页码范围。"""

    currentChanged = Signal(int)

    def __init__(self, title: str = "结构", parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.setFixedWidth(210)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        head = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setStyleSheet(f"font-size:11px;font-weight:600;color:{theme.INK2};")
        self.count = QLabel("—")
        self.count.setObjectName("Hint")
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.count)
        lay.addLayout(head)

        self.list = QListWidget()
        self.list.setIconSize(QSize(46, 62))
        self.list.setSpacing(2)
        self.list.setStyleSheet(
            f"QListWidget{{background:transparent;border:0;font-size:10pt;color:{theme.INK};outline:0;}}"
            f"QListWidget::item{{padding:6px 4px;border-radius:6px;}}"
            f"QListWidget::item:selected{{background:{theme.RED_SOFT};color:{theme.INK};}}")
        lay.addWidget(self.list, 1)
        self.empty = QLabel("还没有内容")
        self.empty.setObjectName("Hint")
        self.empty.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty)
        self.list.currentRowChanged.connect(self.currentChanged.emit)

    def set_items(self, items: list[tuple[str, int, str, str]]):
        """items: (pdf 路径, 页号从 0 起, 标题, 副标题)"""
        self.list.clear()
        for path, pno, title, sub in items:
            try:
                with fitz.open(path) as d:
                    pix = d[min(pno, len(d) - 1)].get_pixmap(dpi=30)
                    img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                                 QImage.Format_RGB888).copy()
                icon = QPixmap.fromImage(img)
            except Exception:
                icon = QPixmap(46, 62)
            it = QListWidgetItem(icon, f"{title}\n{sub}")
            it.setData(Qt.UserRole, (path, pno))
            self.list.addItem(it)
        self.empty.setVisible(not items)
        self.count.setText(f"{len(items)} 项" if items else "—")

    def current(self) -> tuple[str, int] | None:
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None


# ------------------------------------------------------------------ 后台任务
import threading

CANCEL = threading.Event()      # 全局取消标志（一次只跑一个任务）


class JobSignals(QObject):
    progress = Signal(int, int)
    done = Signal(object)      # dict / str 都行，别让 Qt 做类型转换
    failed = Signal(str)


class Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = JobSignals()
        import threading
        self.cancel_event = threading.Event()

    def run(self):
        try:
            def cb(done, total):
                if CANCEL.is_set() or self.cancel_event.is_set():
                    raise RuntimeError("已取消")
                self.signals.progress.emit(int(done), int(total))
            result = self.fn(cb)
            self.signals.done.emit(result or {})
        except Exception as e:  # noqa: BLE001
            if self.cancel_event.is_set():
                self.signals.failed.emit("已取消")
                return
            import traceback
            traceback.print_exc()
            self.signals.failed.emit(str(e))


def submit(fn, on_progress=None, on_done=None, on_fail=None) -> Job:
    job = Job(fn)
    if on_progress:
        job.signals.progress.connect(on_progress)
    if on_done:
        job.signals.done.connect(on_done)
    if on_fail:
        job.signals.failed.connect(on_fail)
    QThreadPool.globalInstance().start(job)
    return job
