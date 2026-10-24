"""关闭右侧栏 = 关掉它的"功能"，不只是把面板藏起来。

封面页右侧那几栏（版式 / 配色 / 封面文字 / 书脊文字）会往封面上压字、上色。
导入现成的封面图之后，这些文字压在图上就是脏的。

所以：
- 收起右栏 → 把右栏里的文字字段**清空**（值备份到内存 + 设置里，防丢），封面只剩图片；
- 展开右栏 → 原样恢复。
只动右栏里的输入框，左侧尺寸/页数那些 Stepper 不碰。
"""

from __future__ import annotations

import json

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QTextEdit,
    QWidget,
)

#: 右栏里会被"关掉"的字段（按上面那行标签识别）
KEYS = ("书名", "副标题", "作者", "系列", "出版", "封底文字", "书脊文字")


def _root(area: QWidget) -> QWidget | None:
    return area.widget() if isinstance(area, QScrollArea) else area


def _text_widgets(area: QWidget) -> list[QWidget]:
    root = _root(area)
    if root is None:
        return []
    out: list[QWidget] = []
    out.extend(root.findChildren(QLineEdit))
    out.extend(root.findChildren(QTextEdit))
    out.extend(root.findChildren(QPlainTextEdit))
    return out


def _label_of(widget: QWidget) -> str:
    parent = widget.parentWidget()
    for _ in range(3):
        if parent is None:
            break
        for lab in parent.findChildren(QLabel):
            text = lab.text().strip().rstrip("：:")
            if text in KEYS:
                return text
        parent = parent.parentWidget()
    return ""


def _settings_key(area: QWidget) -> str:
    page = area.parentWidget()
    name = type(page).__name__ if page is not None else type(area).__name__
    return f"ui/rail/{name}_muted"


def _text_of(w: QWidget) -> str:
    return w.text() if isinstance(w, QLineEdit) else w.toPlainText()


def _set_text(w: QWidget, text: str) -> None:
    if isinstance(w, QLineEdit):
        w.setText(text)
    else:
        w.setPlainText(text)


def mute_texts(area: QWidget) -> dict[int, str]:
    """清空右栏文字，返回备份；同时按字段名存一份到设置里（重启也不丢）。"""
    backup: dict[int, str] = {}
    named: dict[str, str] = {}
    for w in _text_widgets(area):
        text = _text_of(w)
        if not text.strip():
            continue
        backup[id(w)] = text
        key = _label_of(w)
        if key:
            named[key] = text
        _set_text(w, "")
    return backup


def restore_texts(area: QWidget, backup: dict[int, str] | None = None) -> None:
    """把收起时清掉的文字放回去（只在内存里备份，不落盘）。"""
    if not backup:
        return
    for w in _text_widgets(area):
        text = backup.get(id(w))
        if text:
            _set_text(w, text)
