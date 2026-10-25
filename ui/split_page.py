"""「分割」工具页：把一本 PDF 拆成「封面素材 + 正文」。

替换原程序的「分拆」页。中间用原程序同一块网格画布（PreviewView）显示原稿，
可以翻页查看，边看边定「前 N 页算封面、末尾 M 页丢掉」。

外观沿用原程序：页面留白 18/16/18/0、卡片 Card、列表 #FCFAF5、参数行 84px 标签 + Stepper。
"""

from __future__ import annotations

import os

from PySide6.QtCore import QSize, QThread, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QWidget,
)

from ui.theme import INK2, INK3, RED
from ui.widgets import Card, Hint

from ui import cover_link as CL
from core import pipeline as P
from ui import ui_kit as K
from ui.preview_kit import GridCanvas, page_count, render_page
from core.shelf.store import ShelfStore


class _Worker(QThread):
    """分割是纯文件活（大 PDF 要几秒），放后台跑，界面不会假死。"""

    done = Signal(dict)
    failed = Signal(str)

    def __init__(self, src: str, front: int, tail: int, parent=None) -> None:
        super().__init__(parent)
        self.src, self.front, self.tail = src, front, tail

    def run(self) -> None:  # noqa: D401
        try:
            self.done.emit(P.split_pdf(self.src, front=self.front, tail=self.tail))
        except Exception as exc:                      # noqa: BLE001
            self.failed.emit(str(exc))


