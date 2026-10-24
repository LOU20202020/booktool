"""缩略图缓存：书的首页渲成小图，按 (路径+大小+时间) 做键。

书架、生产线节点都要用，所以单独一层；不缓存像素到内存，
只把 PNG 落在 %LOCALAPPDATA%\\XPlus\\BookTool\\thumbs\\，下次直接读文件。
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


def _cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "XPlus" / "BookTool" / "thumbs"


CACHE = _cache_dir()


def _key(pdf: str, page: int = 0) -> str:
    try:
        st = os.stat(pdf)
        raw = f"{os.path.abspath(pdf)}|{st.st_size}|{int(st.st_mtime)}|{page}"
    except OSError:
        raw = f"{os.path.abspath(pdf)}|{page}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def thumb(pdf: str, width: int = 200, page: int = 0) -> str | None:
    """返回缩略图 PNG 的路径；渲染失败返回 None（界面画占位框）。

    page 从 0 开始：分割页要同时看"封面素材第 1 页"和"正文第 1 页"。
    """
    if not pdf or not os.path.exists(pdf):
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{_key(pdf, page)}-{width}.png"
    if out.exists() and out.stat().st_size > 0:
        return str(out)
    try:
        import pymupdf

        with pymupdf.open(pdf) as doc:
            if doc.page_count == 0:
                return None
            if doc.page_count == 0:
                return None
            pg = doc[min(max(0, page), doc.page_count - 1)]
            zoom = max(0.2, width / max(1.0, pg.rect.width))
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            pix.save(str(out))
        return str(out)
    except Exception:                                  # noqa: BLE001
        return None


def clear(pdf: str | None = None, width: int = 200) -> None:
    """清缓存：给某本书清，或整库清（设置里用）。"""
    if not CACHE.exists():
        return
    if pdf is None:
        for f in CACHE.glob("*.png"):
            f.unlink(missing_ok=True)
        return
    p = CACHE / f"{_key(pdf)}-{width}.png"
    p.unlink(missing_ok=True)
