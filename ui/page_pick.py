"""从 PDF 里挑一页当图用（封面图 / 封底图）。

封面页的图槽直接吃 PDF 时只会取第一页；而扫描版漫画的「封面素材」常常有
封面 + 扉页两页，用户要能自己挑。这里给一个看得见缩略图的选择框，
选完把那一页渲染成 PNG（220dpi），再交给封面页的图槽。
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QListWidgetItem as _Item,  # noqa: F401  兼容旧名
    QVBoxLayout,
)

CACHE = Path(os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")) \
    / "XPlus" / "BookTool" / "cover"


def _doc(path: str):
    import pymupdf

    return pymupdf.open(path)


def page_pixmap(pdf: str, page: int, dpi: int = 120) -> QPixmap | None:
    try:
        with _doc(pdf) as doc:
            if doc.page_count == 0:
                return None
            pg = doc[min(max(0, page), doc.page_count - 1)]
            pix = pg.get_pixmap(dpi=dpi, alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                         QImage.Format_RGB888).copy()
            return QPixmap.fromImage(img)
    except Exception:                                    # noqa: BLE001
        return None


def extract_page_image(pdf: str, page: int, dpi: int = 220) -> str | None:
    """把 PDF 的某一页存成 PNG，返回路径（带缓存）。"""
    if not pdf or not os.path.exists(pdf):
        return None
    try:
        st = os.stat(pdf)
        key = hashlib.sha1(f"{os.path.abspath(pdf)}|{st.st_size}|{int(st.st_mtime)}|{page}"
                           .encode("utf-8")).hexdigest()[:20]
    except OSError:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    import re as _re

    stem = os.path.splitext(os.path.basename(pdf))[0]
    safe = _re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5._-]+", "-", stem)[:36].strip("-")
    out = CACHE / f"{safe or 'page'}-p{page + 1}-{key[:6]}.png"
    if out.exists() and out.stat().st_size > 0:
        return str(out)
    try:
        import pymupdf

        with pymupdf.open(pdf) as doc:
            if doc.page_count == 0:
                return None
            pg = doc[min(max(0, page), doc.page_count - 1)]
            pix = pg.get_pixmap(dpi=dpi, alpha=False)
            pix.save(str(out))
        return str(out)
    except Exception:                                    # noqa: BLE001
        return None


class PagePicker(QDialog):
    """缩略图挑页：左边所有页，右边放大预览。"""

    def __init__(self, pdf: str, title: str = "选一页", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.pdf = pdf
        self.page = 0
        self.resize(720, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        hint = QLabel(f"{os.path.basename(pdf)}　·　点左边选一页")
        hint.setStyleSheet("color:#6B6459;font-size:11px;")
        root.addWidget(hint)

        body = QHBoxLayout()
        body.setSpacing(12)

        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setIconSize(QSize(84, 118))
        self.grid.setGridSize(QSize(102, 148))
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setMovement(QListWidget.Static)
        self.grid.setSpacing(4)
        self.grid.setUniformItemSizes(True)
        self.grid.setStyleSheet(
            "QListWidget{background:#FCFAF5;border:1px solid #E4DDD1;border-radius:6px;outline:0;}"
            "QListWidget::item{border-radius:4px;padding:3px;color:#6B6459;}"
            "QListWidget::item:selected{background:#F3E3DF;color:#1E1B18;}"
        )
        self.grid.currentRowChanged.connect(self._on_pick)
        body.addWidget(self.grid, 1)

        self.preview = QLabel()
        self.preview.setFixedSize(300, 440)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet(
            "QLabel{background:#FCFAF5;border:1px solid #E4DDD1;border-radius:6px;color:#7E7568;}"
        )
        body.addWidget(self.preview)
        root.addLayout(body)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("用这一页")
        box.button(QDialogButtonBox.Cancel).setText("取消")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        root.addWidget(box)

        self._fill()

    def _fill(self) -> None:
        try:
            with _doc(self.pdf) as doc:
                total = doc.page_count
        except Exception:                                # noqa: BLE001
            total = 0
        for i in range(total):
            pm = page_pixmap(self.pdf, i, dpi=36)
            it = QListWidgetItem(QIcon(pm), str(i + 1))
            it.setTextAlignment(Qt.AlignHCenter)
            it.setSizeHint(QSize(96, 142))
            self.grid.addItem(it)
        if total:
            self.grid.setCurrentRow(0)

    def _on_pick(self, row: int) -> None:
        if row < 0:
            return
        self.page = row
        pm = page_pixmap(self.pdf, row, dpi=150)
        if pm is not None:
            self.preview.setPixmap(pm.scaled(QSize(296, 436), Qt.KeepAspectRatio,
                                             Qt.SmoothTransformation))
            self.preview.setText("")

    @staticmethod
    def choose(pdf: str, title: str, parent=None) -> tuple[int | None, str | None]:
        """弹框选页，返回 (页号, 该页导出的 PNG 路径)；取消返回 (None, None)。"""
        dlg = PagePicker(pdf, title, parent)
        if dlg.exec() != QDialog.Accepted:
            return None, None
        return dlg.page, extract_page_image(pdf, dlg.page)
