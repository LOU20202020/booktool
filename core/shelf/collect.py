"""书架的文件收集器：从原稿所在目录里认出"这本书的产物"。

只认事实，不做决定：
- 同目录 + 同前缀（原稿名去掉扩展名）+ .pdf → 是这本书的产物；
- 再按后缀判断是哪一步做的（小册子/四堆叠/封面/加页码/…）；
- 认不出的仍归到这本书，标成「其它」，不会被误删。

原程序的产物后缀是从字节码里核对过的：
-小册子 / -四堆叠 / -4合1 / -加页码 / -A4拼版 / 封面
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .model import (
    KIND_A4A4, KIND_BODY, KIND_BOOKLET, KIND_COVER, KIND_COVER_BACK, KIND_COVER_SRC,
    KIND_DUP, KIND_FOURSTACK, KIND_FOURUP, KIND_OTHER, KIND_PAGED,
    Item, Project, Source,
)

PDF_EXT = ".pdf"
EBOOK_EXT = (".pdf", ".mobi", ".azw3", ".epub", ".fb2", ".txt", ".docx", ".rtf", ".cbz", ".cbr")

# 顺序有讲究：先长后短（「封面素材」必须排在「封面」前面）
SUFFIX_RULES = (
    ("封面素材", KIND_COVER_SRC),
    ("封底素材", KIND_COVER_BACK),
    ("-封底", KIND_COVER_BACK),
    ("-正文", KIND_BODY),
    ("成品封面", KIND_COVER),
    ("封面", KIND_COVER),
    ("-加页码", KIND_PAGED),
    ("-小册子", KIND_BOOKLET),
    ("-四堆叠", KIND_FOURSTACK),
    ("-4合1", KIND_FOURUP),
    ("-A4拼版", KIND_A4A4),
)

# 卷号：Vol_11 / 第11卷 / v11 / (11)
VOLUME_PATTERNS = (
    re.compile(r"[Vv][Oo][Ll](?:[Uu][Mm][Ee])?[._\-\s]*(\d{1,3})"),
    re.compile(r"第\s*(\d{1,3})\s*[卷册集部]"),
    re.compile(r"[Vv](\d{1,3})(?!\d)"),
    re.compile(r"\((\d{1,3})\)"),
    re.compile(r"[_\-\s](\d{1,3})(?!\d)\s*$"),
)


DUP_RE = re.compile(r"^[-_\s]?\d{1,2}\.pdf$", re.IGNORECASE)
#: 产物后面的 -2 / -3（如「-小册子-2.pdf」）也是副本，不算新产物
DUP_TAIL_RE = re.compile(r"[-_\s]\d{1,2}\.pdf$", re.IGNORECASE)


def classify(tail: str) -> str:
    """tail 是去掉原稿前缀后的文件名部分，例如 '-小册子-2.pdf'。

    带 -2/-3 尾巴的**先**认成副本：不然「-小册子-2.pdf」会盖过正本，
    生产线第⑤⑥步就会指着一份副本说话。
    """
    if DUP_RE.match(tail) or DUP_TAIL_RE.search(tail):
        return KIND_DUP
    for key, kind in SUFFIX_RULES:
        if key in tail:
            return kind
    return KIND_OTHER


JUNK_RE = re.compile(
    r"[\(\（][^\)\）]*(?:z-?lib|1lib|libgen|annas?|archive|download|www\.|\.com|\.sk|\.org|\.net)[^\)\）]*[\)\）]",
    re.IGNORECASE,
)


def clean_name(stem: str) -> str:
    """把下载站的水印去掉，给书架一个能看的名字。"""
    s = JUNK_RE.sub(" ", stem)
    s = re.sub(r"[\[\]【】]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -_·,，")
    return s or stem


def _strip_ext(name: str) -> str:
    """只去掉真正的扩展名——文件名里常有 z-library.sk 这种点，Path.stem 会切错。"""
    low = name.lower()
    for ext in sorted(EBOOK_EXT, key=len, reverse=True):
        if low.endswith(ext):
            return name[: -len(ext)]
    return name


def parse_volume(name: str) -> tuple[int | None, str]:
    """从文件名里抽卷号，并返回去掉卷号后的书名（用来做系列名/卷名）。"""
    stem = _strip_ext(os.path.basename(name))
    base = clean_name(stem)          # 先去掉下载站水印，再找卷号
    for pat in VOLUME_PATTERNS:
        m = pat.search(base)
        if m:
            try:
                idx = int(m.group(1))
            except (TypeError, ValueError):
                continue
            if 0 < idx < 1000:
                cleaned = base[:m.start()] + " " + base[m.end():]
                cleaned = re.sub(r"[\(\)\[\]_\-]+", " ", cleaned)
                cleaned = clean_name(re.sub(r"\s+", " ", cleaned).strip())
                return idx, cleaned or base
    return None, base


def count_pages(path: str) -> int | None:
    """读页数；失败就返回 None（书架不因为一个坏文件崩掉）。"""
    try:
        import pymupdf  # 只在需要时导入
        with pymupdf.open(path) as doc:
            return doc.page_count
    except Exception:                                   # noqa: BLE001
        return None


def scan_products(project: Project, read_pages: bool = True, reader=None) -> int:
    """重扫这本书所在目录，更新 items 与 missing。返回条目数。"""
    src = project.source
    if not src or not src.path:
        return 0
    folder = os.path.dirname(src.path)
    stem = os.path.splitext(os.path.basename(src.path))[0]
    src_abs = os.path.abspath(src.path)
    get_pages = reader or count_pages

    try:
        names = os.listdir(folder)
    except OSError:
        return len(project.items)

    discovered: dict[str, Item] = {}
    for name in names:
        if not name.lower().endswith(PDF_EXT):
            continue
        path = os.path.abspath(os.path.join(folder, name))
        if path == src_abs or not name.startswith(stem):
            continue
        tail = name[len(stem):]
        item = Item.of(path, classify(tail))
        if read_pages and item.kind != KIND_OTHER:
            item.pages = get_pages(path)
        discovered[path] = item

    old = {os.path.abspath(i.path): i for i in project.items}
    merged: list[Item] = []
    missing: list[str] = []

    for path, item in discovered.items():
        prev = old.get(path)
        if prev:                                  # 保留用户/运行时的记录
            item.params = prev.params
            item.params_hash = prev.params_hash
            item.created = prev.created or item.created
            item.manual = prev.manual
            if item.kind == KIND_OTHER and prev.kind != KIND_OTHER:
                item.kind = prev.kind
            item.pages = item.pages or prev.pages
        merged.append(item)

    for path, prev in old.items():
        if path in discovered:
            continue
        if os.path.exists(path):                  # 改名/挪走但还在：按旧记录留着
            merged.append(prev)
        else:
            missing.append(path)
            if prev.manual:                       # 手动加入的不删，标失联
                merged.append(prev)

    project.items = merged
    project.missing = sorted(set(missing) | set(project.missing))
    return len(merged)


def clean_missing(project: Project) -> None:
    """把已经重新出现的文件从失联名单里去掉（界面刷新时调用）。"""
    project.missing = [p for p in project.missing if not os.path.exists(p)]


# ── 建项目 / 批量导入 ──────────────────────────────────────────────────────

def project_from_file(path: str, series_id: str | None = None,
                      read_pages: bool = True) -> Project:
    path = os.path.abspath(path)
    stem = _strip_ext(os.path.basename(path))
    index, clean = parse_volume(stem)
    src = Source.of(path)
    if read_pages and path.lower().endswith(PDF_EXT):
        src.pages = count_pages(path)
    pid = "p-" + re.sub(r"[^0-9a-zA-Z\u4e00-\u9fa5]+", "-", stem)[:40].lower()
    proj = Project(id=pid, name=clean or stem, series_id=series_id, index=index, source=src)
    if path.lower().endswith(PDF_EXT):
        scan_products(proj, read_pages=read_pages)
    return proj


def import_folder(folder: str, read_pages: bool = True) -> list[Project]:
    """拖一个文件夹进来：每个电子书文件建一卷，按卷号排好。"""
    out: list[Project] = []
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith(EBOOK_EXT):
            continue
        path = os.path.abspath(os.path.join(folder, name))
        if f"-" in name and classify(name) != KIND_OTHER:   # 产物不单独建卷
            continue
        out.append(project_from_file(path, read_pages=read_pages))
    return sorted(out, key=lambda p: (p.index if p.index is not None else 10**6, p.name))
