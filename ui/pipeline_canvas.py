"""生产线画布：节点图的自绘原语（节点 / 缩放平移画布 / 连线）。

从 ui/pipeline_page.py 拆出来的 —— 那是「画什么、怎么画」，页面那边是「画哪些、点了干什么」。
类和常量的名字都没改，页面直接 import。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsPathItem, QGraphicsScene, QGraphicsView)
from ui.theme import INK
from ui.preview_kit import GridCanvas

NODE_W, NODE_H = 150, 90
X0, PITCH, ROW_Y = 4, 168, 108
COVER_X, COVER_Y = 4 + PITCH, 0
NODE_LABEL = {1: "导入", 2: "分割", 3: "封面", 4: "页码", 5: "排版", 6: "打印", 7: "定稿"}


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
