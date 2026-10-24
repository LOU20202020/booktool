"""PDF 选页对话框：把所有页缩略图摊开，点一张当封面用。"""
from __future__ import annotations

import fitz
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout)

from . import theme


class PagePickerDialog(QDialog):
    def __init__(self, pdf_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选一页作为图片")
        self.resize(880, 640)
        self.page = 0
        self.setStyleSheet(f"""
            QDialog {{ background: {theme.SURFACE}; }}
            QListWidget {{ background: #FCFAF5; border: 1px solid {theme.LINE}; border-radius: 8px; }}
            QListWidget::item {{ border-radius: 4px; padding: 4px; }}
            QListWidget::item:selected {{ background: {theme.RED_SOFT}; color: {theme.INK}; }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)

        name = pdf_path.replace("\\", "/").split("/")[-1]
        head = QLabel(f"{name} · 点一张，再按「用这一页」")
        head.setStyleSheet(f"color:{theme.INK2};font-size:12px;")
        lay.addWidget(head)

        from PySide6.QtWidgets import QSpinBox
        with fitz.open(pdf_path) as _d:
            _n = len(_d)
        jump = QHBoxLayout()
        jump.setSpacing(6)
        lab = QLabel(f"共 {_n} 页，跳到第")
        lab.setStyleSheet(f"color:{theme.INK3};font-size:11px;")
        self.jump = QSpinBox()
        self.jump.setRange(1, max(1, _n))
        self.jump.setFixedWidth(80)
        lab2 = QLabel("页")
        lab2.setStyleSheet(f"color:{theme.INK3};font-size:11px;")
        jump.addWidget(lab)
        jump.addWidget(self.jump)
        jump.addWidget(lab2)
        jump.addStretch(1)
        lay.addLayout(jump)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setIconSize(QSize(104, 148))
        self.list.setSpacing(6)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        lay.addWidget(self.list, 1)

        with fitz.open(pdf_path) as doc:
            n = len(doc)
            for i in range(n):
                pix = doc[i].get_pixmap(matrix=fitz.Matrix(0.28, 0.28))
                img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                             QImage.Format_RGB888).copy()
                it = QListWidgetItem(QPixmap.fromImage(img), str(i + 1))
                it.setData(Qt.UserRole, i)
                self.list.addItem(it)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("用这一页")
        ok.setObjectName("Primary")
        ok.setFixedHeight(34)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

        self.list.currentRowChanged.connect(self._row_changed)
        self.list.itemDoubleClicked.connect(lambda _it: self.accept())
        self.jump.valueChanged.connect(lambda v: self.list.setCurrentRow(v - 1))
        self.list.setCurrentRow(0)

    def _row_changed(self, i):
        self.page = max(0, i)
        if self.jump.value() != i + 1:
            self.jump.blockSignals(True)
            self.jump.setValue(i + 1)
            self.jump.blockSignals(False)
