"""六个功能页的汇总导出。

页面本身已经拆到各自的文件里，这里只保留原来的 import 路径：

    from ui.pages import BookletPage, CoverPage, FourStackPage, FourUpPage, MergePage, NumberPage, SplitPage

- `page_base.py`   基类 `ToolPage`、边距提示 `margin_note`、临时目录 `TMP`
- `pages_impose.py` 拼版三页：小册子 / 四堆叠 / 4合1
- `pages_pdf.py`    PDF 三页：合并 / 分拆 / 加页码
- `cover_page.py`   封面页

为什么拆：这个文件原来 1854 行，改任何一页都要在两千行里翻。
**类名一个都没改** —— `core/shelf/model.py` 把这些名字当 `params` 的 key 存进
`shelf.json`，改名会让老书架的参数读不出来。
"""
from __future__ import annotations

from .cover_page import CoverPage
from .page_base import TMP, ToolPage, margin_note
from .pages_impose import BookletPage, FourStackPage, FourUpPage
from .pages_pdf import MergePage, NumberPage, SplitPage
# 这三个模块历史上是从 ui.pages 拿 SectionLabel 的，继续从这儿导出，免得改它们的 import
from .widgets import (CANCEL, Card, ChipGroup, Collapsible, FileCard, Hint, ImagePicker,
                      OutlinePanel, PreviewView, SectionLabel, Stepper, ThumbPanel, submit)

__all__ = [
    "TMP", "ToolPage", "margin_note",
    "BookletPage", "CoverPage", "FourStackPage", "FourUpPage",
    "MergePage", "NumberPage", "SplitPage",
]
