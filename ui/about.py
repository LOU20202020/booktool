"""关于窗口：白底、可读、和帮助窗口同一套排版。"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QTextBrowser, QVBoxLayout)

from . import theme

ABOUT_HTML = """
<style>
  body { color:#1E1B18; font-family:"Microsoft YaHei"; font-size:13px; line-height:1.85; }
  h3 { font-family:SimSun; font-size:15px; letter-spacing:1px; margin:14px 0 4px 0; }
  p  { margin:3px 0 8px 0; color:#3A342B; }
  .k { color:#B23A2E; }
  code { background:#F4F1EA; padding:1px 4px; border-radius:3px; }
</style>
<h3>书籍制作工具</h3>
<p>把 PDF 排成能折、能订、能裁的书。全程在本机运行，文件不上传、不联网。</p>

<h3>能做什么</h3>
<p>小册子（A5 / A6）· 封面（含书脊、出血、裁切线）· 四堆叠 · 4合1 · 合并 · 分拆 · 加页码，
并可直接按双面小册子的设置送印。</p>

<h3>许可</h3>
<p>本程序以 <span class="k">AGPL-3.0</span> 发布，因为内核使用
<a href="https://github.com/pymupdf/PyMuPDF">PyMuPDF</a>（AGPL-3.0）。</p>
<p>打印引擎：SumatraPDF 3.5.2（GPL-3.0，作为独立程序被调用，未修改、未链接）。</p>

<h3>作者</h3>
<p>LOU0122 · <a href="https://space.bilibili.com/702283845">B 站主页</a></p>
"""


class AboutDialog(QDialog):
    def __init__(self, parent=None, version: str = "1.0.0", log_path: str = ""):
        super().__init__(parent)
        self.log_path = log_path
        self.setWindowTitle("关于 书籍制作工具")
        self.setMinimumSize(600, 560)
        self.setStyleSheet(f"""
            QDialog {{ background:{theme.SURFACE}; }}
            QTextBrowser {{ background:{theme.SURFACE}; border:0; color:{theme.INK}; }}
            QLabel#Ver {{ color:{theme.INK2}; font-size:12px; }}
            QPushButton#Close {{
                background:{theme.RED}; color:#FBF7F0; border:0; border-radius:7px;
                padding:8px 26px; font-size:13px; font-weight:600;
            }}
            QPushButton#Log {{
                background:#FCFAF5; border:1px solid {theme.LINE}; border-radius:7px;
                padding:8px 18px; font-size:13px; color:{theme.INK};
            }}
            QPushButton#Log:hover {{ border-color:{theme.RED}; color:{theme.RED}; }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 18)
        lay.setSpacing(10)

        head = QHBoxLayout()
        logo = QLabel("书")
        logo.setFixedSize(44, 44)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(f"background:{theme.RED}; color:#FBF7F0; border-radius:9px;"
                           f"font-family:'{theme.FONT_HEAD}'; font-size:26px;")
        head.addWidget(logo)
        title = QLabel("书籍制作工具")
        title.setStyleSheet(f"font-family:'{theme.FONT_HEAD}';font-size:22px;"
                            f"letter-spacing:2px;color:{theme.INK};")
        head.addSpacing(12)
        head.addWidget(title)
        head.addStretch(1)
        ver = QLabel(f"v{version}")
        ver.setObjectName("Ver")
        head.addWidget(ver)
        lay.addLayout(head)

        body = QTextBrowser()
        body.setHtml(ABOUT_HTML)
        body.setOpenExternalLinks(True)
        lay.addWidget(body, 1)

        row = QHBoxLayout()
        if log_path:
            log_btn = QPushButton("打开日志文件夹")
            log_btn.setObjectName("Log")
            log_btn.clicked.connect(self._open_log)
            row.addWidget(log_btn)
        row.addStretch(1)
        btn = QPushButton("知道了")
        btn.setObjectName("Close")
        btn.clicked.connect(self.accept)
        row.addWidget(btn)
        lay.addLayout(row)

    def _open_log(self):
        folder = os.path.dirname(self.log_path)
        try:
            os.makedirs(folder, exist_ok=True)
            os.startfile(folder)  # noqa: S606
        except Exception:
            pass
