"""生产线页：一卷书从左到右的七道工序（参考 ComfyUI 的信息表达，不做它的编辑器）。

图是**固定拓扑**：① 导入 → ② 分割 →（③ 封面 / ④ 页码 → ⑤ 排版）→ ⑥ 打印 → ⑦ 定稿，
分支与汇合是真实的（封面绕开正文直接进打印）。

节点全部自绘（QGraphicsItem.paint），不嵌入真实控件：
- 缩放不会糊，72 卷也不会吃内存；
- 点节点 → 右侧参数/产物面板，跳转到原程序对应工具页去干活。

数据全部来自 新的 ui/core 层/shelf 的派生状态，这一页不自己判断业务。
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QUrl
from PySide6.QtGui import (
    QBrush, QColor, QDesktopServices, QFont, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.pages import SectionLabel
from ui.theme import INK, INK2, INK3, LINE, RED, SURFACE
from ui.widgets import Card

from ui.preview_kit import GridCanvas
from ui.right_rail import RightRail

from ui import cover_link as CL
from core import pipeline as P
from core.shelf import collect as C
from core.shelf import thumbs as T
from core.shelf.model import (
    KIND_BODY, KIND_COVER, KIND_COVER_BACK, KIND_COVER_SRC, KIND_LABELS, KIND_PAGED,
    ST_BLOCKED, ST_DONE, ST_STALE, ST_SKIP, ST_TODO,
    STEP_COVER, STEP_FINAL, STEP_IMPORT, STEP_LAYOUT, STEP_NAMES, STEP_PAGER,
    STEP_PRINT, STEP_SPLIT, STEPS, Project,
)
from core.shelf.store import ShelfStore

NODE_W, NODE_H = 150, 90
MAIN_ROW = (STEP_IMPORT, STEP_SPLIT, STEP_PAGER, STEP_LAYOUT, STEP_PRINT, STEP_FINAL)
X0, PITCH, ROW_Y = 4, 168, 108
COVER_X, COVER_Y = 4 + PITCH, 0
NODE_LABEL = {1: "导入", 2: "分割", 3: "封面", 4: "页码", 5: "排版", 6: "打印", 7: "定稿"}

# 只用原程序的调色板：墨 #1E1B18、朱红 #B23A2E、米白 #FCFAF5、灰 #7E7568
STATE_STYLE = {
    ST_DONE:    ("#1E1B18", "#F3EEE4", "#1E1B18", "完成"),
    ST_STALE:   ("#B23A2E", "#FFF3F1", "#B23A2E", "需重跑"),
    ST_TODO:    ("#DCD3C4", "#FCFAF5", "#7E7568", "待做"),
    ST_SKIP:    ("#C6BCAA", "#F4F1EA", "#7E7568", "跳过"),
    ST_BLOCKED: ("#DCD3C4", "#FCFAF5", "#7E7568", "缺输入"),
}

# 每一步对应的原程序页面（类名）
STEP_PAGE = {
    STEP_SPLIT: "SplitToolPage",
    STEP_COVER: "CoverPage",
    STEP_PAGER: "NumberPage",
    STEP_LAYOUT: "BookletPage",
    STEP_PRINT: "PrintPage",
}
STEP_ACTION = {
    STEP_IMPORT: "打不开原稿时去「转换」",
    STEP_SPLIT: "打开分割页（带预览）",
    STEP_COVER: "去封面页",
    STEP_PAGER: "去页码页",
    STEP_LAYOUT: "去排版页",
    STEP_PRINT: "去打印页",
    STEP_FINAL: "在这里打星",
}


class _NodeItem(QGraphicsItem):
    def __init__(self, step: int, state: str, meta1: str, meta2: str,
                 thumb: QPixmap | None = None):
        super().__init__()
        self.step = step
        self.state = state
        self.meta1 = meta1
        self.meta2 = meta2
        self.thumb = thumb
        self.selected = False
        self.setAcceptHoverEvents(True)
        self.setZValue(2)

    def boundingRect(self) -> QRectF:
        return QRectF(-2, -2, NODE_W + 4, NODE_H + 4)

    def paint(self, p: QPainter, _opt, _widget=None) -> None:
        accent, pill_bg, pill_fg, pill_text = STATE_STYLE.get(self.state, STATE_STYLE[ST_TODO])
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, NODE_W, NODE_H)

        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        p.fillPath(path, QBrush(QColor("#FFFFFF")))

        border = QColor("#E4DDD1")
        if self.state == ST_STALE:
            border = QColor("#E7C3BC")
        if self.selected:
            border = QColor("#B23A2E")
        p.setPen(QPen(border, 2.0 if self.selected else 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # 步骤号 + 标题
        f = QFont()
        f.setPointSizeF(8.0)
        p.setFont(f)
        p.setPen(QColor("#A79D8F"))
        p.drawText(QRectF(8, 7, 20, 14), Qt.AlignLeft | Qt.AlignVCenter, f"{self.step:02d}")

        f2 = QFont("SimSun")
        f2.setPointSizeF(10.5)
        f2.setBold(False)
        p.setFont(f2)
        p.setPen(QColor(INK))
        p.drawText(QRectF(30, 7, NODE_W - 92, 15), Qt.AlignLeft | Qt.AlignVCenter,
                   NODE_LABEL.get(self.step, STEP_NAMES.get(self.step, "")))

        # 状态胶囊
        pf = QFont()
        pf.setPointSizeF(7.5)
        p.setFont(pf)
        tw = p.fontMetrics().horizontalAdvance(pill_text) + 12
        pill = QRectF(NODE_W - 10 - tw, 7, tw, 15)
        pp = QPainterPath()
        pp.addRoundedRect(pill, 7, 7)
        p.fillPath(pp, QBrush(QColor(pill_bg)))
        p.setPen(QColor(pill_fg))
        p.drawText(pill, Qt.AlignCenter, pill_text)

        # 缩略图
        th = QRectF(8, 28, 22, 31)
        if self.thumb and not self.thumb.isNull():
            p.save()
            clip = QPainterPath()
            clip.addRoundedRect(th, 2, 2)
            p.setClipPath(clip)
            scaled = self.thumb.scaled(int(th.width()), int(th.height()),
                                       Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(int(th.x() + (th.width() - scaled.width()) / 2),
                         int(th.y() + (th.height() - scaled.height()) / 2), scaled)
            p.restore()
            p.setPen(QPen(QColor("#E4DDD1"), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(th, 2, 2)
        else:
            p.setPen(QPen(QColor("#E4DDD1"), 1, Qt.DashLine))
            p.setBrush(QColor("#FCFAF5"))
            p.drawRoundedRect(th, 2, 2)

        # 两行信息
        f3 = QFont()
        f3.setPointSizeF(7.6)
        p.setFont(f3)
        p.setPen(QColor("#1E1B18"))
        w1 = NODE_W - 44
        t1 = p.fontMetrics().elidedText(self.meta1, Qt.ElideRight, w1)
        p.drawText(QRectF(36, 28, w1, 17), Qt.AlignLeft | Qt.AlignTop, t1)
        p.setPen(QColor("#6B6459"))
        t2 = p.fontMetrics().elidedText(self.meta2, Qt.ElideRight, w1 * 2)
        p.drawText(QRectF(36, 45, w1, 30), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, t2)

    # 只做视觉反馈，不拖拽
    def hoverEnterEvent(self, ev) -> None:
        self.update()
        super().hoverEnterEvent(ev)


class _Canvas(GridCanvas):
    """原程序的网格画布 + 节点图（网格来自 PreviewView.drawBackground）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = self.scene_          # PreviewView 建好的场景
        self._scene.setSceneRect(
            QRectF(0, 0, X0 + PITCH * 5 + NODE_W + 8, ROW_Y + NODE_H + 8))
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.on_node = None            # 点击节点回调：页面用它切右侧面板

    def mousePressEvent(self, ev) -> None:
        item = self.itemAt(ev.pos())
        while item is not None and not isinstance(item, _NodeItem):
            item = item.parentItem()
        if isinstance(item, _NodeItem) and callable(self.on_node):
            self.on_node(item.step)
        super().mousePressEvent(ev)

    def items_scene(self) -> QGraphicsScene:
        return self._scene

    def fit(self) -> None:
        """整张图放进视野：窄了就缩，宽了最多放大 1.35 倍（节点是矢量画的，不会糊）。"""
        res = self.sceneRect()
        self.resetTransform()
        vw, vh = self.viewport().width(), self.viewport().height()
        if vw > 20 and vh > 20:
            sc = min(1.35, (vw - 8) / res.width(), (vh - 8) / res.height())
            if abs(sc - 1.0) > 0.01:
                self.scale(sc, sc)
        self.centerOn(res.center().x(), res.top() + res.height() / 2)

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self.fit()

    def showEvent(self, ev) -> None:
        super().showEvent(ev)
        self.fit()

    def wheelEvent(self, ev) -> None:
        if ev.modifiers() & Qt.ControlModifier:
            f = 1.12 if ev.angleDelta().y() > 0 else 1 / 1.12
            self.scale(f, f)
            ev.accept()
        else:
            super().wheelEvent(ev)


