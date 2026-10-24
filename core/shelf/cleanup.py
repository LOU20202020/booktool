"""清理中间产物：只删"派生出来的那几份"，原稿和定稿永远不碰。

规则（和 docs/SHELF-PLAN.md §9 一致）：
- 只考虑登记在这本书 items 里的文件，不动目录里别的东西；
- 不删原稿（source）；
- 不删定稿（final）；
- 不删手动加入的项（Item.manual）；
- 默认也不删 `-正文.pdf`：后面拼版/加页码还要用它，删了就得重切；
- 每次删除都返回逐文件结果，删不掉的（被占用/没权限）单独报，不静默吞掉。
"""

from __future__ import annotations

import os

from .model import (KIND_A4A4, KIND_BODY, KIND_BOOKLET, KIND_COVER, KIND_COVER_BACK,
                    KIND_COVER_SRC, KIND_DUP, KIND_FOURSTACK, KIND_FOURUP, KIND_OTHER,
                    KIND_PAGED, Item, Project)

#: 算"中间产物"的种类（除正文以外的派生文件）
PRODUCT_KINDS = {
    KIND_COVER_SRC, KIND_COVER_BACK, KIND_COVER,
    KIND_PAGED, KIND_BOOKLET, KIND_FOURSTACK, KIND_FOURUP, KIND_A4A4,
    KIND_DUP, KIND_OTHER,
}


def candidates(project: Project, keep_body: bool = True) -> list[Item]:
    """这台书里可以删的中间产物（不含原稿 / 定稿 / 手动项 / 默认的正文）。"""
    final = os.path.abspath(project.final) if project.final else ""
    src = os.path.abspath(project.source.path) if project.source and project.source.path else ""
    out: list[Item] = []
    for item in project.items:
        if not item.path:
            continue
        path = os.path.abspath(item.path)
        if path in (final, src):
            continue
        if item.manual:
            continue
        if item.kind == KIND_BODY and keep_body:
            continue
        if item.kind == KIND_BODY or item.kind in PRODUCT_KINDS:
            out.append(item)
    return out


def total_size(items: list[Item]) -> int:
    total = 0
    for item in items:
        try:
            total += os.path.getsize(item.path)
        except OSError:
            continue
    return total


def delete(project: Project, items: list[Item]) -> dict:
    """真删。返回 {'deleted': [path], 'failed': [(path, 原因)], 'freed': 字节}。"""
    deleted: list[str] = []
    failed: list[tuple[str, str]] = []
    freed = 0
    final = os.path.abspath(project.final) if project.final else ""
    src = os.path.abspath(project.source.path) if project.source and project.source.path else ""

    for item in items:
        path = os.path.abspath(item.path)
        if path in (final, src):
            failed.append((path, "原稿或定稿，不能删"))
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        try:
            if os.path.exists(path):
                os.remove(path)
                freed += size
            deleted.append(path)
        except OSError as exc:
            failed.append((path, f"{type(exc).__name__}: {exc}"))

    gone = {os.path.abspath(p) for p in deleted}
    project.items = [i for i in project.items if os.path.abspath(i.path) not in gone]
    project.missing = [p for p in project.missing if os.path.abspath(p) not in gone]
    if project.final and os.path.abspath(project.final) in gone:      # 兜底，正常不会发生
        project.final = None
    return {"deleted": deleted, "failed": failed, "freed": freed}


def human_size(n: int) -> str:
    n = max(0, int(n))
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1024 / 1024:.1f} MB"
