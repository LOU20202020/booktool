"""「格式转换」页：MOBI / AZW3 / EPUB → PDF。

这一页是移植时新写的（原程序那七页在 app/ui 里是编译好的字节码），
但走的是原程序自己的框架：继承同样的页面契约（crumb / title / action_text /
require_file() / on_show() / run() / status()），由 main.py 追加进
`MainWindow.pages` 与页面栈，并挂到左侧导航的 QButtonGroup 上 ——
所以顶部标题、底部「开始转换」主按钮、状态栏文案全都由主窗口原生接管，
不需要自己画一条动作栏。

版式沿用原程序：左 ScrollArea 里一叠 Card（SectionLabel 打头）、
中间 Panel + PreviewView（网格画布）、右侧 214 宽 Panel 列目录。

转换后端见 core/convert.py（Calibre 的 ebook-convert）。
"""

from __future__ import annotations

import os
import threading

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.pages import SectionLabel
from ui.theme import INK, INK2, INK3, RED
from ui.widgets import Card, ChipGroup, Hint, PreviewView

from core import convert as C

FILTER = "电子书 (" + " ".join("*" + e for e in C.SUPPORTED_EXT) + ");;所有文件 (*)"


class _Worker(QThread):
    progressed = Signal(float, str)
    ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, src: str, opts: dict, cancel: threading.Event, parent=None):
        super().__init__(parent)
        self.src = src
        self.opts = opts
        self.cancel = cancel

    def run(self) -> None:  # noqa: D401
        try:
            res = C.convert(
                self.src,
                progress=lambda f, t: self.progressed.emit(f, t),
                should_stop=self.cancel.is_set,
                **self.opts,
            )
            self.ok.emit(res)
        except Exception as err:  # noqa: BLE001
            self.failed.emit(str(err))


class _CoverWorker(QThread):
    """后台读封面图（ebook-meta 只读元数据，很快；大 mobi 也不卡界面）。"""

    done = Signal(str)

    def __init__(self, src: str, parent=None) -> None:
        super().__init__(parent)
        self.src = src

    def run(self) -> None:  # noqa: D401
        try:
            self.done.emit(C.cover_image(self.src))
        except Exception:                       # noqa: BLE001
            self.done.emit("")


class _Canvas(PreviewView):
    """预览画布。

    PreviewView 自己在 drawForeground 里画了一句「把 PDF 拖进来…」的提示，
    本页有自己的提示文案（浮在网格中央），所以把那句盖掉，只留网格。
    """

    def drawForeground(self, *args, **kwargs) -> None:  # noqa: D401,N802
        return


def _row(label: str, widget: QWidget) -> QHBoxLayout:
    """一行「小标题 + 控件」，与原程序左侧参数行同一套间距。"""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    lab = QLabel(label)
    lab.setStyleSheet(f"color:{INK2}; font-size:12px;")
    lab.setFixedWidth(56)
    row.addWidget(lab)
    row.addWidget(widget, 1)
    return row


