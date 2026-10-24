"""把「封面素材 / 封底素材」送进原程序封面页的三个图槽。

封面页（app/ui 里的 CoverPage）有三个 ImagePicker：封面图 / 书脊图 / 封底图。
它们没暴露公开 API 名称，但每个 picker 都有 `set_path(path)`，而且支持直接给
PDF（封面页的说明里写着"图可以是图片，也可以是 PDF 的某一页"）。

这里按"标签就近找控件"定位，找不到再按顺序兜底，避免把封底塞进书脊槽。
"""

from __future__ import annotations

import os

from PySide6.QtWidgets import QLabel

from ui.widgets import ImagePicker

#: 标签文字 → 槽位名
SLOTS = {"封面图": "cover", "书脊图": "spine", "封底图": "back"}
SLOTS_NAME = {"cover": "封面图", "spine": "书脊图", "back": "封底图"}
#: 兜底顺序（与封面页里三个 picker 的出现顺序一致）
FALLBACK_ORDER = ("cover", "spine", "back")


def _retitle(picker, slot: str, path: str) -> None:
    """原程序填入图片后会把标签直接换成文件名，三行都变成文件名就分不清哪行是哪个槽。

    这里给标签补回槽名：`封面图：xxx.png`，文件名过长再交给 tidy_labels 省略。
    """
    from PySide6.QtWidgets import QLabel

    labs = picker.findChildren(QLabel)
    if not labs:
        return
    lab = labs[0]
    name = os.path.basename(path)
    slot_name = SLOTS_NAME.get(slot, "")
    lab.setText(f"{slot_name}：{name}" if slot_name else name)
    lab.setToolTip(f"{slot_name}\n{path}" if slot_name else path)


def _elide(text: str, width: int, font) -> str:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFontMetrics

    fm = QFontMetrics(font)
    return fm.elidedText(text, Qt.ElideRight, max(40, width - 8))


def tidy_labels(page, max_w: int = 186) -> None:
    """封面页的图槽会把整条文件名铺出来，撑爆左栏。

    这里把过长/像文件名的标签压到 max_w，并让它在布局里"不再要求宽度"，
    否则左栏内容会被撑到 480px，右侧的数值控件整排被裁掉。
    """
    from PySide6.QtWidgets import QLabel, QSizePolicy

    for picker in page.findChildren(ImagePicker):
        for lab in picker.findChildren(QLabel):
            text = lab.text()
            if len(text) <= 22 and not text.lower().endswith(
                    (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")):
                continue
            lab.setToolTip(text)
            lab.setMaximumWidth(max_w)
            policy = lab.sizePolicy()
            policy.setHorizontalPolicy(QSizePolicy.Ignored)
            lab.setSizePolicy(policy)
            short = _elide(text, max_w, lab.font())
            if short != text:
                lab.setText(short)


def find_cover_page(win):
    pages = getattr(win, "pages", [])
    return next((p for p in pages if type(p).__name__ == "CoverPage"), None)


def _pickers_by_label(page) -> dict[str, ImagePicker]:
    """每个 ImagePicker 内部就有一个写着「封面图 / 书脊图 / 封底图」的标签，
    所以直接看 picker 自己的子标签，比按位置猜可靠。"""
    found: dict[str, ImagePicker] = {}
    for picker in page.findChildren(ImagePicker):
        for lab in picker.findChildren(QLabel):
            slot = SLOTS.get(lab.text().strip())
            if slot and slot not in found:
                found[slot] = picker
                break
    return found


def _pickers_in_order(page) -> list[ImagePicker]:
    return page.findChildren(ImagePicker)


def fill_cover(win, cover: str = "", spine: str = "", back: str = "") -> dict[str, bool]:
    """把文件塞进封面页对应的槽。返回 {槽位: 是否成功}。"""
    page = find_cover_page(win)
    if page is None:
        return {}
    result = {k: False for k in SLOTS.values()}
    by_label = _pickers_by_label(page)
    ordered = _pickers_in_order(page)
    targets = {"cover": cover, "spine": spine, "back": back}
    for slot, path in targets.items():
        if not path:
            continue
        picker = by_label.get(slot)
        if picker is None:
            idx = FALLBACK_ORDER.index(slot)
            picker = ordered[idx] if idx < len(ordered) else None
        if picker is None:
            continue
        try:
            picker.set_path(path)
            _retitle(picker, slot, path)
            result[slot] = True
        except Exception:                                # noqa: BLE001
            result[slot] = False
    tidy_labels(page)
    return {k: v for k, v in result.items() if v}


def pick_and_fill(win, slot: str, pdf: str, parent=None) -> str:
    """从 PDF 里挑一页填进某个槽（封面/书脊/封底）；只有一页时不弹框。"""
    from ui.page_pick import PagePicker, extract_page_image
    from ui.preview_kit import page_count

    if not pdf or not os.path.exists(pdf):
        return ""
    total = page_count(pdf)
    if total <= 0:
        return ""
    if total == 1:
        img = extract_page_image(pdf, 0)
    else:
        _page, img = PagePicker.choose(pdf, f"选{SLOTS_NAME.get(slot, '图')}用哪一页", parent)
    if not img:
        return ""
    fill_cover(win, **{slot: img})
    return img


def goto_cover(win) -> bool:
    page = find_cover_page(win)
    if page is None:
        return False
    pages = getattr(win, "pages", [])
    idx = pages.index(page)
    goto = getattr(win, "goto", None)
    if callable(goto):
        goto(idx)
        return True
    return False
