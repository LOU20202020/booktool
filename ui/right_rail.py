"""右侧栏一键收起/展开。

原程序的页面（封面页）右侧是一整列卡片（版式 / 配色 / 封面文字 / 书脊），
中间画布被挤得只剩一半。这里在**右栏顶部**放一个小按钮：
点一下收起右栏、画布变宽；再点一下展开。

按钮是页面上的浮层（不放进右栏内部），所以右栏藏起来时它还在原地，
位置随窗口尺寸重算，锚在右上角。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QTimer, Qt
from PySide6.QtWidgets import QScrollArea, QToolButton, QWidget

CLOSE_GLYPH = "×"
OPEN_LABEL = "右\n侧\n栏"
BTN_W = 26
RAIL_W = 20


class RightRail(QObject):
    def __init__(self, page: QWidget, target: QWidget) -> None:
        super().__init__(page)
        self.page = page
        self.target = target
        self.collapsed = False
        self._muted: dict[int, str] = {}

        self.btn = QToolButton(page)
        self.btn.setObjectName("RailToggle")
        self.btn.setText(CLOSE_GLYPH)
        self.btn.setToolTip("关闭右侧栏")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setFixedSize(BTN_W, BTN_W)
        self.btn.setStyleSheet(
            "QToolButton#RailToggle{background:#FCFAF5;border:1px solid #E4DDD1;"
            "border-radius:5px;color:#6B6459;font-size:13px;padding:0;}"
            "QToolButton#RailToggle:hover{border-color:#B23A2E;color:#B23A2E;background:#FFF8F6;}"
        )
        self.btn.clicked.connect(self.toggle)
        self.btn.raise_()
        self.btn.show()          # 父页面已经显示出来之后才建这个按钮，必须显式 show
        page.installEventFilter(self)
        QTimer.singleShot(0, self.reposition)

    # ── 行为 ───────────────────────────────────────────────────────────
    def toggle(self) -> None:
        self.set_collapsed(not self.collapsed)

    def set_collapsed(self, collapsed: bool, remember: bool = True) -> None:
        self.collapsed = collapsed
        self.target.setVisible(not collapsed)
        # 收起 = 连它的功能一起关掉：把右栏里的文字临时清空，封面只剩图片
        try:
            from ui.cover_effects import mute_texts, restore_texts

            if collapsed and not self._muted:
                self._muted = mute_texts(self.target)
            elif not collapsed:
                restore_texts(self.target, self._muted or None)
                self._muted = {}
        except Exception:                                # noqa: BLE001
            pass
        if collapsed:
            self.btn.setText(OPEN_LABEL)
            self.btn.setToolTip("打开右侧栏")
            self.btn.setFixedSize(RAIL_W, 66)
            self.btn.setStyleSheet(
                "QToolButton#RailToggle{background:#FCFAF5;border:1px solid #E4DDD1;"
                "border-radius:5px;color:#6B6459;font-size:9px;padding:0;}"
                "QToolButton#RailToggle:hover{border-color:#B23A2E;color:#B23A2E;"
                "background:#FFF8F6;}"
            )
        else:
            self.btn.setText(CLOSE_GLYPH)
            self.btn.setToolTip("关闭右侧栏")
            self.btn.setFixedSize(BTN_W, BTN_W)
            self.btn.setStyleSheet(
                "QToolButton#RailToggle{background:#FCFAF5;border:1px solid #E4DDD1;"
                "border-radius:5px;color:#6B6459;font-size:13px;padding:0;}"
                "QToolButton#RailToggle:hover{border-color:#B23A2E;color:#B23A2E;"
                "background:#FFF8F6;}"
            )
        if False:                                        # 不落盘：避免把清空后的文字存进配置
            self._remember()
        self.reposition()
        self.btn.raise_()
        # 收起/展开后让封面预览重画一次，否则画面上还是旧的那张
        try:
            refresh = getattr(self.page, "refresh_preview", None)
            if callable(refresh):
                refresh()
        except Exception:                                # noqa: BLE001
            pass

    # ── 记忆（关掉之后下次进来还是关着的）─────────────────────────────
    def _key(self) -> str:
        return f"ui/rail/{type(self.page).__name__}_collapsed"

    def _remember(self) -> None:
        try:
            from PySide6.QtCore import QSettings

            QSettings("XPlus", "BookTool").setValue(self._key(), "1" if self.collapsed else "0")
        except Exception:                                # noqa: BLE001
            pass

    def restore(self) -> None:
        try:
            from PySide6.QtCore import QSettings

            val = QSettings("XPlus", "BookTool").value(self._key(), "0")
            if str(val) in ("1", "true", "True"):
                self.set_collapsed(True, remember=False)
        except Exception:                                # noqa: BLE001
            pass

    # ── 位置 ───────────────────────────────────────────────────────────
    def _panel_left(self) -> int:
        try:
            p = self.target.mapTo(self.page, QPoint(0, 0))
            if 0 < p.x() < self.page.width() - 40:
                return p.x()
        except Exception:                                # noqa: BLE001
            pass
        return self.page.width() - 360

    def _panel_top(self) -> int:
        try:
            p = self.target.mapTo(self.page, QPoint(0, 0))
            if 0 <= p.y() < self.page.height() - 40:
                return max(10, p.y() + 6)
        except Exception:                                # noqa: BLE001
            pass
        return 22

    def reposition(self) -> None:
        page_w, y = self.page.width(), self._panel_top()
        if self.collapsed:
            x = page_w - RAIL_W - 8           # 收起后贴在页面右边缘
            y = max(10, y)
        else:
            x = page_w - BTN_W - 26           # 展开时在右栏右上角
        self.btn.move(max(8, x), y)

    def eventFilter(self, obj, ev) -> bool:            # noqa: N802
        if obj is self.page and ev.type() in (QEvent.Resize, QEvent.Show):
            QTimer.singleShot(0, self.reposition)
        return False


def find_right_area(page: QWidget, markers=("版式", "配色")) -> QScrollArea | None:
    """按内容认右栏：哪个滚动区里出现「版式」「配色」这些字样就是它。"""
    from PySide6.QtWidgets import QLabel

    best = None
    for area in page.findChildren(QScrollArea):
        inner = area.widget()
        if inner is None:
            continue
        texts = {l.text().strip() for l in inner.findChildren(QLabel)}
        if any(m in texts for m in markers):
            if best is None or area.geometry().x() > best.geometry().x():
                best = area
    return best


def attach_page_right_rail(page: QWidget, markers=("版式", "配色")) -> RightRail | None:
    area = find_right_area(page, markers)
    if area is None:
        return None
    rail = RightRail(page, area)
    page._right_rail = rail            # 方便调试/自检
    return rail
