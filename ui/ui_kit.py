"""新页面用的「原生外观」小工具。

移植时新增的页面（书架 / 生产线 / 分割）以前各自写了一套样式，颜色、字号、
圆角都跟原程序有出入。这里把原程序真正在用的那一套数值集中起来：

- 卡片：`ui.widgets.Card`，内边距 16/14/16/14，控件间距 10
- 小节标题：`ui.widgets.SectionLabel`（10px、字距 2、#7E7568）
- 行标题：普通 QLabel，颜色 #6B6459，宽度 84（原程序所有参数行都是这个宽度）
- 列表：背景 #FCFAF5、边框 #E4DDD1、圆角 6、字号 10.5pt、item 内边距 7/8、
  分隔线 #EFE9DE、选中 #F3E3DF
- 主按钮：objectName "Primary"（朱红）；其余按钮不写样式，吃全局 QSS
- 数字输入：`ui.widgets.Stepper`（高 28，值框 92 宽）

新页面一律从这里取，不再自己调色。
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QPushButton, QSpinBox, QTreeWidget, QWidget

from ui.theme import INK, INK2, INK3, LINE, LINE2, RED, RED_SOFT
from ui.widgets import SectionLabel, Stepper  # noqa: F401  （页面直接用）

ROW_LABEL_W = 84
ROW_H = 30

# 与 MergePage 里的列表样式逐字一致
LIST_QSS = (
    "QListWidget{background:#FCFAF5;border:1px solid #E4DDD1;border-radius:6px;"
    "font-size:10.5pt;color:#1E1B18;outline:0;}"
    "QListWidget::item{padding:7px 8px;border-bottom:1px solid #EFE9DE;}"
    "QListWidget::item:selected{background:#F3E3DF;color:#1E1B18;}"
)

TREE_QSS = (
    "QTreeWidget{background:#FCFAF5;border:1px solid #E4DDD1;border-radius:6px;"
    "font-size:10.5pt;color:#1E1B18;outline:0;}"
    "QTreeWidget::item{padding:6px 6px;border-bottom:1px solid #EFE9DE;}"
    "QTreeWidget::item:selected{background:#F3E3DF;color:#1E1B18;}"
    "QTreeWidget::item:selected:!active{background:#F3E3DF;color:#1E1B18;}"
    "QTreeWidget{selection-background-color:#F3E3DF;selection-color:#1E1B18;}"
    "QTreeView::branch{background:transparent;border:none;}"
    "QTreeView::branch:selected{background:transparent;}"
)

PANEL_QSS = "QLabel{background:#FCFAF5;border:1px solid #E4DDD1;border-radius:6px;}"


def make_list() -> QListWidget:
    lw = QListWidget()
    lw.setStyleSheet(LIST_QSS)
    return lw


def make_tree() -> QTreeWidget:
    tw = QTreeWidget()
    tw.setStyleSheet(TREE_QSS)
    tw.setHeaderHidden(True)
    tw.setIndentation(12)
    tw.setUniformRowHeights(True)
    return tw


def primary(btn: QPushButton) -> QPushButton:
    btn.setObjectName("Primary")
    return btn


def plain_btn(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(btn_cursor())
    return b


def btn_cursor():
    from PySide6.QtCore import Qt
    return Qt.PointingHandCursor


def group_title(text: str) -> QLabel:
    """卡片里的小标题（衬线 13px），比 SectionLabel 更"正文"。"""
    lab = QLabel(text)
    lab.setObjectName("GroupTitle")
    return lab


def key_label(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet(f"color:{INK2};")
    lab.setFixedWidth(ROW_LABEL_W)
    return lab


def value_label(text: str = "") -> QLabel:
    lab = QLabel(text)
    lab.setStyleSheet(f"color:{INK};")
    lab.setWordWrap(True)
    return lab


def row(text: str, widget: QWidget, label_w: int = ROW_LABEL_W, spacing: int = 8) -> QHBoxLayout:
    """一行「标签 + 控件」，标签宽度和原程序一致（84px），行高 30。"""
    lay = QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    lab = QLabel(text)
    lab.setStyleSheet(f"color:{INK2};")
    lab.setFixedWidth(label_w)
    lay.addWidget(lab)
    widget.setMinimumHeight(ROW_H - 2)
    lay.addWidget(widget, 1)
    return lay


def stepper(value: int = 0, lo: int = 0, hi: int = 99, on_change=None) -> Stepper:
    st = Stepper(value, lo, hi)
    if on_change is not None:
        from PySide6.QtWidgets import QLineEdit

        le = st.findChild(QLineEdit)
        if le is not None:
            le.textChanged.connect(lambda *_: on_change(st.value()))
    return st


def thin_divider() -> QWidget:
    from PySide6.QtWidgets import QFrame

    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color:{LINE};background:{LINE};max-height:1px;border:none;")
    return f


def panel_label(text: str = "") -> QLabel:
    """预览 / 缩略图那种浅底面板。"""
    lab = QLabel(text)
    lab.setAlignment(btn_alignment())
    lab.setStyleSheet(PANEL_QSS + f"QLabel{{color:{INK3};font-size:11px;}}")
    return lab


def btn_alignment():
    from PySide6.QtCore import Qt
    return Qt.AlignCenter


__all__ = [
    "SectionLabel", "Stepper", "LIST_QSS", "TREE_QSS", "PANEL_QSS",
    "ROW_LABEL_W", "ROW_H", "INK", "INK2", "INK3", "LINE", "LINE2", "RED", "RED_SOFT",
    "make_list", "make_tree", "primary", "plain_btn", "group_title", "key_label",
    "value_label", "row", "stepper", "thin_divider", "panel_label",
]
