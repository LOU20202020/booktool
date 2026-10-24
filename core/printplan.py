"""打印计划：把"这一本到底怎么打"算清楚，存进 Project.print_plan。

以前这个字段是死的（模型里有、没人写），生产线第⑥步只能说"还没打印"。
现在它记录：

    layout     要打的那份成品（哪一帖就是哪个文件）
    kind       小册子 / 四堆叠 / 4合1 / A4 拼版
    pages      成品几面
    sheets     要用几张纸（双面减半，乘份数）
    duplex     双面方向（short/long/none）
    signatures 小册子的帖明细：[{index, pages, sheets}]，做胶装分册时要照着打
    paper/copies/at

注意：帖数依赖"每册几面"这个设置，值来自小册子页最近一次用的参数
（界面把 QSettings 里的 每册页数 / 起始页 传进来），没有就用默认 20 面/帖。
"""

from __future__ import annotations

import math
import os

from core import pdfops
from core.shelf.model import (KIND_A4A4, KIND_BOOKLET, KIND_FOURSTACK, KIND_FOURUP,
                              KIND_LABELS, now_iso, Project)

LABELS = {
    KIND_BOOKLET: "小册子",
    KIND_FOURSTACK: "四堆叠",
    KIND_FOURUP: "4合1",
    KIND_A4A4: "A4 拼版",
}

#: 小册子默认每册几面（20 面 = 5 张纸）
DEFAULT_PAGES_PER_SIG = 20


def _as_int(value, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def build(project: Project, params: dict | None = None,
          duplex: str = "short", copies: int = 1, paper: str = "A4") -> dict:
    """按这本书现有的成品算一份打印计划；没有成品就返回 {}。"""
    layout = project.layout_item()
    if layout is None or not layout.path:
        return {}
    pages = _as_int(layout.pages, 0)
    plan: dict = {
        "layout": layout.path,
        "kind": layout.kind,
        "kind_label": LABELS.get(layout.kind, KIND_LABELS.get(layout.kind, "")),
        "pages": pages,
        "duplex": duplex,
        "copies": max(1, _as_int(copies, 1)),
        "paper": paper,
        "signatures": [],
        "at": now_iso(),
    }

    if layout.kind == KIND_BOOKLET and pages > 0:
        params = params or {}
        per_sig = _as_int(params.get("每册页数"), DEFAULT_PAGES_PER_SIG)
        per_sig = max(4, per_sig - per_sig % 4)
        start = max(1, _as_int(params.get("起始页"), 1))
        try:
            groups = pdfops.booklet_plan(pages, max_sheets=max(1, per_sig // 4),
                                         start_page=start)
        except Exception:                       # noqa: BLE001
            groups = []
        plan["per_sig"] = per_sig
        plan["signatures"] = [
            {"index": i + 1, "pages": g.get("count", 0), "sheets": len(g.get("sheets") or [])}
            for i, g in enumerate(groups)
        ]
        plan["sheets"] = sum(s["sheets"] for s in plan["signatures"]) or 0
    elif pages > 0:
        per_sheet = 2 if duplex not in ("", "none") else 1
        plan["sheets"] = int(math.ceil(pages / per_sheet))
    else:
        plan["sheets"] = 0

    plan["sheets_total"] = plan["sheets"] * plan["copies"]
    return plan


def summary(plan: dict) -> str:
    """一行话：'10 帖 · 26 张 · 双面短边 · A4'。"""
    if not plan:
        return ""
    bits = []
    if plan.get("signatures"):
        bits.append(f"{len(plan['signatures'])} 帖")
    if plan.get("sheets"):
        bits.append(f"{plan['sheets']} 张")
    if int(plan.get("copies") or 1) > 1:
        bits.append(f"×{plan['copies']} 份")
    duplex = plan.get("duplex")
    bits.append({"short": "双面短边", "long": "双面长边", "none": "单面"}.get(duplex, ""))
    if plan.get("paper"):
        bits.append(plan["paper"])
    return " · ".join(b for b in bits if b)


def is_stale(plan: dict, project: Project) -> bool:
    """成品换过（或没了）就算计划过期。"""
    if not plan or not plan.get("layout"):
        return True
    layout = project.layout_item()
    if layout is None:
        return True
    if os.path.abspath(plan["layout"]) != os.path.abspath(layout.path):
        return True
    return _as_int(plan.get("pages"), 0) != _as_int(layout.pages, 0)
