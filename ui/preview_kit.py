"""原程序网格画布的小封装。

工具页（小册子/封面/四堆叠…）中间那块底纹是 `ui.widgets.PreviewView` 画的：
白底 + 32px 淡网格（rgba(0,0,0,14)）。新页面要"看起来一样"就必须用它，
而不是自己刷一个纯色背景。

PreviewView 会在没有图时画一句提示文字，这里只把 drawForeground 关掉，
网格（drawBackground）保持原样。
"""

from __future__ import annotations

from PySide6.QtGui import QImage, QPixmap

from ui.widgets import PreviewView


class GridCanvas(PreviewView):
    """带原程序网格的空白画布。"""

    def drawForeground(self, *args, **kwargs) -> None:      # noqa: N802
        return

    def resizeEvent(self, ev) -> None:                       # noqa: N802
        super().resizeEvent(ev)
        if getattr(self, "item", None) is not None:          # 有图就重新铺满
            self.fit()


def render_page(path: str, page: int = 0, dpi: int = 110) -> QPixmap | None:
    """把 PDF 的某一页渲染成 QPixmap（页面从 0 开始）。"""
    try:
        import pymupdf

        with pymupdf.open(path) as doc:
            if doc.page_count == 0:
                return None
            pg = doc[min(max(0, int(page)), doc.page_count - 1)]
            pix = pg.get_pixmap(dpi=dpi, alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                         QImage.Format_RGB888).copy()
            return QPixmap.fromImage(img)
    except Exception:                                        # noqa: BLE001
        return None


def page_count(path: str) -> int:
    try:
        import pymupdf

        with pymupdf.open(path) as doc:
            return doc.page_count
    except Exception:                                        # noqa: BLE001
        return 0
