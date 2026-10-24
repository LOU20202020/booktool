"""「书架」页：系列 → 卷（一本书）→ 产物。

这一页是移植时新写的，但和「格式转换」页一样走原程序自己的框架
（crumb / title / action_text / require_file / on_show / run / status），
由 main.py 插进 MainWindow.pages 与左侧导航。

数据来自 新的 ui/core 层/shelf（model / store / collect / thumbs），界面这一层不判断业务，
只把 Project 派生出来的状态画出来、把用户的动作写回 shelf.json。

规则：**每一本书必须属于一个系列**；不属于多卷系列的归到内置「单本」。
"""

from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.pages import SectionLabel
from ui.theme import INK, INK2, INK3, LINE, RED, SURFACE
from ui.widgets import Card, Hint

from ui import ui_kit as K
from core.shelf import collect as C
from core.shelf import thumbs as T
from core.shelf.model import (
    DEFAULT_SERIES_ID, DEFAULT_SERIES_NAME, KIND_LABELS, ST_BLOCKED, ST_DONE,
    ST_SKIP, ST_STALE, ST_TODO, STEPS, STEP_NAMES, Project, Series, Shelf,
)
from core.shelf.store import ShelfStore

STATE_COLOR = {
    ST_DONE: "#1E1B18",
    ST_STALE: "#B23A2E",
    ST_TODO: "#CFC6B6",
    ST_SKIP: "#A79D8F",
    ST_BLOCKED: "#DCD3C4",
}
STATUS_COLOR = {
    "定稿": "#1E1B18", "已打印": "#B23A2E", "已排版": "#6B6459",
    "已分割": "#6B6459", "已导入": "#7E7568", "缺原稿": "#B23A2E",
}


def _human(n: float) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.0f} MB"
    return f"{max(1, n // 1024):.0f} KB"


