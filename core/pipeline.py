"""生产线上的两个「原件操作」：分割（析出封面素材 / 正文）。

原程序只提供"拼版时从第几页开始"，但它不改文件；生产线要求的是**切出正文**，
后面加页码、排版都基于正文，封面素材单独拿去做封面。所以这里补一个真正的切分。

只做两件事：
- 前 N 页 → `<原名>-封面素材.pdf`
- 去掉尾部 M 页（封底），剩下 → `<原名>-正文.pdf`
"""

from __future__ import annotations

import os

from core.shelf.model import KIND_BODY, KIND_COVER_BACK, KIND_COVER_SRC, Item, Project


def unique_path(path: str) -> str:
    """重名不覆盖：a.pdf → a-2.pdf。"""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{stem}-{i}{ext}"):
        i += 1
    return f"{stem}-{i}{ext}"


def _save(doc, path: str) -> None:
    """先写临时文件再替换，避免中途失败留下半个 PDF。"""
    tmp = path + ".tmp"
    doc.save(tmp, garbage=3, deflate=True)
    os.replace(tmp, path)


def split_pdf(src: str, front: int = 2, tail: int = 1, out_dir: str | None = None,
              overwrite: bool = True) -> dict:
    """把源 PDF 切成封面素材 + 正文。

    front: 前几页算封面素材（0 表示不分封面）
    tail : 末尾几页算封底素材（也进封面，不再丢弃）
    返回 {"cover":…, "back":…, "body":…, "pages": (封面, 封底, 正文)}
    """
    import pymupdf

    if not os.path.exists(src):
        raise FileNotFoundError(src)
    front = max(0, int(front))
    tail = max(0, int(tail))

    with pymupdf.open(src) as doc:
        total = doc.page_count
        if total == 0:
            raise ValueError("源 PDF 没有页面")
        body_start, body_end = front, total - tail
        if body_end - body_start < 1:
            raise ValueError(
                f"分割参数不合理：共 {total} 页，从前 {front} 页之后到倒数 {tail} 页之前已经没内容了"
            )
        out_dir = out_dir or os.path.dirname(os.path.abspath(src))
        stem = os.path.splitext(os.path.basename(src))[0]

        def target(name: str) -> str:
            path = os.path.join(out_dir, name)
            return path if overwrite else unique_path(path)

        body_path = target(f"{stem}-正文.pdf")
        body = pymupdf.open()
        body.insert_pdf(doc, from_page=body_start, to_page=body_end - 1)
        body_pages = body.page_count
        _save(body, body_path)
        body.close()

        cover_path = None
        if front > 0:
            cover_path = target(f"{stem}-封面素材.pdf")
            cover = pymupdf.open()
            cover.insert_pdf(doc, from_page=0, to_page=front - 1)
            _save(cover, cover_path)
            cover.close()

        back_path = None
        if tail > 0:
            back_path = target(f"{stem}-封底素材.pdf")
            back = pymupdf.open()
            back.insert_pdf(doc, from_page=total - tail, to_page=total - 1)
            _save(back, back_path)
            back.close()

    return {"cover": cover_path, "back": back_path, "body": body_path,
            "pages": (front if cover_path else 0, tail if back_path else 0, body_pages)}


def existing_files(src: str, front: int, tail: int) -> dict | None:
    """目录里已经有同样参数切好的三个文件，就返回它们（不依赖书架）。"""
    if not src:
        return None
    folder = os.path.dirname(os.path.abspath(src))
    stem = os.path.splitext(os.path.basename(src))[0]
    paths = {"cover": os.path.join(folder, f"{stem}-封面素材.pdf") if front else None,
             "back": os.path.join(folder, f"{stem}-封底素材.pdf") if tail else None,
             "body": os.path.join(folder, f"{stem}-正文.pdf")}
    if not all(p is None or os.path.exists(p) for p in paths.values()):
        return None
    import pymupdf

    try:
        with pymupdf.open(src) as d:
            total = d.page_count
        with pymupdf.open(paths["body"]) as d:
            body_pages = d.page_count
        cover_pages = 0
        if paths["cover"]:
            with pymupdf.open(paths["cover"]) as d:
                cover_pages = d.page_count
        back_pages = 0
        if paths["back"]:
            with pymupdf.open(paths["back"]) as d:
                back_pages = d.page_count
    except Exception:                                  # noqa: BLE001
        return None
    # 现有文件的页数必须和当前参数吻合，否则说明参数改过，要重切
    if cover_pages != (front if paths["cover"] else 0):
        return None
    if back_pages != (tail if paths["back"] else 0):
        return None
    if cover_pages + back_pages + body_pages != total:
        return None
    return {"cover": paths["cover"], "back": paths["back"], "body": paths["body"],
            "pages": (cover_pages, back_pages, body_pages)}


def existing_split(project: Project, front: int, tail: int) -> dict | None:
    if not project.source:
        return None
    return existing_files(project.source.path, front, tail)


def register_split(project: Project, res: dict, front: int, tail: int) -> dict:
    """把已经切好的文件登记进这本书（产物 + 页数）。"""

    if res.get("cover"):
        it = Item.of(res["cover"], KIND_COVER_SRC)
        it.pages = res["pages"][0]
        project.add_item(it)
    if res.get("back"):
        it = Item.of(res["back"], KIND_COVER_BACK)
        it.pages = res["pages"][1]
        project.add_item(it)
    body = Item.of(res["body"], KIND_BODY)
    body.pages = res["pages"][2]
    project.add_item(body)
    project.params.setdefault("SplitPage", {})
    project.params["SplitPage"].update(front=front, tail=tail)
    return res


def apply_split(project: Project, front: int = 2, tail: int = 1) -> dict:
    """切分 + 登记。已有同样结果时直接复用。"""
    if not project.source:
        raise ValueError("这本书没有原稿")
    res = existing_split(project, front, tail)
    if res is None:
        res = split_pdf(project.source.path, front=front, tail=tail)
    return register_split(project, res, front, tail)
