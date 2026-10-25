"""把拖放事件转给页面自己处理。

为什么需要：Qt 在 Windows 上投递拖放时，是从光标下**最深的子控件**往上找第一个
`acceptDrops()` 的控件。页面里嵌了 QGraphicsView（预览画布），它的 viewport
自带 acceptDrops，于是文件被丢进画布就被 viewport 吃掉，页面自己的
`dragEnterEvent / dropEvent` 根本收不到 —— 表现就是"把 mobi 拖进去没反应"。

做法：给页面里所有"会截获拖放"的子控件装一个事件过滤器，把 DragEnter / DragMove /
Drop 直接转交给页面自己的处理函数。
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QWidget


class _DropForwarder(QObject):
    def __init__(self, page: QWidget, handler=None) -> None:
        super().__init__(page)
        self.page = page
        self.handler = handler or page

    def eventFilter(self, obj, ev) -> bool:            # noqa: N802
        etype = ev.type()
        if etype not in (QEvent.DragEnter, QEvent.DragMove, QEvent.Drop):
            return False
        # 只管"拖本地文件"；拖文字进来（比如往输入框里拖一段文本）不拦，交给控件自己
        md = ev.mimeData() if hasattr(ev, "mimeData") else None
        if not md or not md.hasUrls():
            return False
        if not any(u.isLocalFile() for u in md.urls()):
            return False
        target = self.handler
        if etype == QEvent.Drop:
            target.dropEvent(ev)
        else:
            target.dragEnterEvent(ev)
        return True


def forward_drops(page: QWidget, handler=None) -> None:
    """让页面里"抢拖放"的子控件把事件交给页面自己（或指定的 handler）。

    规则：页面所有子孙控件都装过滤器，但**子控件自己实现了 dropEvent 的除外**
    （那种是有意自己接文件的，比如封面页的图槽）。重复调用无副作用。

    handler 传主窗口时，用在场面上"页面自己不接拖放、由主窗口统一接"的工具页。
    """
    if getattr(page, "_drop_forwarder", None) is not None:
        return
    forwarder = _DropForwarder(page, handler)
    for child in page.findChildren(QWidget):
        if child is page:
            continue
        own_drop = type(child).dropEvent is not QWidget.dropEvent
        if own_drop:
            continue
        child.installEventFilter(forwarder)
    page._drop_forwarder = forwarder