class SplitToolPage(QWidget):
    crumb = "书籍制作工具 / 分割"
    title = "分割"
    action_text = "开始分割"

    def __init__(self, main=None, parent=None) -> None:
        super().__init__(parent)
        self.main = main
        self.src = ""
        self.out: dict = {}
        self.page = 0
        self._worker: _Worker | None = None
        self._thumbs: dict[int, QPixmap] = {}   # 右侧页列表的小图
        self._pages: dict[int, QPixmap] = {}    # 主预览的高清图
        self.setAcceptDrops(True)
        self._build()
        from ui.dnd import forward_drops
        forward_drops(self)          # 预览画布会抢拖放，转回本页处理
        self._refresh_all()

    # ── 页面契约 ───────────────────────────────────────────────────────
    def require_file(self) -> bool:
        return bool(self.src)

    def run(self) -> None:
        self.start()

    def on_show(self) -> None:
        if not self.src:
            doc = getattr(self.main, "_doc", None)
            if isinstance(doc, (str, os.PathLike)) and str(doc).lower().endswith(".pdf") \
                    and os.path.exists(str(doc)):
                self.set_source(str(doc))
            else:                       # 没当前文稿时，用书架里最近打开的那本
                src = self._recent_source()
                if src:
                    self.set_source(src)
        prim = getattr(self.main, "primary", None)
        if prim is not None:
            prim.setText(self.action_text)
            prim.setEnabled(True)
        self._say(f"已载入 {os.path.basename(self.src)}" if self.src
                  else "选一个 PDF，一边翻页一边定分割位置")

    def status(self, msg: str) -> None:
        self._say(msg)

    def _say(self, msg: str) -> None:
        setter = getattr(self.main, "set_status", None)
        if callable(setter):
            setter(msg)

    def set_source(self, path: str) -> None:
        if not path or not os.path.exists(path):
            return
        self.src = os.path.abspath(path)
        self.lbl_src.setText(os.path.basename(self.src))
        self.lbl_src.setToolTip(self.src)
        self.page = 0
        self._thumbs.clear()
        self._pages.clear()
        self.out = {}
        self._build_page_grid()
        self._refresh_all()
        prim = getattr(self.main, "primary", None)
        if prim is not None:
            prim.setText(self.action_text)
            prim.setEnabled(True)
        refresh = getattr(self.main, "refresh_action_state", None)
        if callable(refresh):
            refresh()

    # ── 界面 ───────────────────────────────────────────────────────────
    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 0)
        root.setSpacing(14)

        # 左：源文件 + 分割参数
        left = Card()
        left.setFixedWidth(360)
        lay = left.layout()
        lay.addWidget(K.SectionLabel("源文件"))
        pick = QHBoxLayout()
        pick.setSpacing(8)
        self.lbl_src = QLabel("还没选文件")
        self.lbl_src.setStyleSheet(f"color:{INK3};")
        self.lbl_src.setWordWrap(True)
        pick.addWidget(self.lbl_src, 1)
        btn = K.plain_btn("选择…")
        btn.setMinimumHeight(28)
        btn.clicked.connect(self.pick_file)
        pick.addWidget(btn)
        lay.addLayout(pick)

        lay.addWidget(K.SectionLabel("分割方式"))
        self.sp_front = K.stepper(2, 0, 60, on_change=self._on_param)
        self.sp_tail = K.stepper(1, 0, 60, on_change=self._on_param)
        lay.addLayout(K.row("前 N 页=封面", self.sp_front))
        lay.addLayout(K.row("末尾 M 页=封底", self.sp_tail))
        self.lbl_calc = QLabel("")
        self.lbl_calc.setStyleSheet(f"color:{INK2};")
        lay.addWidget(self.lbl_calc)

        lay.addWidget(K.SectionLabel("按当前页取位置"))
        self.btn_body_first = K.plain_btn("此页设为正文第 1 页")
        self.btn_body_first.setMinimumHeight(28)
        self.btn_body_first.clicked.connect(self._set_body_start)
        self.btn_body_last = K.plain_btn("此页设为正文末页（其后作封底）")
        self.btn_body_last.setMinimumHeight(28)
        self.btn_body_last.clicked.connect(self._set_body_end)
        lay.addWidget(self.btn_body_first)
        lay.addWidget(self.btn_body_last)

        lay.addWidget(Hint("封面和封底都会另存成素材，交给「封面」页合成一张展开图；"
                           "正文是新的起点，加页码和排版都基于它，不再动原件。"))
        lay.addStretch(1)
        root.addWidget(left)

        # 中：网格画布 + 翻页
        mid = Card()
        ml = mid.layout()
        head = QHBoxLayout()
        head.addWidget(K.SectionLabel("原稿预览"))
        head.addStretch(1)
        self.lbl_total = QLabel("")
        self.lbl_total.setStyleSheet(f"color:{INK3};font-size:11px;")
        head.addWidget(self.lbl_total)
        ml.addLayout(head)

        stage = QHBoxLayout()
        stage.setSpacing(10)
        self.view = GridCanvas()
        self.view.setMinimumHeight(360)
        stage.addWidget(self.view, 1)

        self.pages_list = QListWidget()
        self.pages_list.setViewMode(QListWidget.IconMode)
        self.pages_list.setIconSize(QSize(48, 68))
        self.pages_list.setGridSize(QSize(64, 94))
        self.pages_list.setResizeMode(QListWidget.Adjust)
        self.pages_list.setMovement(QListWidget.Static)
        self.pages_list.setSpacing(3)
        self.pages_list.setUniformItemSizes(True)
        self.pages_list.setWordWrap(False)
        self.pages_list.setFixedWidth(212)
        self.pages_list.setStyleSheet(
            "QListWidget{background:#FCFAF5;border:1px solid #E4DDD1;border-radius:6px;"
            "outline:0;font-size:9pt;}"
            "QListWidget::item{color:#6B6459;border-radius:4px;padding:2px;}"
            "QListWidget::item:selected{background:#F3E3DF;color:#1E1B18;}"
        )
        self.pages_list.itemClicked.connect(
            lambda it: self.goto_page(self.pages_list.row(it)))
        stage.addWidget(self.pages_list)
        ml.addLayout(stage, 1)

        nav = QHBoxLayout()
        nav.setSpacing(8)
        self.btn_prev = K.plain_btn("◀")
        self.btn_prev.setFixedWidth(34)
        self.btn_prev.setMinimumHeight(26)
        self.btn_prev.clicked.connect(lambda: self.goto_page(self.page - 1))
        self.btn_next = K.plain_btn("▶")
        self.btn_next.setFixedWidth(34)
        self.btn_next.setMinimumHeight(26)
        self.btn_next.clicked.connect(lambda: self.goto_page(self.page + 1))
        self.lbl_page = QLabel("第 — / — 页")
        self.lbl_page.setStyleSheet(f"color:{INK2};")
        self.lbl_page.setMinimumWidth(96)
        self.lbl_page.setAlignment(Qt.AlignCenter)
        self.btn_cover = K.plain_btn("看封面页")
        self.btn_cover.setMinimumHeight(26)
        self.btn_cover.clicked.connect(lambda: self.goto_page(0))
        self.btn_body = K.plain_btn("看正文首页")
        self.btn_body.setMinimumHeight(26)
        self.btn_body.clicked.connect(lambda: self.goto_page(int(self.sp_front.value())))
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.lbl_page)
        nav.addWidget(self.btn_next)
        nav.addStretch(1)
        nav.addWidget(self.btn_cover)
        nav.addWidget(self.btn_body)
        ml.addLayout(nav)

        self.lbl_map = QLabel("")
        self.lbl_map.setStyleSheet(f"color:{INK3};font-size:11px;")
        ml.addWidget(self.lbl_map)
        root.addWidget(mid, 1)

        # 右：结果
        right = Card()
        right.setFixedWidth(268)
        rl = right.layout()
        rl.addWidget(K.SectionLabel("结果"))
        self.list_out = K.make_list()
        self.list_out.setMaximumHeight(104)
        self.list_out.itemDoubleClicked.connect(self._open_row)
        rl.addWidget(self.list_out)
        rl.addStretch(1)
        self.btn_pick_cover = K.plain_btn("选封面图…")
        self.btn_pick_cover.setMinimumHeight(28)
        self.btn_pick_cover.clicked.connect(lambda: self.to_cover("cover"))
        self.btn_pick_cover.setEnabled(False)
        rl.addWidget(self.btn_pick_cover)

        self.btn_pick_back = K.plain_btn("选封底图…")
        self.btn_pick_back.setMinimumHeight(28)
        self.btn_pick_back.clicked.connect(lambda: self.to_cover("back"))
        self.btn_pick_back.setEnabled(False)
        rl.addWidget(self.btn_pick_back)
        self.btn_dir = K.plain_btn("打开所在文件夹")
        self.btn_dir.setMinimumHeight(28)
        self.btn_dir.clicked.connect(self._open_out_dir)
        self.btn_dir.setEnabled(False)
        rl.addWidget(self.btn_dir)
        root.addWidget(right)

    # ── 预览与计算 ─────────────────────────────────────────────────────
    def _total(self) -> int:
        return page_count(self.src) if self.src else 0

    def goto_page(self, page: int) -> None:
        total = self._total()
        if not total:
            return
        self.page = max(0, min(total - 1, int(page)))
        self._show_page(self.page)
        self._refresh_labels()
        if self.pages_list.count() == total:
            self.pages_list.blockSignals(True)
            self.pages_list.setCurrentRow(self.page)
            for i in range(self.pages_list.count()):     # 当前页加粗，一眼定位
                it = self.pages_list.item(i)
                f = it.font()
                f.setBold(i == self.page)
                it.setFont(f)
            self.pages_list.scrollToItem(self.pages_list.item(self.page),
                                         QListWidget.EnsureVisible)
            self.pages_list.blockSignals(False)

    def _build_page_grid(self) -> None:
        """右侧列出所有页面（小缩略图），点一下主预览跳过去。"""
        self.pages_list.clear()
        total = self._total()
        self.lbl_total.setText(f"共 {total} 页" if total else "")
        if not total:
            return
        from PySide6.QtGui import QImage
        import pymupdf

        try:
            doc = pymupdf.open(self.src)
        except Exception:                             # noqa: BLE001
            return
        for i in range(total):
            pm = self._thumbs.get(i)
            if pm is None:
                try:
                    pix = doc[i].get_pixmap(dpi=28, alpha=False)
                    img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                                 QImage.Format_RGB888).copy()
                    pm = QPixmap.fromImage(img)
                except Exception:                     # noqa: BLE001
                    pm = QPixmap()
                if len(self._thumbs) > 600:
                    self._thumbs.clear()
                self._thumbs[i] = pm
            it = QListWidgetItem(QIcon(pm), str(i + 1))
            it.setTextAlignment(Qt.AlignHCenter)
            it.setToolTip(f"第 {i + 1} 页")
            it.setSizeHint(QSize(60, 90))
            self.pages_list.addItem(it)
        doc.close()
        self._paint_ranges()

    def _paint_ranges(self) -> None:
        """按「封面素材 / 正文 / 丢弃」给缩略图着色，一眼看出边界。"""
        total = self._total()
        if not total:
            return
        front = int(self.sp_front.value())
        tail = int(self.sp_tail.value())
        body_end = max(front, total - tail)
        for i in range(self.pages_list.count()):
            it = self.pages_list.item(i)
            if i < front:
                it.setBackground(QColor("#FBEDE9"))
                it.setForeground(QColor("#B23A2E"))
                it.setToolTip(f"第 {i + 1} 页 · 封面")
            elif i >= body_end:
                it.setBackground(QColor("#F1EDE4"))
                it.setForeground(QColor("#1E1B18"))
                it.setToolTip(f"第 {i + 1} 页 · 封底")
            else:
                it.setBackground(QColor("#FFFFFF"))
                it.setForeground(QColor("#6B6459"))
                it.setToolTip(f"第 {i + 1} 页 · 正文")

    def _show_page(self, page: int) -> None:
        if not self.src:
            return
        pm = self._pages.get(page)
        if pm is None:
            # 220dpi：缩到屏幕大小是"降采样"，比按屏幕尺寸渲染再放大清楚得多
            pm = render_page(self.src, page, dpi=220)
            if pm is None:
                return
            if len(self._pages) > 6:
                self._pages.clear()
            self._pages[page] = pm
        self.view.set_image(pm)
        self.view.fit()

    def _on_param(self, *_a) -> None:
        self._refresh_all()

    def _refresh_all(self, *_a) -> None:
        total = self._total()
        # 目录里已经有同参数的切分结果 → 直接把"结果"区填上（尤其重启之后）
        if self.src and total:
            res = P.existing_files(self.src, int(self.sp_front.value()),
                                   int(self.sp_tail.value()))
            self.out = res or {}
        front = int(self.sp_front.value())
        tail = int(self.sp_tail.value())
        body = max(0, total - front - tail)

        if not total:
            self.lbl_calc.setText("还没有载入 PDF")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
        else:
            self.lbl_calc.setText(
                f"共 {total} 页 → 封面 {min(front, total)} 页 · 封底 {min(tail, total)} 页"
                f" · 正文 {body} 页"
            )
            self.btn_prev.setEnabled(self.page > 0)
            self.btn_next.setEnabled(self.page < total - 1)
            self._show_page(self.page)
        if self.pages_list.count() == total:
            self._paint_ranges()
        self._refresh_labels()
        self._refresh_result()

    def _refresh_labels(self) -> None:
        total = self._total()
        if not total:
            self.lbl_page.setText("第 — / — 页")
            self.lbl_map.setText("")
            return
        front = int(self.sp_front.value())
        tail = int(self.sp_tail.value())
        self.lbl_page.setText(f"第 {self.page + 1} / {total} 页")
        if self.page < front:
            where = "封面"
        elif self.page >= total - tail:
            where = "封底"
        else:
            where = "正文"
        self.lbl_map.setText(
            f"第 1–{front} 页 → 封面　　"
            f"第 {front + 1}–{max(front + 1, total - tail)} 页 → 正文"
            + (f"　　第 {total - tail + 1}–{total} 页 → 封底" if tail else "")
            + f"　　当前页：{where}"
        )
        self.btn_prev.setEnabled(self.page > 0)
        self.btn_next.setEnabled(self.page < total - 1)

    def _refresh_result(self) -> None:
        self.list_out.clear()
        if not self.out:
            item = QListWidgetItem("分割后在这里列出封面 / 封底 / 正文")
            item.setFlags(Qt.NoItemFlags)
            self.list_out.addItem(item)
            self.btn_dir.setEnabled(False)
            return
        cover, back, body = self.out.get("cover"), self.out.get("back"), self.out.get("body")
        self.btn_pick_cover.setEnabled(bool(cover))
        self.btn_pick_back.setEnabled(bool(back))
        for label, path, pages in (("封面素材", cover, self.out["pages"][0]),
                                   ("封底素材", back, self.out["pages"][1]),
                                   ("正文", body, self.out["pages"][2])):
            if not path:
                continue
            it = QListWidgetItem(f"{label}　{pages} 页")
            it.setData(Qt.UserRole, path)
            it.setToolTip(path)
            self.list_out.addItem(it)
        self.btn_dir.setEnabled(True)

    # ── 用当前页定位置 ─────────────────────────────────────────────────
    def _set_body_start(self) -> None:
        if not self._total():
            return
        self.sp_front.set_value(self.page)          # 前面 page 页都是封面素材
        self._refresh_all()
        self._say(f"正文从第 {self.page + 1} 页开始（封面素材 {self.page} 页）")

    def _set_body_end(self) -> None:
        total = self._total()
        if not total:
            return
        tail = total - (self.page + 1)              # 当前页之后都丢掉
        self.sp_tail.set_value(tail)
        self._refresh_all()
        self._say(f"正文到第 {self.page + 1} 页结束（其后 {tail} 页作封底）")

    # ── 动作 ───────────────────────────────────────────────────────────
    def pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选一个 PDF",
                                              os.path.expanduser("~"), "PDF (*.pdf)")
        if path:
            self.set_source(path)

    def _set_busy(self, busy: bool, msg: str = "") -> None:
        prim = getattr(self.main, "primary", None)
        if prim is not None:
            prim.setEnabled(not busy)
            if busy:
                prim.setText("正在分割…")
            else:
                prim.setText(self.action_text)
        if msg:
            self._say(msg)

    def start(self) -> None:
        if not self.src:
            self._say("先选一个 PDF")
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(self, "还没有选文件",
                                    "先点「选择…」挑一个 PDF，或者直接把 PDF 拖进来。")
            return
        if self._worker is not None and self._worker.isRunning():
            return
        front, tail = int(self.sp_front.value()), int(self.sp_tail.value())
        self.proj = self._project_for(self.src)

        # 同样的参数已经切过 → 复用，不再生成 -2 -3 …
        if self.proj is not None:
            res = P.existing_split(self.proj, front, tail)
            if res is not None:
                P.register_split(self.proj, res, front, tail)
                self._save_project(self.proj)
                self._finish(res, "已经分割过（参数相同），复用现有文件")
                return

        self._set_busy(True, "正在分割…（大文件要几秒）")
        self._worker = _Worker(self.src, front, tail, self)
        self._worker.done.connect(lambda res: self._on_done(res, front, tail))
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_done(self, res: dict, front: int, tail: int) -> None:
        if self.proj is not None:
            P.register_split(self.proj, res, front, tail)
            self._save_project(self.proj)
        self._finish(res)

    def _on_fail(self, msg: str) -> None:
        self._set_busy(False, f"分割失败：{msg}")

    def _finish(self, res: dict, note: str = "") -> None:
        self.out = res
        self._refresh_result()
        self._set_busy(False)
        head = f"{note}，" if note else "完成："
        self._say(f"{head}封面 {res['pages'][0]} 页 · 封底 {res['pages'][1]} 页"
                  f" · 正文 {res['pages'][2]} 页")

    def _save_project(self, proj) -> None:
        try:
            store = ShelfStore()
            shelf = store.load()
            shelf.add_project(proj)
            store.save(shelf)
        except Exception:                             # noqa: BLE001
            pass

    def _recent_source(self) -> str:
        try:
            shelf = ShelfStore().load()
        except Exception:                             # noqa: BLE001
            return ""
        projs = [p for p in shelf.projects if p.source and os.path.exists(p.source.path)]
        if not projs:
            return ""
        projs.sort(key=lambda p: p.opened or p.created, reverse=True)
        return projs[0].source.path

    def _project_for(self, path: str):
        try:
            shelf = ShelfStore().load()
        except Exception:                             # noqa: BLE001
            return None
        target = os.path.abspath(path)
        for p in shelf.projects:
            if p.source and os.path.abspath(p.source.path) == target:
                return p
        return None

    def to_cover(self, slot: str = "cover") -> None:
        pdf = self.out.get("cover" if slot == "cover" else "back", "")
        img = CL.pick_and_fill(self.main, slot, pdf, self)
        if not img:
            self._say("没有选到页")
            return
        CL.goto_cover(self.main)
        self._say(f"已把{CL.SLOTS_NAME[slot]}（{os.path.basename(img)}）送进封面页")

    def _open_row(self, item) -> None:
        path = item.data(Qt.UserRole)
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _open_out_dir(self) -> None:
        body = self.out.get("body")
        if body and os.path.exists(body):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(body)))

    # ── 拖放 ───────────────────────────────────────────────────────────
    def dragEnterEvent(self, ev) -> None:
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev) -> None:
        for url in ev.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf") and os.path.exists(path):
                self.set_source(path)
                break
