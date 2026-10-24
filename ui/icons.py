"""手绘线性图标（不依赖图标字体，深浅两套颜色）。"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


ASSETS = __import__("os").path.join(
    __import__("os").path.dirname(__import__("os").path.dirname(
        __import__("os").path.abspath(__file__))), "assets")


def avatar_icon(size: int = 44, radius: int = 10) -> QIcon:
    """左上角头像（圆角方形，像 App 图标）。"""
    from PySide6.QtGui import QPainterPath, QPixmap
    pm = QPixmap(__import__("os").path.join(ASSETS, "bili_avatar.jpg"))
    if pm.isNull():
        return QIcon()
    pm = pm.scaled(size * 2, size * 2, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = max(0, (pm.width() - size * 2) // 2)
    y = max(0, (pm.height() - size * 2) // 2)
    pm = pm.copy(x, y, size * 2, size * 2)
    out = QPixmap(size * 2, size * 2)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, size * 2, size * 2, radius * 2, radius * 2)
    p.setClipPath(clip)
    p.drawPixmap(0, 0, pm)
    p.end()
    return QIcon(out)


def _pix(draw, color: str, size: int = 44) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(size / 15)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s = size / 24.0
    p.scale(s, s)
    draw(p)
    p.end()
    return pm


def icon(name: str, color: str, active_color: str | None = None) -> QIcon:
    ic = QIcon()
    ic.addPixmap(_pix(DRAW[name], color), QIcon.Normal, QIcon.Off)
    if active_color:
        ic.addPixmap(_pix(DRAW[name], active_color), QIcon.Normal, QIcon.On)
        ic.addPixmap(_pix(DRAW[name], active_color), QIcon.Selected, QIcon.Off)
    return ic


# ---------------- 图形 ----------------
def _booklet(p: QPainter):
    p.drawRoundedRect(QRectF(3, 4, 18, 16), 1.6, 1.6)
    p.drawLine(QPointF(12, 4), QPointF(12, 20))          # 中缝
    p.drawLine(QPointF(6, 8), QPointF(9, 8))
    p.drawLine(QPointF(6, 11.5), QPointF(9, 11.5))
    p.drawLine(QPointF(15, 8), QPointF(18, 8))
    p.drawLine(QPointF(15, 11.5), QPointF(18, 11.5))


def _cover(p: QPainter):
    p.drawRoundedRect(QRectF(3, 4, 18, 16), 1.6, 1.6)
    p.drawLine(QPointF(8, 4), QPointF(8, 20))            # 书脊
    p.drawLine(QPointF(12, 9), QPointF(18, 9))
    p.drawLine(QPointF(12, 12.5), QPointF(16, 12.5))


def _stack(p: QPainter):
    # 三张平放的纸，逐层右移 → 一眼看出"堆"
    for k, y in enumerate((4.0, 10.0, 16.0)):
        p.drawRoundedRect(QRectF(3.0 + k * 2.2, y, 14.5, 4.6), 1.2, 1.2)


def _fourup(p: QPainter):
    p.drawRoundedRect(QRectF(3, 4, 18, 16), 1.6, 1.6)
    p.drawLine(QPointF(12, 4), QPointF(12, 20))
    p.drawLine(QPointF(3, 12), QPointF(21, 12))


def _a5toa4(p: QPainter):
    p.drawRoundedRect(QRectF(3, 3.5, 18, 7.5), 1.2, 1.2)
    p.drawRoundedRect(QRectF(3, 13, 18, 7.5), 1.2, 1.2)
    p.drawLine(QPointF(12, 10), QPointF(12, 15))
    p.drawLine(QPointF(10.2, 13.2), QPointF(12, 15))
    p.drawLine(QPointF(13.8, 13.2), QPointF(12, 15))


def _merge(p: QPainter):
    p.drawRoundedRect(QRectF(3, 3, 12, 15), 1.4, 1.4)
    p.drawRoundedRect(QRectF(9, 6, 12, 15), 1.4, 1.4)
    p.drawLine(QPointF(12.5, 11), QPointF(17.5, 11))
    p.drawLine(QPointF(12.5, 14), QPointF(16, 14))


def arrangement(mode: str, color: str = "#1E1B18") -> QIcon:
    """4 合 1 的四种排列示意：四个格子里写 1-4，直接看出哪页放哪。"""
    from PySide6.QtGui import QFont
    orders = {"A": [0, 1, 2, 3], "B": [0, 2, 1, 3],
              "C": [2, 0, 3, 1], "D": [1, 0, 3, 2]}
    order = orders[mode]
    pm = QPixmap(56, 56)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.4)
    p.setPen(pen)
    f = QFont("Microsoft YaHei")
    f.setPixelSize(11)
    f.setBold(True)
    p.setFont(f)
    slot = [(2, 2), (30, 2), (2, 30), (30, 30)]
    for s, (x, y) in enumerate(slot):
        p.drawRoundedRect(QRectF(x, y, 24, 24), 3, 3)
        p.drawText(QRectF(x, y, 24, 24), Qt.AlignCenter, str(order[s] + 1))
    p.end()
    return QIcon(pm)


def _pager(p: QPainter):
    # 一张纸 + 底部页码
    p.drawRoundedRect(QRectF(4, 3, 16, 18), 1.6, 1.6)
    p.drawLine(QPointF(8, 8), QPointF(16, 8))
    p.drawLine(QPointF(8, 12), QPointF(16, 12))
    p.drawLine(QPointF(10, 17), QPointF(14, 17))


def _print(p: QPainter):
    # 打印机：机身 + 出纸 + 进纸
    p.drawRoundedRect(QRectF(3, 8, 18, 9), 1.6, 1.6)
    p.drawRect(QRectF(6, 3, 12, 6))
    p.drawRect(QRectF(6, 15, 12, 6))
    p.drawLine(QPointF(9, 18), QPointF(15, 18))


def _split(p: QPainter):
    # 一张纸被虚线切成两半
    p.drawRoundedRect(QRectF(3, 3, 18, 8), 1.4, 1.4)
    p.drawRoundedRect(QRectF(3, 13, 18, 8), 1.4, 1.4)
    pen = p.pen()
    pen.setStyle(Qt.DashLine)
    p.setPen(pen)
    p.drawLine(QPointF(1.5, 12), QPointF(22.5, 12))


def _shelf(p: QPainter):
    # 三本竖立的书 + 一条搁板
    p.drawRect(QRectF(3, 5, 4.2, 13))
    p.drawRect(QRectF(8.2, 3, 4.2, 15))
    p.drawLine(QPointF(14.4, 7), QPointF(18.6, 5.6))     # 斜靠的一本
    p.drawLine(QPointF(15.2, 9.6), QPointF(19.4, 8.2))
    p.drawLine(QPointF(14.4, 7), QPointF(15.2, 9.6))
    p.drawLine(QPointF(18.6, 5.6), QPointF(19.4, 8.2))
    p.drawLine(QPointF(2, 19.5), QPointF(21, 19.5))       # 搁板


def _cut(p: QPainter):
    # 一张纸，左边一窄条被虚线撕下（封面素材 / 正文分开）
    p.drawRoundedRect(QRectF(3, 3, 18, 18), 1.6, 1.6)
    pen = p.pen()
    pen.setStyle(Qt.DashLine)
    p.setPen(pen)
    p.drawLine(QPointF(8.5, 3), QPointF(8.5, 21))
    pen.setStyle(Qt.SolidLine)
    p.setPen(pen)
    p.drawLine(QPointF(12, 9), QPointF(18, 9))
    p.drawLine(QPointF(12, 13), QPointF(18, 13))


def _pipeline(p: QPainter):
    # 三个节点串成一条线（生产线的七道工序）
    p.drawEllipse(QRectF(2.5, 3, 6, 6))
    p.drawEllipse(QRectF(15.5, 3, 6, 6))
    p.drawEllipse(QRectF(9, 15, 6, 6))
    p.drawLine(QPointF(8.5, 6), QPointF(15.5, 6))
    p.drawLine(QPointF(6.2, 8.6), QPointF(10.2, 15.2))
    p.drawLine(QPointF(17.8, 8.6), QPointF(13.8, 15.2))


def _convert(p: QPainter):
    # 一本书 → 一张纸（格式转换）
    p.drawRoundedRect(QRectF(2.5, 4, 7.5, 16), 1.2, 1.2)
    p.drawLine(QPointF(4.5, 8), QPointF(8, 8))
    p.drawLine(QPointF(4.5, 11.5), QPointF(8, 11.5))
    p.drawLine(QPointF(11, 12), QPointF(15.5, 12))
    p.drawLine(QPointF(13.6, 9.8), QPointF(15.8, 12))
    p.drawLine(QPointF(13.6, 14.2), QPointF(15.8, 12))
    p.drawRoundedRect(QRectF(16.5, 5, 5, 14), 1.0, 1.0)


DRAW = {
    "booklet": _booklet,
    "cover": _cover,
    "stack": _stack,
    "fourup": _fourup,
    "a5toa4": _a5toa4,
    "merge": _merge,
    "split": _split,
    "cut": _cut,
    "shelf": _shelf,
    "pipeline": _pipeline,
    "convert": _convert,
    "pager": _pager,
    "print": _print,
}
