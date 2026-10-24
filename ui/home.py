"""主页面（点左上角「书」进入）：介绍功能、作者与 B 站入口。"""
from __future__ import annotations

import os

from PySide6.QtCore import QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QIcon, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QGridLayout,
                               QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from . import icons, theme

BILIBILI = "https://space.bilibili.com/702283845"
AUTHOR = "LOU0122"
ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def round_pixmap(size: int = 40) -> QPixmap:
    path = os.path.join(ASSETS, "bili_avatar.jpg")
    pm = QPixmap(path)
    if pm.isNull():
        return QPixmap()
    pm = pm.scaled(size * 2, size * 2, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = max(0, (pm.width() - size * 2) // 2)
    y = max(0, (pm.height() - size * 2) // 2)
    pm = pm.copy(x, y, size * 2, size * 2)
    out = QPixmap(size * 2, size * 2)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addEllipse(0, 0, size * 2, size * 2)
    p.setClipPath(clip)
    p.drawPixmap(0, 0, pm)
    p.end()
    out.setDevicePixelRatio(2)
    return out


def round_icon(size: int = 40) -> QIcon:
    """把 B 站头像裁成圆形图标。"""
    path = os.path.join(ASSETS, "bili_avatar.jpg")
    pm = QPixmap(path)
    if pm.isNull():
        return QIcon()
    pm = pm.scaled(size * 2, size * 2, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = max(0, (pm.width() - size * 2) // 2)
    y = max(0, (pm.height() - size * 2) // 2)
    pm = pm.copy(x, y, size * 2, size * 2)
    out = QPixmap(size * 2, size * 2)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addEllipse(0, 0, size * 2, size * 2)
    p.setClipPath(clip)
    p.drawPixmap(0, 0, pm)
    p.end()
    return QIcon(out)

TOOLS = [
    ("shelf", "书架", "按系列管所有书：原稿、正文、封面、定稿各自在位，做到第几步一眼能看出来。"),
    ("pipeline", "生产线", "一本书的七道工序：分割 → 封面 → 页码 → 排版 → 打印 → 定稿，节点直接跳转。"),
    ("booklet", "小册子打印", "骑马钉 / 胶装分册，自动补页、按帖分册。A5 或 A6 成书，一张 A4 直接出两份。"),
    ("cover", "封面制作", "封底 + 书脊 + 封面一张展开图，带 3mm 出血与竖排书脊，300dpi 直出。"),
    ("stack", "四堆叠放", "一张 A4 排 8 页，切两刀成 4 叠，做 A6 小本的省纸排法。"),
    ("fourup", "4 合 1", "4 页缩到 1 张 A4，四种排列可选，适合讲义和资料汇总。"),
    ("merge", "PDF 合并", "多份 PDF 拖一下排序，合成一本，顺序就是你要的阅读顺序。"),
    ("split", "PDF 分拆", "按页数、按份数或自定页码，切成两份或更多份，每份单独成文件。"),
    ("cut", "分割", "前 N 页析出成封面素材、末尾 M 页当封底素材，其余留成正文，直接进生产线。"),
    ("pager", "加页码", "给每页加页码：位置、格式、起始页、奇偶镜像，可选跳过封面。"),
    ("convert", "格式转换", "MOBI / AZW3 / EPUB / TXT 等电子书转成 PDF，带目录、可选纸张与页边距。"),
    ("print", "打印", "选任意 PDF 直接送印：双面短边、100% 不缩放、按面选范围，单面机自动分两遍。"),
]


class ToolCard(QFrame):
    clicked = Signal(int)

    def __init__(self, page: int, ordinal: int, key: str, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.index = page          # 点下去要跳到的页面下标
        self.setObjectName("ToolCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(178)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(f"""
            QFrame#ToolCard {{
                background: {theme.SURFACE}; border: 1px solid {theme.LINE}; border-radius: 10px;
            }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(0)

        top = QHBoxLayout()
        self.icon_label = QLabel()
        self.icon_label.setPixmap(icons.icon(key, theme.INK).pixmap(26, 26))
        top.addWidget(self.icon_label)
        top.addStretch(1)
        num = QLabel(f"{ordinal + 1:02d}")
        num.setStyleSheet("color:#D8CFC0;font-family:Georgia;font-size:22px;")
        top.addWidget(num)
        lay.addLayout(top)

        lay.addSpacing(16)
        t = QLabel(title)
        t.setStyleSheet(f"font-family:'{theme.FONT_HEAD}';font-size:17px;"
                        f"letter-spacing:1px;color:{theme.INK};")
        lay.addWidget(t)
        lay.addSpacing(6)
        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet(f"color:{theme.INK2};font-size:11.5px;")
        lay.addWidget(d)
        lay.addStretch(1)

        self.more = QLabel("打开  →")
        self.more.setStyleSheet(f"color:{theme.RED};font-size:11px;font-weight:600;")
        self.more.setVisible(False)
        lay.addWidget(self.more)

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(0)
        self._shadow.setOffset(0, 0)
        self._shadow.setColor(QColor(30, 27, 24, 40))
        self.setGraphicsEffect(self._shadow)

    def enterEvent(self, ev):
        self.setStyleSheet(f"""
            QFrame#ToolCard {{
                background: #FFFFFF; border: 1px solid {theme.RED}; border-radius: 10px;
            }}
        """)
        self.more.setVisible(True)
        self._shadow.setBlurRadius(22)
        self._shadow.setOffset(0, 6)
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.setStyleSheet(f"""
            QFrame#ToolCard {{
                background: {theme.SURFACE}; border: 1px solid {theme.LINE}; border-radius: 10px;
            }}
        """)
        self.more.setVisible(False)
        self._shadow.setBlurRadius(0)
        self._shadow.setOffset(0, 0)
        super().leaveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(ev)


class SpreadArt(QWidget):
    """右上角的装饰：一张对折的纸，带折线与裁切角标。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(258, 180)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(0.86, 0.86)          # 原图按 300×210 画的，这里整体缩到 258×180
        w, h = 262, 178
        x, y = 22, 16
        # 纸张
        p.setPen(QPen(QColor("#E4DDD1"), 1))
        p.setBrush(QColor("#FFFFFF"))
        p.drawRect(QRectF(x, y, w, h))
        # 内页淡影
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(30, 27, 24, 10))
        p.drawRect(QRectF(x + 4, y + h - 2, w, 6))
        # 折线
        pen = QPen(QColor(theme.RED))
        pen.setStyle(Qt.DashLine)
        pen.setWidth(1)
        p.setPen(pen)
        p.drawLine(int(x + w / 2), int(y), int(x + w / 2), int(y + h))
        # 文字示意
        p.setPen(QPen(QColor("#DFD8CB"), 2))
        for side in (0, 1):
            bx = x + 20 + side * (w / 2)
            for i in range(7):
                yy = y + 28 + i * 16
                p.drawLine(int(bx), int(yy), int(bx + 58 + (i % 3) * 12), int(yy))
        p.setPen(QPen(QColor("#CFC6B6"), 1))
        p.drawRect(QRectF(x + 14, y + 14, w - 28, h - 28))
        # 裁切角标
        p.setPen(QPen(QColor("#C9C0B1"), 1))
        for cx, cy, dx, dy in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
            p.drawLine(int(cx), int(cy), int(cx + 14 * dx), int(cy))
            p.drawLine(int(cx), int(cy), int(cx), int(cy + 14 * dy))
        p.end()


class HomePage(QWidget):
    open_tool = Signal(int)

    def __init__(self, parent=None, page_index: dict | None = None):
        super().__init__(parent)
        # 首页内容装进滚动区：工具卡从 8 张变成 12 张，矮屏上也不会被裁掉
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:0;}")
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        scroll.setWidget(inner)
        shell.addWidget(scroll)

        outer = QVBoxLayout(inner)
        outer.setContentsMargins(40, 22, 40, 22)
        outer.setSpacing(0)
        self._scroll = scroll
        self._inner = inner
        self._cards = []

        # ---------- Hero ----------
        hero = QHBoxLayout()
        hero.setSpacing(20)
        left = QVBoxLayout()
        left.setSpacing(0)

        kicker = QLabel("XPLUS · BOOK TOOLKIT")
        kicker.setStyleSheet(f"color:{theme.INK3};font-size:10px;letter-spacing:3px;")
        left.addWidget(kicker)
        left.addSpacing(6)

        title = QLabel("书籍制作工具")
        title.setStyleSheet(f"font-family:'{theme.FONT_HEAD}';font-size:44px;"
                            f"letter-spacing:6px;color:{theme.INK};")
        left.addWidget(title)
        left.addSpacing(6)

        rule = QFrame()
        rule.setFixedSize(52, 3)
        rule.setStyleSheet(f"background:{theme.RED};")
        left.addWidget(rule)
        left.addSpacing(10)

        sub = QLabel("把 PDF 排成能折、能订、能裁的书——排版全程本地，文件不上传。")
        sub.setStyleSheet(f"color:{theme.INK2};font-size:13px;")
        left.addWidget(sub)
        left.addSpacing(12)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        for text in (f"{len(TOOLS)} 个工具", "A5 / A6 成书", "印刷级出血", "本地运行"):
            c = QLabel(text)
            c.setStyleSheet(f"background:#FCFAF5;border:1px solid {theme.LINE};border-radius:999px;"
                            f"color:{theme.INK2};font-size:11px;padding:4px 12px;")
            chips.addWidget(c)
        chips.addStretch(1)
        left.addLayout(chips)
        left.addStretch(1)

        hero.addLayout(left, 1)
        art = QVBoxLayout()
        art.addStretch(1)
        art.addWidget(SpreadArt(), 0, Qt.AlignRight | Qt.AlignVCenter)
        art.addStretch(1)
        hero.addLayout(art)
        outer.addLayout(hero)
        outer.addSpacing(8)

        # ---------- 工具卡 ----------
        head = QHBoxLayout()
        t = QLabel("功能")
        t.setStyleSheet(f"color:{theme.INK3};font-size:10px;letter-spacing:2px;")
        head.addWidget(t)
        head.addStretch(1)
        tip = QLabel("点卡片直接进入")
        tip.setStyleSheet(f"color:{theme.INK3};font-size:11px;")
        head.addWidget(tip)
        outer.addLayout(head)
        outer.addSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(14)
        for i, (key, name, desc) in enumerate(TOOLS):
            page = (page_index or {}).get(key, i)
            card = ToolCard(page, i, key, name, desc)
            card.clicked.connect(self.open_tool.emit)
            grid.addWidget(card, i // 4, i % 4)
            self._cards.append(card)
        outer.addLayout(grid)
        self._grid = grid

        outer.addSpacing(12)

        # ---------- 作者 ----------
        author = QFrame()
        author.setObjectName("AuthorBar")
        author.setStyleSheet(f"""
            QFrame#AuthorBar {{ background: {theme.SURFACE}; border: 1px solid {theme.LINE};
                                border-radius: 10px; }}
        """)
        al = QHBoxLayout(author)
        al.setContentsMargins(18, 9, 18, 9)
        al.setSpacing(14)

        avatar = QLabel()
        avatar.setFixedSize(42, 42)
        pm = round_pixmap(42)
        if not pm.isNull():
            avatar.setPixmap(pm)
        else:
            avatar.setText("书")
            avatar.setAlignment(Qt.AlignCenter)
            avatar.setStyleSheet(f"background:{theme.RED};color:#FBF7F0;border-radius:21px;"
                                 f"font-family:'{theme.FONT_HEAD}';font-size:22px;")
        al.addWidget(avatar)

        who = QVBoxLayout()
        who.setSpacing(1)
        name = QLabel(AUTHOR)
        name.setStyleSheet(f"font-size:14px;font-weight:600;color:{theme.INK};")
        role = QLabel("作者 · 独立开发 · 全部离线运行")
        role.setStyleSheet(f"color:{theme.INK3};font-size:11px;")
        who.addWidget(name)
        who.addWidget(role)
        al.addLayout(who)
        al.addStretch(1)

        ver = QLabel("v1.1")
        ver.setStyleSheet(f"color:{theme.INK3};font-size:11px;font-family:Consolas;")
        al.addWidget(ver)

        guide = QPushButton("使用说明")
        guide.setCursor(Qt.PointingHandCursor)
        guide.setFixedHeight(34)
        guide.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 0; color: {theme.INK2};
                           padding: 0 10px; font-size: 12px; }}
            QPushButton:hover {{ color: {theme.RED}; }}
        """)
        guide.clicked.connect(self._show_help)
        al.addWidget(guide)

        bili = QPushButton("在 B 站看作者  ↗")
        bili.setCursor(Qt.PointingHandCursor)
        bili.setFixedHeight(34)
        bili.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid {theme.LINE};
                           border-radius: 7px; color: {theme.INK}; padding: 0 16px; font-size: 12px; }}
            QPushButton:hover {{ border-color: {theme.RED}; color: {theme.RED}; }}
        """)
        bili.setToolTip(BILIBILI)
        bili.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(BILIBILI)))
        al.addWidget(bili)
        outer.addWidget(author)

        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.fit_cards)

    # ---------------- 让 12 张卡在窗口高度内自己长高/压扁 ----------------
    def resizeEvent(self, ev):                                  # noqa: N802
        super().resizeEvent(ev)
        self.fit_cards()

    def fit_cards(self) -> None:
        """卡片高度按窗口高度自适应：能放下就 178，放不下压到 132（更小就滚动）。"""
        cards = getattr(self, "_cards", None)
        if not cards:
            return
        rows = (len(cards) + 3) // 4
        spacing = self._grid.spacing()
        current = cards[0].height()
        # other = 除卡片网格以外的固定高度（标题区 + 作者条 + 外边距）
        total_hint = self._inner.sizeHint().height()
        other = total_hint - self._grid.sizeHint().height()
        avail = self._scroll.viewport().height()
        target = int((avail - other - (rows - 1) * spacing) / rows)
        target = max(132, min(178, target))
        if target == current:
            return
        for c in cards:
            c.setFixedHeight(target)
        self._inner.updateGeometry()

    def _show_help(self):
        from .help import HelpDialog
        HelpDialog(self).exec()