def _edge(a: QPointF, b: QPointF, color: str, dashed: bool = False,
          elbow_x: float | None = None) -> QGraphicsPathItem:
    """直线或"先横后竖"的折线，圆角过渡。"""
    path = QPainterPath(a)
    if elbow_x is None:
        path.lineTo(b)
    else:
        path.lineTo(elbow_x, a.y())
        path.quadTo(b.x() if abs(elbow_x - b.x()) < 1 else elbow_x, a.y(), b.x(), b.y())
    item = QGraphicsPathItem(path)
    pen = QPen(QColor(color), 1.2)
    if dashed:
        pen.setStyle(Qt.DashLine)
        pen.setDashPattern([4, 3])
    item.setPen(pen)
    item.setZValue(0)
    return item


class PipelinePage(QWidget):
    crumb = "书籍制作工具 / 生产线"
    title = "生产线"
    action_text = "下一步"

    def __init__(self, main=None, parent=None, store: ShelfStore | None = None) -> None:
        super().__init__(parent)
        self.main = main
        self.store = store or ShelfStore()
        self.shelf = self.store.load()
        self.project: Project | None = None
        self._order: list[str] = []
        self._cur_step = STEP_SPLIT
        self._build()

    # ── 页面契约 ───────────────────────────────────────────────────────
    def require_file(self) -> bool:
        return False

    always_ready = True          # 主按钮（下一步）不需要先选文件

    def on_show(self) -> None:
        if self.project is not None:
            pid = self.project.id
            self.shelf = self.store.load()
            self.project = self.shelf.by_id(pid) or self.project
            self._order = [p.id for p in self.shelf.projects_of(self.project.series_id)] or [pid]
            # 刚从「小册子 / 封面」回来时，产物是别的页写进磁盘的：
            # 这里重扫一遍目录，第⑤⑥步才会立刻变成"完成"，不用手工点「重新扫描」。
            try:
                C.scan_products(self.project, read_pages=True)
                self._save()
            except Exception:                        # noqa: BLE001
                logging.getLogger(__name__).exception("生产线重扫产物失败")
        elif not self.set_project_default():
            self.refresh()
        prim = getattr(self.main, "primary", None)
        if prim is not None:
            prim.setText(self.action_text)
            prim.setEnabled(True)
        self.refresh()
        self._say(self._status_line())

    def run(self) -> None:
        self.goto_step(self._next_step())

    def status(self, msg: str) -> None:
        self._say(msg)

    def _say(self, msg: str) -> None:
        setter = getattr(self.main, "set_status", None)
        if callable(setter):
            setter(msg)

    def set_project_default(self) -> bool:
        """没选书时默认显示书架里的第一本，免得页面空着。"""
        self.shelf = self.store.load()
        if not self.shelf.projects:
            return False
        ordered = sorted(self.shelf.projects, key=lambda p: p.opened or p.created, reverse=True)
        return self.set_project(ordered[0].id)

    def attach_split_page(self, page) -> None:
        """main.py 把新「分割」页换上来之后，把引用交给我们。"""
        self._split_page = page

    # ── 载入某一卷 ─────────────────────────────────────────────────────
    def set_project(self, pid: str) -> bool:
        self.shelf = self.store.load()
        self.project = self.shelf.by_id(pid)
        if self.project is None:
            return False
        siblings = self.shelf.projects_of(self.project.series_id)
        self._order = [p.id for p in siblings] or [self.project.id]
        self.refresh()
        return True

    def _siblings(self) -> list[str]:
        return self._order

    def _move_volume(self, delta: int) -> None:
        if not self.project or len(self._order) < 2:
            return
        try:
            i = self._order.index(self.project.id) + delta
        except ValueError:
            return
        if 0 <= i < len(self._order):
            self.set_project(self._order[i])
            self._say(f"第 {self.project.index or '?'} 卷")

    # ── 界面 ───────────────────────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 0)
        root.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.lbl_title = QLabel("没有选中任何书")

        self.lbl_title.setObjectName("GroupTitle")
        head.addWidget(self.lbl_title)

        self.lbl_meta = QLabel("")
        self.lbl_meta.setStyleSheet(f"color:{INK2};")
        head.addWidget(self.lbl_meta)
        head.addStretch(1)

        self.btn_prev = self._btn("← 上一卷", lambda: self._move_volume(-1))
        self.btn_next = self._btn("下一卷 →", lambda: self._move_volume(1))
        head.addWidget(self.btn_prev)
        head.addWidget(self.btn_next)
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(14)

        graph_card = Card()
        gl = graph_card.layout()
        gl.addWidget(SectionLabel("生产线"))
        self.canvas = _Canvas()
        self.canvas.on_node = self._select_step
        self.canvas.setMinimumHeight(300)
        gl.addWidget(self.canvas, 1)
        self.tip = QLabel("　点节点看这一步在干什么；橙框 = 上游改过需要重跑；③ 封面做完会直接进 ⑥ 打印")
        self.tip.setStyleSheet(f"color:{INK3};font-size:10.5px;")
        self.tip.setWordWrap(True)
        gl.addWidget(self.tip)
        body.addWidget(graph_card, 1)

        side = Card()
        side.setFixedWidth(280)
        side.setMinimumWidth(280)
        sl = side.layout()
        sl.addWidget(SectionLabel("这一步"))
        self.detail = QLabel("点一个节点看详情")
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet(f"color:{INK2};font-size:11.5px;line-height:150%;")
        sl.addWidget(self.detail)

        # 分割参数（只有第②步用得到）
        self.split_box = QWidget()
        sb = QVBoxLayout(self.split_box)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(6)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("前 N 页 = 封面"))
        self.sp_front = QSpinBox()
        self.sp_front.setRange(0, 30)
        self.sp_front.setValue(2)
        row1.addWidget(self.sp_front)
        row1.addStretch(1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("末尾 M 页 = 封底"))
        self.sp_tail = QSpinBox()
        self.sp_tail.setRange(0, 30)
        self.sp_tail.setValue(1)
        row2.addWidget(self.sp_tail)
        row2.addStretch(1)
        sb.addLayout(row1)
        sb.addLayout(row2)
        self.btn_split = self._btn("就地分割", self.do_split)
        sb.addWidget(self.btn_split)
        sl.addWidget(self.split_box)

        sl.addStretch(1)
        self.btn_fill_cover = self._btn("选封面图…", lambda: self.fill_cover_materials("cover"))
        sl.addWidget(self.btn_fill_cover)
        self.btn_fill_back = self._btn("选封底图…", lambda: self.fill_cover_materials("back"))
        sl.addWidget(self.btn_fill_back)
        self.btn_open_tool = self._btn("打开这一步的工具 →", self.open_tool, primary=True)
        self.btn_open_out = self._btn("打开产物", self.open_product)
        self.btn_final = self._btn("设为定稿", self.mark_final)
        for b in (self.btn_open_tool, self.btn_open_out, self.btn_final):
            sl.addWidget(b)
        body.addWidget(side)
        self._rail = RightRail(self, side)          # 右栏一键收起

        root.addLayout(body, 1)

    def _btn(self, text: str, slot, primary: bool = False) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumHeight(28)
        if primary:
            b.setStyleSheet(
                f"QPushButton{{background:{RED};color:#fff;border:none;border-radius:6px;"
                "padding:0 12px;font-size:12px;}QPushButton:hover{background:#9E3327;}"
            )
        else:
            b.setStyleSheet(
                f"QPushButton{{background:{SURFACE};color:{INK};border:1px solid {LINE};"
                "border-radius:6px;padding:0 10px;font-size:12px;}"
                "QPushButton:hover{border-color:#D3C7B4;}"
            )
        b.clicked.connect(slot)
        return b

    # ── 画图 ───────────────────────────────────────────────────────────
    def refresh(self) -> None:
        p = self.project
        scene = self.canvas.items_scene() if hasattr(self, "canvas") else None
        if scene is None:
            return
        scene.clear()
        if p is None:
            self.lbl_title.setText("没有选中任何书")
            self.lbl_meta.setText("去书架点一本书")
            self.detail.setText("点一个节点看详情")
            return

        series = self.shelf.series_by_id(p.series_id)
        self.lbl_title.setText(f"{p.name}　第 {p.index} 卷" if p.index else p.name)
        self.lbl_meta.setText(
            f"{series.name if series else '单本'}　·　{p.done_steps}/7 步　·　{p.status}"
        )
        self.btn_prev.setEnabled(len(self._order) > 1 and self._order[0] != p.id)
        self.btn_next.setEnabled(len(self._order) > 1 and self._order[-1] != p.id)

        pos: dict[int, tuple[float, float]] = {}
        for i, step in enumerate(MAIN_ROW):
            pos[step] = (X0 + PITCH * i, ROW_Y)
        pos[STEP_COVER] = (COVER_X, COVER_Y)

        for step in STEPS:
            state, reason = p.step_state(step)
            m1, m2 = self._meta_for(p, step, state, reason)
            x, y = pos[step]
            node = _NodeItem(step, state, m1, m2, self._thumb_for(p, step))
            node.setPos(QPointF(x, y))
            node.setFlag(QGraphicsItem.ItemIsSelectable, True)
            node.selected = (step == self._cur_step)
            node.setData(0, step)
            scene.addItem(node)

        # 连线
        def cx(step: int) -> float:
            return pos[step][0] + NODE_W

        def cy(step: int) -> float:
            return pos[step][1] + NODE_H / 2

        seq = list(MAIN_ROW)
        for a, b in zip(seq, seq[1:]):
            stale_a = p.step_state(a)[0] == ST_STALE
            color = "#B23A2E" if stale_a else "#D8D0C2"
            scene.addItem(_edge(QPointF(cx(a), cy(a)), QPointF(pos[b][0], cy(b)), color,
                                dashed=stale_a))
        # ② → ③（向上）
        st3 = p.step_state(STEP_COVER)[0]
        col = "#B23A2E" if st3 == ST_STALE else "#D8D0C2"
        scene.addItem(_edge(
            QPointF(pos[STEP_SPLIT][0] + NODE_W / 2, pos[STEP_SPLIT][1]),
            QPointF(pos[STEP_COVER][0] + NODE_W / 2, COVER_Y + NODE_H),
            col, dashed=True))
        # ③ → ⑥（沿顶部右行，落到打印顶边）
        target_x = pos[STEP_PRINT][0] + NODE_W - 24
        path = QPainterPath(QPointF(cx(STEP_COVER), COVER_Y + NODE_H / 2))
        path.lineTo(target_x, COVER_Y + NODE_H / 2)
        path.quadTo(target_x + 8, COVER_Y + NODE_H / 2, target_x + 8, COVER_Y + NODE_H / 2 + 8)
        path.lineTo(target_x + 8, pos[STEP_PRINT][1])
        item = QGraphicsPathItem(path)
        item.setPen(QPen(QColor("#D8D0C2"), 1.2))
        item.setZValue(0)
        scene.addItem(item)

        self._select_step(self._cur_step, update_only=True)
        self.canvas.fit()

    def _meta_for(self, p: Project, step: int, state: str, reason: str) -> tuple[str, str]:
        if step == STEP_IMPORT:
            src = p.source
            name = os.path.splitext(os.path.basename(src.path))[0] if src else "未导入"
            return name[:16], f"{src.pages or '?'} 页" if src else "拖一本进来"
        if step == STEP_SPLIT:
            cover = next((i for i in p.items if i.kind == KIND_COVER_SRC), None)
            body = next((i for i in p.items if i.kind == KIND_BODY), None)
            if body:
                back = next((i for i in p.items if i.kind == KIND_COVER_BACK), None)
                bits = [f"封面 {cover.pages} 页" if cover else "无封面",
                        f"封底 {back.pages} 页" if back else "无封底"]
                return f"正文 {body.pages or '?'} 页", " · ".join(bits)
            return "前 N 页 = 封面", "其余 → 正文"
        if step == STEP_COVER:
            it = next((i for i in p.items if i.kind == KIND_COVER), None)
            sp = (p.params.get("CoverPage") or {}).get("书脊")
            return (f"书脊 {sp} mm" if sp else "成品封面"), reason
        if step == STEP_PAGER:
            it = next((i for i in p.items if i.kind == KIND_PAGED), None)
            return ("已加页码" if it else "未加页码"), (f"{it.pages} 页" if it else reason)
        if step == STEP_LAYOUT:
            it = p.layout_item()
            if it:
                return f"{KIND_LABELS.get(it.kind, '')} · {it.pages or '?'} 面", reason
            return "未排版", "小册子 / 四堆叠 / 4合1"
        if step == STEP_PRINT:
            cover = next((i for i in p.items if i.kind == KIND_COVER), None)
            real = p.real_prints
            if real:
                return (f"已打 {len(real)} 次 · {sum(e.sheets for e in real)} 张",
                        real[-1].at.replace("T", " ")[5:16])
            return "还没打印", ("封面未做，可选" if not cover else "点了打印会记在这里")
        if step == STEP_FINAL:
            return ("已定稿" if p.final else "未定稿"), reason
        return "", reason

    def _thumb_for(self, p: Project, step: int) -> QPixmap | None:
        path = None
        if step == STEP_IMPORT and p.source:
            path = p.source.path
        elif step == STEP_SPLIT:
            it = next((i for i in p.items if i.kind == KIND_BODY), None) or p.source
            path = it.path if it else None
        elif step == STEP_COVER:
            it = next((i for i in p.items if i.kind == KIND_COVER), None)
            path = it.path if it else None
        elif step == STEP_PAGER:
            it = next((i for i in p.items if i.kind == KIND_PAGED), None)
            path = it.path if it else None
        elif step == STEP_LAYOUT:
            it = p.layout_item()
            path = it.path if it else None
        if not path or not path.lower().endswith(".pdf"):
            return None
        f = T.thumb(path, width=120)
        return QPixmap(f) if f else None

    # ── 选中节点 ───────────────────────────────────────────────────────
    def _select_step(self, step: int, update_only: bool = False) -> None:
        self._cur_step = step
        for it in self.canvas.items_scene().items():
            if isinstance(it, _NodeItem):
                it.selected = (it.step == step)
                it.update()
        if update_only and self.project is None:
            return
        p = self.project
        if p is None:
            return
        state, reason = p.step_state(step)
        color, _bg, _fg, label = STATE_STYLE.get(state, STATE_STYLE[ST_TODO])
        lines = [
            f"<b>{step:02d}　{STEP_NAMES.get(step, '')}</b>　"
            f"<span style='color:{color}'>● {label}</span>",
            f"<span style='color:#8A8072'>{reason}</span>",
        ]
        item = self._product_for(p, step)
        if item:
            lines.append(
                f"<div style='margin-top:6px;color:#6B6459'>{KIND_LABELS.get(item.kind, '')}："
                f"{os.path.basename(item.path)}<br>{item.pages or '?'} 页"
            )
            if item.pages:
                lines[-1] += f" · {item.size / 1048576:.1f} MB"
            lines.append("</div>")
        self.detail.setText("<br>".join(lines))

        self.split_box.setVisible(step == STEP_SPLIT)
        mats = self._cover_materials()
        self.btn_fill_cover.setVisible(step == STEP_COVER and bool(mats.get("cover")))
        self.btn_fill_back.setVisible(step == STEP_COVER and bool(mats.get("back")))
        self.btn_open_tool.setVisible(step in STEP_PAGE or step == STEP_IMPORT)
        self.btn_open_tool.setText(STEP_ACTION.get(step, "打开"))
        self.btn_open_out.setVisible(bool(item))
        self.btn_final.setVisible(step == STEP_FINAL)

    def _cover_materials(self) -> dict:
        p = self.project
        if p is None:
            return {}
        cover = next((i for i in p.items if i.kind == KIND_COVER_SRC and i.exists), None)
        back = next((i for i in p.items if i.kind == KIND_COVER_BACK and i.exists), None)
        out = {}
        if cover:
            out["cover"] = cover.path
        if back:
            out["back"] = back.path
        return out

    def fill_cover_materials(self, slot: str = "cover") -> None:
        mats = self._cover_materials()
        pdf = mats.get(slot)
        if not pdf:
            self._say("还没有这一份素材，先去第②步分割")
            return
        img = CL.pick_and_fill(self.main, slot, pdf, self)
        if not img:
            self._say("没有选到页")
            return
        CL.goto_cover(self.main)
        self._say(f"已把{CL.SLOTS_NAME[slot]}（{os.path.basename(img)}）送进封面页")

    def _product_for(self, p: Project, step: int):
        if step == STEP_SPLIT:
            return next((i for i in p.items if i.kind == KIND_BODY), None)
        if step == STEP_COVER:
            return next((i for i in p.items if i.kind == KIND_COVER), None)
        if step == STEP_PAGER:
            return next((i for i in p.items if i.kind == KIND_PAGED), None)
        if step == STEP_LAYOUT:
            return p.layout_item()
        if step == STEP_PRINT:
            return p.layout_item()
        return None

    # ── 动作 ───────────────────────────────────────────────────────────
    def _next_step(self) -> int:
        if self.project is None:
            return STEP_SPLIT
        for s in STEPS:
            if self.project.step_state(s)[0] != ST_DONE:
                return s
        return STEP_FINAL

    def goto_step(self, step: int) -> None:
        self._select_step(step)

    def do_split(self) -> None:
        if self.project is None or not self.project.source:
            self._say("没有原稿")
            return
        front, tail = self.sp_front.value(), self.sp_tail.value()
        try:
            res = P.apply_split(self.project, front=front, tail=tail)
        except Exception as exc:                      # noqa: BLE001
            self._say(f"分割失败：{exc}")
            return
        self.project.params.setdefault("SplitPage", {})["front"] = front
        self.project.params["SplitPage"]["tail"] = tail
        self._save()
        self.refresh()
        self._say(f"已分割：封面素材 {front} 页 → 正文 {res['pages'][1]} 页")

    def open_tool(self) -> None:
        step = self._cur_step
        page_cls = STEP_PAGE.get(step)
        if page_cls is None:
            if step == STEP_IMPORT:
                self._open_path(self.project.source.path if self.project and self.project.source else "")
            return
        pages = getattr(self.main, "pages", [])
        idx = next((i for i, pg in enumerate(pages) if type(pg).__name__ == page_cls), None)
        if idx is None:
            self._say(f"找不到 {page_cls} 页")
            return
        doc = self._input_for_step(step)
        if doc:
            setter = getattr(self.main, "set_current_doc", None)
            if callable(setter):
                setter(doc)
        if step == STEP_SPLIT:
            page = getattr(self, "_split_page", None) or pages[idx]
            src = self.project.source.path if self.project and self.project.source else None
            if src and hasattr(page, "set_source"):
                page.set_source(src)
        goto = getattr(self.main, "goto", None)
        if callable(goto):
            goto(idx)
        self._say(f"已跳到「{STEP_NAMES.get(step, '')}」")

    def _input_for_step(self, step: int) -> str | None:
        p = self.project
        if p is None:
            return None
        if step == STEP_LAYOUT:
            it = next((i for i in p.items if i.kind == KIND_PAGED), None) or \
                 next((i for i in p.items if i.kind == KIND_BODY), None)
            return it.path if it else (p.source.path if p.source else None)
        if step == STEP_PAGER:
            it = next((i for i in p.items if i.kind == KIND_BODY), None)
            return it.path if it else (p.source.path if p.source else None)
        if step == STEP_PRINT:
            it = p.layout_item()
            return it.path if it else None
        return p.source.path if p.source else None

    def open_product(self) -> None:
        if self.project is None:
            return
        item = self._product_for(self.project, self._cur_step)
        if item:
            self._open_path(item.path)

    def _open_path(self, path: str) -> None:
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            self._say("文件不在了")

    def mark_final(self) -> None:
        if self.project is None:
            return
        if self.project.final:
            self.project.set_final(None)
            self._say("已取消定稿")
        else:
            item = self.project.layout_item() or self._product_for(self.project, STEP_COVER)
            if not item:
                self._say("还没有产物可以定为定稿")
                return
            self.project.set_final(item.path)
            self._say("已设为定稿：" + os.path.basename(item.path))
        self._save()
        self.refresh()

    def _save(self) -> None:
        if self.project is None:
            return
        self.shelf.add_project(self.project)
        try:
            self.store.save(self.shelf)
        except Exception as exc:                      # noqa: BLE001
            self._say(f"保存失败：{exc}")

    def _status_line(self) -> str:
        if self.project is None:
            return "生产线 · 去书架选一本书"
        return f"{self.project.name} · {self.project.done_steps}/7 步 · {self.project.status}"