class _Steps(QWidget):
    """七步进度：固定节距、左对齐，用一条细线串起来，比铺满整行更像工序。"""

    PITCH = 84

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[tuple[int, str]] = []
        self.setFixedHeight(42)

    def set_project(self, proj: Project | None) -> None:
        self._rows = [] if proj is None else [(s, proj.step_state(s)[0]) for s in STEPS]
        self.update()

    def paintEvent(self, _ev) -> None:
        if not self._rows:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pitch, y = self.PITCH, 7
        p.setPen(QPen(QColor("#E7DFD0"), 1))
        p.drawLine(10, y, pitch * (len(self._rows) - 1) + 10, y)
        for i, (step, state) in enumerate(self._rows):
            cx = 10 + pitch * i
            color = QColor(STATE_COLOR.get(state, "#CFC5B2"))
            if state in (ST_TODO, ST_BLOCKED):
                p.setPen(QPen(color, 1.5))
                p.setBrush(QColor("#FBFAF7"))
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(color)
            p.drawEllipse(cx - 4, y - 4, 8, 8)
            f = QFont(self.font())
            f.setPointSizeF(7.8)
            p.setFont(f)
            p.setPen(QColor("#9A9082") if state in (ST_TODO, ST_BLOCKED) else QColor("#6B6154"))
            p.drawText(cx - pitch // 2, y + 13, pitch, 14, Qt.AlignHCenter, STEP_NAMES[step])


class ShelfPage(QWidget):
    crumb = "书籍制作工具 / 书架"
    title = "书架"
    action_text = "导入"

    def __init__(self, main=None, parent=None, store: ShelfStore | None = None) -> None:
        super().__init__(parent)
        self.main = main
        self.store = store or ShelfStore()
        self.shelf: Shelf = self.store.load()
        self._cur: Project | None = None
        self._loading = False
        self._collapsed: set[str] = set()
        self.setAcceptDrops(True)
        self._build()
        self.refresh()
        if self.store.recovered_from:
            self._say(self._recovery_note())

    # ── 页面契约 ───────────────────────────────────────────────────────
    def require_file(self) -> bool:
        return False

    always_ready = True          # 主按钮（导入）不需要先选文件

    def run(self) -> None:
        self.import_folder()

    def on_show(self) -> None:
        self.refresh()
        prim = getattr(self.main, "primary", None)
        if prim is not None:
            prim.setText(self.action_text)
            prim.setEnabled(True)
        self._say(f"书架 · {len(self.shelf.series)} 个系列 / {len(self.shelf.projects)} 本")

    def status(self, msg: str) -> None:
        self._say(msg)

    def _say(self, msg: str) -> None:
        setter = getattr(self.main, "set_status", None)
        if callable(setter):
            setter(msg)

    def _recovery_note(self) -> str:
        if self.store.recovered_from == "bak":
            return "书架数据损坏，已从备份恢复（上次保存的版本）"
        return "书架数据无法读取，已从空白重建（PDF 文件未受影响）"

    # ── 界面 ───────────────────────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 0)
        root.setSpacing(14)
        body = QHBoxLayout()
        body.setSpacing(14)

        # 左：系列 / 卷
        left = Card()
        left.setFixedWidth(368)
        lay = left.layout()
        lay.addWidget(SectionLabel("书架"))

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索书名 / 卷号")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_list)
        self.filter = QComboBox()
        self.filter.addItems(["全部", "待拼版", "已排版", "已打印", "定稿"])
        self.filter.setFixedWidth(88)
        self.filter.currentIndexChanged.connect(self.refresh_list)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.filter)
        lay.addLayout(bar)

        self.tree = K.make_tree()
        self.tree.setColumnCount(2)
        self.tree.setColumnWidth(0, 226)
        self.tree.setRootIsDecorated(False)
        self.tree.setItemsExpandable(False)
        self.tree.itemClicked.connect(self._on_click)
        self.tree.itemSelectionChanged.connect(self._on_select)
        self.tree.itemDoubleClicked.connect(lambda *_: self.open_book())
        lay.addWidget(self.tree, 1)

        self.empty_hint = Hint("书架还是空的\n把 PDF 拖进来，或点右下角「导入」选文件夹")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty_hint)
        body.addWidget(left)

        # 右：这本书
        right = Card()
        rlay = right.layout()

        top = QHBoxLayout()
        top.setSpacing(14)
        self.thumb = QLabel()
        self.thumb.setFixedSize(92, 130)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet(
            "QLabel{background:#FCFAF5;border:1px solid #E4DDD1;border-radius:6px;"
            f"color:{INK3};font-size:11px;}}"
        )
        self.thumb.setText("无预览")
        top.addWidget(self.thumb, 0, Qt.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(4)
        self.detail_head = QLabel("选一本书")
        f = QFont(self.detail_head.font())
        f.setPointSizeF(14.5)
        f.setBold(True)
        self.detail_head.setFont(f)
        self.detail_head.setObjectName("GroupTitle")
        col.addWidget(self.detail_head)

        self.detail_meta = QLabel("")
        self.detail_meta.setStyleSheet(f"color:{INK2};")
        col.addWidget(self.detail_meta)

        self.steps = _Steps()
        col.addWidget(self.steps)

        self.summary = QLabel("")
        self.summary.setStyleSheet(f"color:{INK3};font-size:11px;")
        col.addWidget(self.summary)
        col.addStretch(1)
        top.addLayout(col, 1)

        self.preview = QLabel()
        self.preview.setFixedSize(170, 226)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet(
            "QLabel{background:#FCFAF5;border:1px solid #E4DDD1;border-radius:6px;"
            f"color:{INK3};font-size:11px;}}"
        )
        self.preview.setText("预览")
        top.addWidget(self.preview, 0, Qt.AlignTop)
        rlay.addLayout(top)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color:{LINE};background:{LINE};max-height:1px;border:none;")
        rlay.addWidget(line)

        self.list_title = QLabel("产物")
        self.list_title.setObjectName("SectionLabel")
        rlay.addWidget(self.list_title)

        self.list_items = K.make_list()
        self.list_items.itemDoubleClicked.connect(self._open_item)
        self.list_items.currentItemChanged.connect(lambda *_: self._preview_selected())
        self.list_items.setMaximumHeight(6 * 34)
        rlay.addWidget(self.list_items)

        self.detail_foot = QLabel("")
        self.detail_foot.setStyleSheet(f"color:{INK3};font-size:11px;")
        rlay.addWidget(self.detail_foot)

        self.info = QLabel("")
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info.setStyleSheet(f"color:{INK3};font-size:11px;line-height:152%;")
        rlay.addWidget(self.info)
        rlay.addStretch(1)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.btn_open = self._btn("打开这本书", self.open_book, primary=True)
        self.btn_folder = self._btn("在文件夹中显示", self.reveal)
        self.btn_final = self._btn("设为定稿", self.toggle_final)
        self.btn_rescan = self._btn("重新扫描", self.rescan)
        for b in (self.btn_open, self.btn_folder, self.btn_final, self.btn_rescan):
            btns.addWidget(b)
        btns.addStretch(1)
        btns.addWidget(QLabel("系列"))
        self.series_box = QComboBox()
        self.series_box.setFixedWidth(140)
        self.series_box.setToolTip("这本书属于哪个系列（每本书必须有一个系列）")
        self.series_box.activated.connect(self._move_series)
        btns.addWidget(self.series_box)
        rlay.addLayout(btns)

        body.addWidget(right, 1)
        root.addLayout(body, 1)

    def _btn(self, text: str, slot, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumHeight(28)
        if primary:
            b.setObjectName("Primary")
        b.clicked.connect(slot)
        return b

    # ── 列表 ───────────────────────────────────────────────────────────
    def refresh(self) -> None:
        self.shelf = self.store.load()
        self.shelf.ensure_default_series()
        for p in self.shelf.projects:
            if not p.series_id or not self.shelf.series_by_id(p.series_id):
                p.series_id = DEFAULT_SERIES_ID
        self.refresh_list()
        self.refresh_series_box()
        has_any = bool(self.shelf.projects)
        self.tree.setVisible(has_any)
        self.empty_hint.setVisible(not has_any)

    def refresh_list(self) -> None:
        self._loading = True
        keep = self._cur.id if self._cur else None
        self.tree.clear()
        q = (self.search.text() or "").strip().lower()
        want = self.filter.currentText()

        for series in self.shelf.series:
            projs = [p for p in self.shelf.projects_of(series.id) if self._match(p, q, want)]
            if not projs:
                continue
            mark = "▸" if series.id in self._collapsed else "▾"
            top = QTreeWidgetItem([f"{mark} {series.name}", f"{len(projs)} 卷"])
            top.setFlags(top.flags() & ~Qt.ItemIsSelectable)
            top.setData(0, Qt.UserRole + 1, series.id)
            fb = QFont(self.tree.font())
            fb.setBold(True)
            top.setFont(0, fb)
            top.setForeground(0, QColor(INK2))
            top.setForeground(1, QColor(INK3))
            top.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            self.tree.addTopLevelItem(top)
            top.setExpanded(series.id not in self._collapsed)
            for p in projs:
                vol = f"第 {p.index} 卷" if p.index else p.name
                it = QTreeWidgetItem([vol, p.status])
                it.setData(0, Qt.UserRole, p.id)
                it.setForeground(1, QColor(STATUS_COLOR.get(p.status, INK2)))
                it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                it.setToolTip(0, os.path.basename(p.source.path) if p.source else p.name)
                top.addChild(it)
                if p.id == keep:
                    self.tree.setCurrentItem(it)
        self._loading = False
        self._auto_select()

    def _auto_select(self) -> None:
        """打开书架时默认选中第一本，别让右边空着；没内容就把占位控件藏掉。"""
        if self.tree.currentItem() is not None:
            return
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if top.childCount():
                self.tree.setCurrentItem(top.child(0))
                return
        self._cur = None
        self.info.setVisible(False)
        self.preview.setVisible(False)
        self.thumb.setVisible(False)
        self.steps.set_project(None)

    def _on_click(self, item, _col: int) -> None:
        sid = item.data(0, Qt.UserRole + 1)
        if not sid:
            return
        if sid in self._collapsed:
            self._collapsed.discard(sid)
        else:
            self._collapsed.add(sid)
        self.refresh_list()

    def _match(self, p: Project, q: str, want: str) -> bool:
        if q:
            hay = f"{p.name} {p.index or ''} " + (os.path.basename(p.source.path) if p.source else "")
            if q not in hay.lower():
                return False
        if want == "待拼版":
            return p.status in ("已导入", "已分割")
        if want == "已排版":
            return p.status == "已排版"
        if want == "已打印":
            return p.status == "已打印"
        if want == "定稿":
            return p.status == "定稿"
        return True

    def refresh_series_box(self) -> None:
        self.series_box.blockSignals(True)
        self.series_box.clear()
        for s in self.shelf.series:
            self.series_box.addItem(s.name, s.id)
        if self._cur:
            i = self.series_box.findData(self._cur.series_id)
            self.series_box.setCurrentIndex(max(0, i))
        self.series_box.blockSignals(False)

    # ── 选中 ───────────────────────────────────────────────────────────
    def _on_select(self) -> None:
        if self._loading:
            return
        it = self.tree.currentItem()
        pid = it.data(0, Qt.UserRole) if it else None
        if not pid:
            return
        proj = self.shelf.by_id(pid)
        if proj:
            self._cur = proj
            self._show_detail(proj)

    def _show_detail(self, p: Project) -> None:
        series = self.shelf.series_by_id(p.series_id)
        vol = f"第 {p.index} 卷" if p.index else ""
        self.detail_head.setText(f"{p.name}{('　' + vol) if vol else ''}")
        bits = [series.name if series else DEFAULT_SERIES_NAME, p.status]
        if p.source and p.source.pages:
            bits.append(f"{p.source.pages} 页")
        bits.append(_human(p.size_total))
        self.detail_meta.setText("　·　".join(str(b) for b in bits))
        self.steps.set_project(p)

        self.thumb.setPixmap(QPixmap())
        self.thumb.setText("无预览")
        if p.source and p.source.path.lower().endswith(".pdf"):
            path = T.thumb(p.source.path, width=200)
            if path:
                pm = QPixmap(path)
                if not pm.isNull():
                    self.thumb.setPixmap(
                        pm.scaled(QSize(90, 128), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    )
                    self.thumb.setText("")

        items = [i for i in p.items if i.exists]
        items.sort(key=lambda i: (i.kind not in ("body", "cover_src"), i.kind))
        dups = [i for i in items if i.kind == "dup"]
        items = [i for i in items if i.kind != "dup"]
        self.list_title.setText(f"产物（{len(items) + (1 if dups else 0)}）")
        self.list_items.clear()
        for it in items:
            label = KIND_LABELS.get(it.kind, "其它")
            pages = f"{it.pages} 页 · " if it.pages else ""
            star = "　★" if p.final and os.path.abspath(it.path) == os.path.abspath(p.final) else ""
            row = QListWidgetItem(f"  {label}　　{pages}{_human(it.size)}{star}")
            row.setData(Qt.UserRole, it.path)
            if star:
                row.setForeground(QColor("#6F7F52"))
            self.list_items.addItem(row)
        if dups:
            row = QListWidgetItem(
                f"  副本　　×{len(dups)}　　{_human(sum(d.size for d in dups))}"
            )
            row.setForeground(QColor("#A79C89"))
            row.setToolTip("同名的 -2/-3 副本，不参与拼版；清理时可以单独删")
            self.list_items.addItem(row)
        if not items and not dups:
            empty = QListWidgetItem("还没有产物 · 到小册子 / 封面 / 四堆叠页里做")
            empty.setFlags(Qt.NoItemFlags)
            self.list_items.addItem(empty)

        real = p.real_prints
        prints = len(real)
        last = real[-1].at.replace("T", " ")[5:16] if real else "—"
        sheets = sum(e.sheets for e in real)
        notes = []
        if p.overdue_final():
            notes.append("定稿可能过期")
        if p.missing:
            notes.append(f"失联 {len(p.missing)} 个文件")
        if p.final:
            notes.append("定稿 " + os.path.basename(p.final))
        self.detail_foot.setText(
            f"打印 {prints} 次" + (f" · 共 {sheets} 张纸" if sheets else "")
            + f" · 最近 {last}" + ("　·　" + "　·　".join(notes) if notes else "")
        )
        if real:
            tip = "\n".join(
                f"{e.at.replace('T', ' ')[5:16]}　{e.tag}　{e.sheets} 张"
                + (f"　{e.job}" if e.job else "") for e in real[-8:])
            self.detail_foot.setToolTip("打印记录（最近 8 次）\n" + tip)
        else:
            self.detail_foot.setToolTip("还没有真正打印过（只打样张不算）")
        rows = self.list_items.count()
        self.list_items.setFixedHeight(min(6 * 34, 34 * rows + 2))
        self.btn_final.setText("取消定稿" if p.final else "设为定稿")
        self._paint_preview(p.source.path if p.source else None, "预览")
        fmt = KIND_LABELS.get(self._cur_layout_kind(p), "")
        final_txt = "★ " + os.path.basename(p.final) if p.final else "未设"
        self.summary.setText(
            f"产物 {len(items)} 个" + (f"（{fmt}）" if fmt else "") + f"　·　定稿 {final_txt}"
        )

        src = p.source
        if src:
            folder = os.path.dirname(src.path)
            self.info.setText(
                f"原稿　{os.path.basename(src.path)}\n"
                f"位置　{folder}\n"
                f"创建　{p.created.replace('T', ' ')[:16]}　·　打开 {p.opened[:16] or '—'}"
            )
        else:
            self.info.setText("没有原稿记录")
        self.refresh_series_box()

    @staticmethod
    def _cur_layout_kind(p: Project) -> str:
        it = p.layout_item()
        return it.kind if it else ""

    def _paint_preview(self, pdf: str | None, hint: str = "预览") -> None:
        self.preview.setPixmap(QPixmap())
        self.preview.setText(hint)
        if not pdf or not os.path.exists(pdf) or not pdf.lower().endswith(".pdf"):
            return
        path = T.thumb(pdf, width=420)
        if not path:
            return
        pm = QPixmap(path)
        if pm.isNull():
            return
        self.preview.setPixmap(
            pm.scaled(QSize(168, 224), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self.preview.setText("")

    def _preview_selected(self) -> None:
        row = self.list_items.currentItem()
        path = row.data(Qt.UserRole) if row else None
        if path:
            self._paint_preview(path, "无法预览")
        elif self._cur and self._cur.source:
            self._paint_preview(self._cur.source.path, "预览")

    # ── 动作 ───────────────────────────────────────────────────────────
    def open_book(self) -> None:
        if not self._cur or not self._cur.source:
            return
        path = self._cur.source.path
        if not os.path.exists(path):
            self._say("原稿不在了：" + path)
            return
        setter = getattr(self.main, "set_current_doc", None)
        if callable(setter):
            setter(path)
        goto = getattr(self.main, "goto", None)
        pages = getattr(self.main, "pages", [])
        pipe = getattr(self.main, "_pipeline_page", None)
        idx = next((i for i, pg in enumerate(pages) if type(pg).__name__ == "PipelinePage"), None)
        if pipe is not None and idx is not None:
            pipe.set_project(self._cur.id)
            if callable(goto):
                goto(idx)
            self._say(f"已打开生产线：{os.path.basename(path)}")
            return
        idx = next((i for i, pg in enumerate(pages) if type(pg).__name__ == "BookletPage"), None)
        if callable(goto) and idx is not None:
            goto(idx)
        self._say(f"已打开：{os.path.basename(path)}")

    def reveal(self) -> None:
        target = self._cur.source.path if self._cur and self._cur.source else ""
        if target and os.path.exists(target):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(target)))
        else:
            self._say("找不到原稿所在文件夹")

    def _open_item(self, row: QListWidgetItem) -> None:
        path = row.data(Qt.UserRole)
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def toggle_final(self) -> None:
        if not self._cur:
            return
        if self._cur.final:
            self._cur.set_final(None)
            self._say("已取消定稿")
        else:
            chosen = self.list_items.currentItem()
            path = chosen.data(Qt.UserRole) if chosen else None
            if not path and self._cur.items:
                path = self._cur.items[-1].path
            if not path:
                self._say("这本书还没有产物，不能设为定稿")
                return
            self._cur.set_final(path)
            self._say("已设为定稿：" + os.path.basename(path))
        self._save()
        self._show_detail(self._cur)
        self.refresh_list()

    def rescan(self) -> None:
        if not self._cur:
            return
        n = C.scan_products(self._cur)
        self._save()
        self._show_detail(self._cur)
        self._say(f"重新扫描：识别到 {n} 个产物")

    def _move_series(self, index: int) -> None:
        if not self._cur:
            return
        sid = self.series_box.itemData(index)
        if not sid or sid == self._cur.series_id:
            return
        self._cur.series_id = sid
        s = self.shelf.series_by_id(sid)
        self._save()
        self.refresh_list()
        self._show_detail(self._cur)
        self._say(f"已移到系列「{s.name if s else sid}」")

    # ── 导入 ───────────────────────────────────────────────────────────
    def import_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选一个文件夹（文件夹名会成为一个系列）")
        if folder:
            self.add_folder(folder)

    def add_folder(self, folder: str) -> int:
        name = C.clean_name(os.path.basename(folder.rstrip(os.sep))) or "新系列"
        series = next((s for s in self.shelf.series if s.name == name), None)
        if series is None:
            series = Series(id="s-" + name, name=name)
            self.shelf.series.append(series)
        projs = C.import_folder(folder)
        if not projs:
            self._say("这个文件夹里没有可导入的书")
            return 0
        for p in projs:
            p.series_id = series.id
            self.shelf.add_project(p)
        self._save()
        self.refresh()
        self._say(f"已导入 {len(projs)} 本到系列「{name}」")
        return len(projs)

    def add_files(self, paths: list[str]) -> int:
        self.shelf.ensure_default_series()
        n = 0
        for path in paths:
            self.shelf.add_project(C.project_from_file(path, series_id=DEFAULT_SERIES_ID))
            n += 1
        if n:
            self._save()
            self.refresh()
            self._say(f"已导入 {n} 本到「{DEFAULT_SERIES_NAME}」")
        return n

    def _save(self) -> None:
        try:
            self.store.save(self.shelf)
        except Exception as exc:                      # noqa: BLE001
            self._say(f"书架保存失败：{exc}")

    # ── 拖放 ───────────────────────────────────────────────────────────
    def dragEnterEvent(self, ev) -> None:
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        files, folders = [], []
        for url in ev.mimeData().urls():
            p = url.toLocalFile()
            (folders if os.path.isdir(p) else files).append(p)
        total = 0
        for f in folders:
            total += self.add_folder(f)
        if files:
            total += self.add_files(files)
        if not total:
            self._say("拖进来的东西里没有可导入的书")
