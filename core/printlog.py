"""打印记账：真送印成功之后，把这一次写进书架里那本书的 Project.prints。

为什么要有这一层：生产线第⑥步、书架的「打印 N 次」和「已打印」筛选都靠
`Project.prints` 判断。以前这个字段谁也没写过 —— 于是打完整本，状态还停在
「还没打印」，书架永远显示「已排版」。这里把它接上。

规矩：
- 只有真的送印成功才记；失败、取消不记；
- 只打样张（sample=True）账上留一笔，但不算第⑥步做完；
- 手动双面：正面 + 背面合起来算一次成书，记一条；只打了正面记 `odd-only`；
- 不在书架里的 PDF（随手打的原稿）不记，它只落在 print.log 里。
"""

from __future__ import annotations

import math
import os
import re

from core.shelf.model import PrintEvent, now_iso
from core.shelf.store import ShelfStore


def find_project(shelf, path: str):
    """按路径找回属于哪本书（原稿或任一产物都算）。"""
    if not path:
        return None
    target = os.path.abspath(path)
    for proj in shelf.projects:
        if proj.source and proj.source.path and os.path.abspath(proj.source.path) == target:
            return proj
        for item in proj.items:
            if item.path and os.path.abspath(item.path) == target:
                return proj
    return None


def sheets_for(pages: int, duplex: str = "short", copies: int = 1) -> int:
    """按「几面 + 单/双面 + 份数」算实际要吃多少张纸。"""
    per_sheet = 2 if duplex not in ("", "none") else 1
    return int(math.ceil(max(0, int(pages)) / per_sheet)) * max(1, int(copies or 1))


def count_pages_in_range(text: str, total: int) -> int:
    """'3-6,9' → 5。认不出来就返回 0（调用方退回整本页数）。"""
    text = (text or "").strip()
    if not text:
        return 0
    n = 0
    for part in re.split(r"[,，\s]+", text):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:\s*[-–~]\s*(\d+))?", part)
        if not m:
            return 0
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        if a > b:
            a, b = b, a
        if a < 1 or (total and b > total):
            return 0
        n += b - a + 1
    return n


def record_print(path: str, *, printer: str = "", tag: str = "", pages: int = 0,
                 copies: int = 1, duplex: str = "short", pages_text: str = "",
                 sample: bool = False, note: str = "", store: ShelfStore | None = None
                 ) -> PrintEvent | None:
    """记一笔。返回新写的 PrintEvent；这份 PDF 不归任何书时返回 None。"""
    st = store or ShelfStore()
    try:
        shelf = st.load()
    except Exception:                                    # noqa: BLE001
        return None
    proj = find_project(shelf, path)
    if proj is None:
        return None

    counted = count_pages_in_range(pages_text, pages) or int(pages or 0)
    event = PrintEvent(
        at=now_iso(),
        tag=tag or ("single" if duplex in ("", "none") else "duplex"),
        sheets=sheets_for(counted, duplex, copies),
        job=printer,
        pages=int(pages or 0),
        copies=max(1, int(copies or 1)),
        sample=bool(sample),
        note=note,
    )
    proj.prints.append(event)
    del proj.prints[:-50]                 # 只留最近 50 条，shelf.json 不会越写越大
    try:
        st.save(shelf)
    except Exception:                                    # noqa: BLE001
        return None
    return event