class ConvertPage(QWidget):
    """格式转换页。main 是主窗口，页面契约与原程序的 ToolPage 保持一致。"""

    # 原程序 _switch() 读这三个类属性来设置顶部标题和主按钮文案
    crumb = "书籍制作工具 / 转换"
    title = "格式转换"
    action_text = "开始转换"
    pick_hint = "先选一本电子书（MOBI / EPUB / AZW3 / TXT …）"

    def __init__(self, main=None, parent=None) -> None:
        super().__init__(parent)
        self.main = main
        self.src = ""
        self.out = ""
        self._worker: _Worker | None = None
        self._cover_worker: _CoverWorker | None = None
        self._cancel = threading.Event()
        self.setAcceptDrops(True)
        self._build()
        self._sync_kind()
        self._sync_backend()
        from ui.dnd import forward_drops
        forward_drops(self)          # 预览画布的 viewport 会抢拖放，转回本页处理

    # ── 页面契约（供 MainWindow._switch / _run 调用）─────────────────────
    def require_file(self) -> bool:
        return bool(self.src)

    def run(self) -> None:
        self.start()

    def on_show(self) -> None:
        prim = getattr(self.main, "primary", None)
        if prim is not None:
            prim.setText(self.action_text)
            prim.setEnabled(not (self._worker and self._worker.isRunning()))
        self._sync_backend()
        if not C.available():
            self._say(C.missing_hint())
        else:
            self._say("就绪，点「开始转换」" if self.src
                      else "选一个电子书文件（也可以直接拖进窗口）")

    def status(self, msg: str) -> None:
        self._say(msg)

    def _say(self, msg: str) -> None:
        setter = getattr(self.main, "set_status", None)
        if callable(setter):
            setter(msg)

    # ── 界面 ────────────────────────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 6, 16, 0)
        root.setSpacing(12)

        body = QHBoxLayout()
        body.setSpacing(14)

        # 左栏：源文件 + 输出设置（整栏可滚动）
        left_inner = QWidget()
        left = QVBoxLayout(left_inner)
        left.setContentsMargins(0, 0, 8, 8)
        left.setSpacing(10)

        card_src = Card()
        card_src.layout().addWidget(SectionLabel("源文件"))
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(10)
        self.badge = QLabel("电子书")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedSize(42, 50)
        self.badge.setStyleSheet(
            f"border:1.5px solid {RED}; border-radius:5px; color:{RED};"
            "font-size:10px; font-weight:700;"
        )
        head.addWidget(self.badge, 0, Qt.AlignTop)
        name_col = QVBoxLayout()
        name_col.setContentsMargins(0, 0, 0, 0)
        name_col.setSpacing(2)
        self.src_name = QLabel("把电子书拖进来，或点下面的「选择」")
        self.src_name.setWordWrap(True)
        self.src_name.setStyleSheet(f"color:{INK}; font-size:12.5px; font-weight:600;")
        self.src_meta = QLabel("MOBI / AZW3 / EPUB / FB2 / TXT")
        self.src_meta.setObjectName("Hint")
        self.src_meta.setWordWrap(True)
        name_col.addWidget(self.src_name)
        name_col.addWidget(self.src_meta)
        head.addLayout(name_col, 1)
        card_src.layout().addLayout(head)
        self.btn_pick = QPushButton("选择")
        self.btn_pick.clicked.connect(self._pick)
        card_src.layout().addWidget(self.btn_pick)

        # 转换引擎（Calibre）在不在，就写在这里，别让用户猜为什么转不动
        self.calibre_hint = QLabel("")
        self.calibre_hint.setWordWrap(True)
        card_src.layout().addWidget(self.calibre_hint)
        left.addWidget(card_src)

        card_opt = Card()
        card_opt.layout().addWidget(SectionLabel("输出设置"))
        self.chip_paper = ChipGroup(["A5", "A4", "B6"])
        self.chip_paper.set_index(0)
        card_opt.layout().addLayout(_row("纸张", self.chip_paper))

        self.chip_kind = ChipGroup(["文字书", "漫画"])
        self.chip_kind.set_index(0)
        self.chip_kind.changed.connect(lambda *_: self._sync_kind())
        card_opt.layout().addLayout(_row("书型", self.chip_kind))

        self.chip_font = ChipGroup(["宋体", "黑体"])
        self.chip_font.set_index(0)
        card_opt.layout().addLayout(_row("字体", self.chip_font))

        size_box = QWidget()
        sb = QHBoxLayout(size_box)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(6)
        minus = QPushButton("−")
        minus.setObjectName("StepBtn")
        minus.setFixedSize(28, 26)
        plus = QPushButton("+")
        plus.setObjectName("StepBtn")
        plus.setFixedSize(28, 26)
        self.size_value = 11
        self.size_label = QLabel("11 pt")
        self.size_label.setAlignment(Qt.AlignCenter)
        self.size_label.setFixedWidth(56)
        minus.clicked.connect(lambda: self._step_size(-1))
        plus.clicked.connect(lambda: self._step_size(+1))
        sb.addWidget(minus)
        sb.addWidget(self.size_label)
        sb.addWidget(plus)
        sb.addStretch(1)
        self.size_box = size_box
        card_opt.layout().addLayout(_row("字号", size_box))

        self.chip_margin = ChipGroup(["窄", "中", "宽"])
        self.chip_margin.set_index(1)
        card_opt.layout().addLayout(_row("页边距", self.chip_margin))

        self.cb_numbers = QCheckBox("页脚页码")
        self.cb_numbers.setChecked(True)
        self.cb_break = QCheckBox("章节另起一页")
        self.cb_break.setChecked(True)
        for cb in (self.cb_numbers, self.cb_break):
            cb.setStyleSheet(f"color:{INK2}; font-size:12px;")
            card_opt.layout().addWidget(cb)
        left.addWidget(card_opt)

        card_tip = Card()
        card_tip.layout().addWidget(SectionLabel("提示"))
        self.tip = Hint("提示：文字书可调字体/字号/页边距，页码与章节分页在下面的开关里。")
        self.tip.setWordWrap(True)
        card_tip.layout().addWidget(self.tip)
        left.addWidget(card_tip)
        left.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(left_inner)
        scroll.setFixedWidth(372)
        body.addWidget(scroll)

        # 中间：预览画布（网格由 PreviewView 自己画，没内容时也画；提示文字浮在网格上）
        panel = QFrame()
        panel.setObjectName("Panel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(10, 10, 10, 6)
        pl.setSpacing(6)
        self.preview = _Canvas()
        self.placeholder = QLabel("选一个电子书文件，转出来的第一页在这里预览")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setObjectName("Hint")
        self.placeholder.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.placeholder.setStyleSheet("background: transparent;")
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(self.preview, 0, 0)
        grid.addWidget(self.placeholder, 0, 0, Qt.AlignCenter)  # 浮在画布中央
        pl.addWidget(holder, 1)

        result_row = QHBoxLayout()
        result_row.setContentsMargins(0, 0, 0, 0)
        self.preview_hint = QLabel("—")
        self.preview_hint.setObjectName("Hint")
        result_row.addWidget(self.preview_hint, 1)
        self.btn_open = QPushButton("打开结果")
        self.btn_open.clicked.connect(self._open)
        self.btn_open.setEnabled(False)
        self.btn_go = QPushButton("去拼版 →")
        self.btn_go.clicked.connect(self._go_impose)
        self.btn_go.setEnabled(False)
        result_row.addWidget(self.btn_open)
        result_row.addWidget(self.btn_go)
        pl.addLayout(result_row)
        body.addWidget(panel, 1)

        # 右：目录
        side = QFrame()
        side.setObjectName("Panel")
        sl = QVBoxLayout(side)
        sl.setContentsMargins(10, 10, 10, 8)
        sl.setSpacing(6)
        head_row = QHBoxLayout()
        head_row.setContentsMargins(0, 0, 0, 0)
        side_title = QLabel("目录")
        side_title.setStyleSheet(f"color:{INK}; font-size:13px;")
        self.toc_count = QLabel("—")
        self.toc_count.setObjectName("Hint")
        head_row.addWidget(side_title)
        head_row.addStretch(1)
        head_row.addWidget(self.toc_count)
        sl.addLayout(head_row)
        self.toc = QListWidget()
        self.toc.setFrameShape(QFrame.NoFrame)
        sl.addWidget(self.toc, 1)
        self.toc_empty = Hint("转换完成后在这里列出章节")
        sl.addWidget(self.toc_empty)
        side.setFixedWidth(214)
        body.addWidget(side)

        root.addLayout(body, 1)

    # ── 交互 ────────────────────────────────────────────────────────────
    def _sync_backend(self) -> None:
        """把「Calibre 装没装」直接写在源文件卡里。"""
        if C.available():
            self.calibre_hint.setObjectName("Hint")
            self.calibre_hint.setText("转换引擎已就绪：Calibre")
            self.calibre_hint.setStyleSheet(f"color:{INK3};font-size:11px;")
        else:
            self.calibre_hint.setObjectName("Hint")
            self.calibre_hint.setText(
                "还没装 Calibre。转换用的是它的免费命令行工具 ebook-convert："
                "去 calibre-ebook.com 下载安装（默认装到 Program Files\Calibre2），"
                "装完重开本程序，这里会显示「已就绪」。")
            self.calibre_hint.setStyleSheet(f"color:{RED};font-size:11px;")

    def _sync_kind(self) -> None:
        comic = self.chip_kind.index() == 1
        for w in (self.chip_font, self.size_box, self.chip_margin, self.cb_numbers, self.cb_break):
            if w is None:
                continue
            w.setEnabled(not comic)
            # 主题样式表没有 :disabled 态，光 setEnabled 看不出来，补一层淡出
            if comic:
                eff = QGraphicsOpacityEffect(w)
                eff.setOpacity(0.38)
                w.setGraphicsEffect(eff)
            else:
                w.setGraphicsEffect(None)
        self.tip.setText(
            "提示：漫画整页是图片，边距自动归零、不加页码，转完按原比例铺满纸面。"
            if comic
            else "提示：文字书可调字体/字号/页边距，页码与章节分页在下面的开关里。"
        )

    def _step_size(self, delta: int) -> None:
        self.size_value = max(8, min(16, self.size_value + delta))
        self.size_label.setText(f"{self.size_value} pt")

    def _pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择电子书", os.path.expanduser("~/Downloads"), FILTER
        )
        if path:
            self.set_source(path)

    def set_source(self, path: str) -> None:
        path = os.path.abspath(path)
        self.src = path
        size = os.path.getsize(path) if os.path.exists(path) else 0
        ext = os.path.splitext(path)[1].lstrip(".").upper() or "书"
        self.badge.setText(ext[:4])
        self.src_name.setText(os.path.basename(path))
        self.src_meta.setText(
            f"{ext} · {size / 1024 / 1024:.1f} MB"
            + ("" if C.accepts(path) else "　⚠ 不在支持列表里")
        )
        self.preview.clear_image()
        self.placeholder.setText("正在读取封面…")
        self.placeholder.show()
        self.preview_hint.setText("—")
        self._load_cover(path)
        self._say("就绪，点「开始转换」" if C.available() else C.missing_hint())
        prim = getattr(self.main, "primary", None)
        if prim is not None:
            if C.available():
                prim.setText(self.action_text)
                prim.setEnabled(True)
            else:
                prim.setEnabled(False)
        # 拖文件进来时主窗口还停在"没选文件"的状态，要让它重算一次按钮
        refresh = getattr(self.main, "refresh_action_state", None)
        if callable(refresh):
            refresh()

    def _load_cover(self, path: str) -> None:
        """先给一张封面预览，让人确认没选错书；没有封面就说明转完看第 1 页。

        连着换文件时每次都开一个新线程，结果按来源路径过滤——旧的那次回来就直接丢掉，
        免得"上一个文件的封面"盖到新文件上。
        """
        worker = _CoverWorker(path, self)
        worker.done.connect(lambda img, src=path: self._on_cover(img, src))
        self._cover_worker = worker
        worker.start()

    def _on_cover(self, image_path: str, src: str = "") -> None:
        if src and self.src and os.path.abspath(src) != os.path.abspath(self.src):
            return                       # 已经换书了，这张封面过期
        pix = QPixmap(image_path) if image_path else QPixmap()
        if pix.isNull():
            self.placeholder.setText("这本书没有封面图——点「开始转换」，转完在这里看第 1 页")
            self.placeholder.show()
            return
        self.preview.set_image(pix)
        self.placeholder.hide()
        self.preview_hint.setText("封面预览　·　转换完成后这里显示第 1 页")

    def start(self) -> None:
        if not self.src:
            self._pick()
            return
        if self._worker is not None and self._worker.isRunning():
            return
        if not C.available():
            self._say(C.missing_hint())
            return
        opts = {
            "paper": ["A5", "A4", "B6"][self.chip_paper.index()],
            "kind": ["文字书", "漫画"][self.chip_kind.index()],
            "font": ["宋体", "黑体"][self.chip_font.index()],
            "font_size": self.size_value,
            "margin": ["窄", "中", "宽"][self.chip_margin.index()],
            "page_numbers": self.cb_numbers.isChecked(),
            "chapter_break": self.cb_break.isChecked(),
        }
        self._cancel.clear()
        prim = getattr(self.main, "primary", None)
        if prim is not None:
            prim.setEnabled(False)
        self.btn_open.setEnabled(False)
        self.btn_go.setEnabled(False)
        self._say("转换中…（大文件要一两分钟）")
        self._worker = _Worker(self.src, opts, self._cancel, self)
        self._worker.progressed.connect(self._on_progress)
        self._worker.ok.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_progress(self, frac: float, note: str) -> None:
        self._say(f"转换中 {int(frac * 100)}%　{note}")

    def _on_done(self, res: dict) -> None:
        self.out = res.get("out", "")
        prim = getattr(self.main, "primary", None)
        if prim is not None:
            prim.setEnabled(True)
            prim.setText("重新转换")
        self.btn_open.setEnabled(bool(self.out))
        self.btn_go.setEnabled(bool(self.out))
        bits = [f"{res.get('pages', 0)} 页", res.get("size_text", "")]
        if res.get("bookmarks"):
            bits.append(f"目录 {res['bookmarks']} 条")
        self._say("完成：" + " · ".join(b for b in bits if b))
        try:
            info = C.probe(self.out)
            if info["png"]:
                pix = QPixmap()
                if pix.loadFromData(info["png"], "PNG"):
                    self.preview.set_image(pix)
                    self.placeholder.hide()
            w_mm, h_mm = info.get("size_mm", (0, 0))
            self.preview_hint.setText(
                f"第 1 面　共 {info['pages']} 页　{w_mm}×{h_mm} mm" if info["pages"] else "—"
            )
            toc = info.get("toc") or []
            self.toc.clear()
            for _lvl, t, _page in toc[:400]:
                QListWidgetItem(t, self.toc)
            self.toc_count.setText(f"共 {len(toc)} 条" if toc else "—")
            self.toc_empty.setText("这本书没有书签目录（漫画常见）" if not toc else "")
        except Exception:
            pass

    def _on_fail(self, msg: str) -> None:
        prim = getattr(self.main, "primary", None)
        if prim is not None:
            prim.setEnabled(True)
        self._say(f"失败：{msg}")

    def _open(self) -> None:
        if self.out:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.out))

    def _open_dir(self) -> None:
        if self.out:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.out)))

    def _go_impose(self) -> None:
        if not self.out:
            return
        win = self.main
        if win is not None:
            try:
                win.set_current_doc(self.out)
                win.goto(0)  # 0 = 小册子页；主窗口会同时更新标题与导航选中态
                return
            except Exception:
                pass
        self._open_dir()

    # ── 拖文件进来 ──────────────────────────────────────────────────────
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile() and C.accepts(url.toLocalFile()):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile() and C.accepts(url.toLocalFile()):
                self.set_source(url.toLocalFile())
                event.acceptProposedAction()
                return
        event.ignore()
