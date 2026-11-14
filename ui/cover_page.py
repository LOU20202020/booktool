"""封面页：封底 + 书脊 + 封面一张展开图。单独一个文件，因为它是这几个页面里最长的一页。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget)
from core import cover as cover_core
from .page_base import ToolPage
from .widgets import (Card, ChipGroup, Hint, ImagePicker, SectionLabel, Stepper)


class CoverPage(ToolPage):
    title = "封面制作"
    crumb = "书籍制作工具 / 设计"
    action_text = "生成封面"
    # 封面不靠输入文件：开本、书名、配色都是自己填的，纯文字封面也必须能生成。
    # 原来继承 ToolPage.require_file（没 file 就当没准备好），主按钮永远是灰的。
    always_ready = True

    def on_show(self):
        super().on_show()
        # 图槽会把整条文件名铺在标签上，长名字撑爆左栏 → 压成省略号
        try:
            from .cover_link import tidy_labels
            tidy_labels(self)
        except Exception:
            pass
        # 右栏一键收起（收起=连功能一起收起，封面只留图）
        try:
            from .right_rail import attach_page_right_rail
            rail = getattr(self, "_right_rail", None)
            if rail is None:
                attach_page_right_rail(self)
            else:
                rail.reposition()
        except Exception:
            pass

    # ---------------- 左栏：开本 / 图片 / 输出 ----------------
    def build_left(self):
        size = Card()
        size.lay.addWidget(SectionLabel("开本"))
        self.preset = ChipGroup(["A6 105×148", "A5 148×210"])
        self.preset.changed.connect(self._preset_changed)
        size.lay.addWidget(self.preset)
        self.w = Stepper(148, 50, 400, 1, "mm")
        self.h = Stepper(210, 50, 500, 1, "mm")
        self.spine = Stepper(12.5, 0, 80, 0.5, "mm", 1)
        # 默认尺寸是 148×210（A5），开本选中项要跟上；blockSignals 避免此时就回调
        self.preset.blockSignals(True)
        self.preset.set_index(1)
        self.preset.blockSignals(False)
        for lab, w in (("成品宽度", self.w), ("成品高度", self.h), ("书脊厚度", self.spine)):
            w.valueChanged.connect(lambda _=0: self._changed())
            self.add_row(size.lay, lab, w)
        self._spine_text_saved = ""
        self.spine.valueChanged.connect(lambda _=0: self._sync_spine_text())

        # 书脊厚度只认实测值：以前按「总页数 × 克重」估算，实际差 1–2mm 很常见，
        # 填错的后果是书脊文字压到封面/封底上。估算用的几个控件保留（配置键不变、
        # 老设置照样能读），但不再出现在界面上，也不会再改写「书脊厚度」。
        self.pages_count = Stepper(200, 0, 2000, 4, "页")
        self.paper_gsm = QComboBox()
        self.paper_gsm.addItems(list(cover_core.PAPER_THICK.keys()))
        self.paper_gsm.setCurrentIndex(1)
        self.spine_hint = Hint("")
        self.spine_note = Hint("厚度按成品量（书芯压紧后），填 0 则不印书脊文字。")
        size.lay.addWidget(self.spine_note)
        self.add_card(size)

        imgs = Card()
        imgs.lay.addWidget(SectionLabel("已设计好的图（优先）"))
        self.front_img = ImagePicker("封面图")
        self.spine_img = ImagePicker("书脊图")
        self.back_img = ImagePicker("封底图")
        for picker in (self.front_img, self.spine_img, self.back_img):
            picker.btn.clicked.connect(lambda _=0, pk=picker: self._after_pick(pk))
            imgs.lay.addWidget(picker)
        imgs.lay.addWidget(SectionLabel("图片怎么放进版面"))
        self.fit_mode = ChipGroup(["等比适应", "等比填满", "拉伸填满"])
        self.fit_mode.changed.connect(lambda _=0: self._changed())
        imgs.lay.addWidget(self.fit_mode)
        imgs.lay.addWidget(Hint("等比适应：整张图都留，边上补底色（不会裁掉内容）\n"
                                "等比填满：铺满不留边，超出部分裁掉\n"
                                "拉伸填满：硬拉到版面比例，会变形"))
        self.add_card(imgs)

        out = Card()
        out.lay.addWidget(SectionLabel("输出方式"))
        self.sheet_mode = ChipGroup(["A4 居中打印", "仅封面图（1:1）"])
        self.sheet_mode.changed.connect(lambda _=0: self._changed())
        out.lay.addWidget(self.sheet_mode)
        self.sheet_hint = Hint("A4 横向纸上居中；放不下会等比缩小，四周留 5mm 安全边距。")
        self.sheet_hint.setWordWrap(True)
        out.lay.addWidget(self.sheet_hint)

        self.bleed = Stepper(3, 0, 10, 1, "mm")
        self.bleed.valueChanged.connect(lambda _=0: self._changed())
        self.add_row(out.lay, "出血", self.bleed)
        self.dpi = QComboBox()
        self.dpi.addItems(["300 dpi", "600 dpi"])
        self.dpi.currentIndexChanged.connect(lambda _=0: self._changed())
        self.add_row(out.lay, "分辨率", self.dpi)
        self.barcode = QCheckBox("封底留条码位")
        self.barcode.setChecked(True)
        self.barcode.stateChanged.connect(lambda _=0: self._changed())
        out.lay.addWidget(self.barcode)
        self.marks = QCheckBox("裁切 / 折页辅助线")
        self.marks.setChecked(True)
        self.marks.setToolTip("四角裁切线 + 书脊两条折线，只画在出血区，成品裁掉就没了")
        self.marks.stateChanged.connect(lambda _=0: self._changed())
        out.lay.addWidget(self.marks)
        out.lay.addWidget(Hint("辅助线只画在出血区：裁切后看不见，也不会压到画面。"))
        self.add_card(out)

        self.stats_card(("展开宽", "展开高", "像素"))
        self.set_stats("—", "—", "—")

        # ---------------- 右栏：设计 ----------------
        self._build_right()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh_preview)
        self._sync_spine_text()

    def _build_right(self):
        from PySide6.QtWidgets import QLineEdit, QPlainTextEdit

        self.thumbs.setParent(None)

        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 8, 0)
        outer.setSpacing(12)
        outer.addStretch(1)

        def card(title, rows):
            c = Card()
            c.lay.addWidget(SectionLabel(title))
            for item in rows:
                if isinstance(item, tuple):
                    lab, w, *rest = item
                    line = QHBoxLayout()
                    line.setContentsMargins(0, 0, 0, 0)
                    line.setSpacing(8)
                    lb = QLabel(lab)
                    lb.setFixedWidth(72)
                    line.addWidget(lb)
                    line.addWidget(w, 1)
                    c.lay.addLayout(line)
                    if rest:
                        c.lay.addWidget(rest[0])
                else:
                    c.lay.addWidget(item)
            outer.insertWidget(outer.count() - 1, c)
            return c

        self.template = ChipGroup(["竖排文学", "教材技术", "极简留白", "满图压字"])
        self.template.changed.connect(lambda _=0: self._changed())
        self.palette = ChipGroup(list(cover_core.PALETTES.keys()))
        self.palette.changed.connect(lambda _=0: self._changed())
        card("版式", [self.template])
        card("配色", [self.palette])

        self.title_edit = QLineEdit("认 JAVA（上）")
        self.sub_edit = QLineEdit("从一行代码开始")
        self.author_edit = QLineEdit("LOU0122 著")
        self.series_edit = QLineEdit()
        self.series_edit.setPlaceholderText("系列名（可留空）")
        self.pub_edit = QLineEdit()
        self.pub_edit.setPlaceholderText("出版社 / 品牌（可留空）")
        for w in (self.title_edit, self.sub_edit, self.author_edit,
                  self.series_edit, self.pub_edit):
            w.textChanged.connect(lambda _=0: self._changed())

        self.font_box = QComboBox()
        self.font_box.addItems(["黑体", "宋体", "微软雅黑", "楷体"])
        self.font_box.currentIndexChanged.connect(lambda _=0: self._changed())
        self.title_color = "#1E1B18"
        self.color_btn = QPushButton("选颜色")
        self.color_btn.clicked.connect(self._pick_color)

        self.back_edit = QPlainTextEdit()
        self.back_edit.setPlaceholderText("封底文字（会自动换行，可留空）")
        self.back_edit.setFixedHeight(72)
        self.back_edit.textChanged.connect(lambda: self._changed())

        card("封面文字", [
            ("书名", self.title_edit),
            ("副标题", self.sub_edit),
            ("作者", self.author_edit),
            ("系列", self.series_edit),
            ("出版", self.pub_edit),
            ("字体", self.font_box),
            ("颜色", self.color_btn),
            self.back_edit,
        ])

        self.spine_edit = QLineEdit()
        self.spine_edit.setPlaceholderText("留空就用书名")
        self.spine_edit.textChanged.connect(lambda _=0: self._changed())
        self.spine_pt = Stepper(16, 6, 60, 1, "pt")
        self.spine_pt.valueChanged.connect(lambda _=0: self._changed())
        self.vertical = QCheckBox("竖排")
        self.vertical.setChecked(True)
        self.vertical.stateChanged.connect(lambda _=0: self._changed())
        card("书脊", [("文字", self.spine_edit), ("字号", self.spine_pt), self.vertical])

        tip = Card()
        tip.lay.addWidget(SectionLabel("提示"))
        tip.lay.addWidget(Hint("导入现成的封面图会盖住版式文字——图已经设计好时，"
                               "把书名等文字留空最干净。\n"
                               "图可以是图片，也可以是 PDF 的某一页。"))
        outer.insertWidget(outer.count() - 1, tip)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        scroll.setFixedWidth(340)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.layout().addWidget(scroll)

    # ---------------- 交互 ----------------
    def _after_pick(self, picker):
        self._changed()

    def setting_widgets(self):
        return {"宽": self.w, "高": self.h, "书脊": self.spine, "出血": self.bleed,
                "字号": self.spine_pt, "竖排": self.vertical, "字体": self.font_box,
                "裁切线": self.marks, "分辨率": self.dpi, "图片模式": self.fit_mode,
                "输出方式": self.sheet_mode,
                "版式": self.template, "配色": self.palette,
                "页数": self.pages_count, "纸张": self.paper_gsm, "条码": self.barcode}

    def _auto_spine(self):
        """按页数估算书脊已停用：厚度只认实测值（见 build_left 里的说明）。"""
        return

    def _sync_spine_text(self):
        """厚度为 0 时把书脊文字置成零宽空格。

        原程序在 0 宽的脊上照样排书脊文字，字会压到封面/封底上；要么填厚度，
        要么不印字，没有第三种。
        """
        if not hasattr(self, "spine_edit") or not hasattr(self, "spine_note"):
            return
        try:
            value = float(self.spine.value() or 0)
        except (TypeError, ValueError):
            value = 0.0
        current = self.spine_edit.text()
        blank = "\u200b"
        if value <= 0:
            if current.strip() and current != blank:
                self._spine_text_saved = current
            if current != blank:
                self.spine_edit.setText(blank)
            self.spine_note.setText("厚度填 0：书脊上不印字。量好实测厚度再填，字会回来。")
        else:
            if current == blank:
                self.spine_edit.setText(getattr(self, "_spine_text_saved", ""))
            self.spine_note.setText("厚度按成品量（书芯压紧后）。")
        self._limit_spine_pt(value)
        self._changed()

    def _limit_spine_pt(self, spine_mm=None) -> None:
        """字号不能大过这条脊：超了字就会压到封面/封底上。

        上限 = 书脊宽 × 0.72 换算成 pt（和 core.cover.max_spine_pt 同一套算法）。
        界面把字号步进器的上限跟着厚度走；已经超了的直接调回上限，并在提示里说明。
        """
        if not hasattr(self, "spine_pt") or not hasattr(self, "spine_note"):
            return
        try:
            mm = float(self.spine.value() if spine_mm is None else spine_mm)
        except (TypeError, ValueError):
            mm = 0.0
        if mm <= 0:
            self.spine_pt.set_range(6, 60)
            return
        limit = max(6, int(cover_core.max_spine_pt(mm)))
        self.spine_pt.set_range(6, limit)
        clamped = float(self.spine_pt.value()) > limit
        if clamped:
            self.spine_pt.set_value(limit)
        note = f"厚度按成品量（书芯压紧后）；{mm:g}mm 的书脊，字号最多 {limit}pt。"
        if clamped:
            note = f"字号超出书脊宽度，已调到 {limit}pt（{mm:g}mm 的脊最多这么多）。"
        self.spine_note.setText(note)

    def load_settings(self, s):
        super().load_settings(s)
        try:
            # 升级一次性迁移：老版本那个厚度是按页数估出来的，统一换成常用实测值 12.5mm
            if not s.value("ui/spine_default_v2"):
                s.setValue("tool/CoverPage/书脊", 12.5)
                s.setValue("ui/spine_default_v2", 1)
                s.setValue("ui/spine_manual", 1)
                s.sync()
                self.spine.set_value(12.5)
        except Exception:
            pass
        self._sync_spine_text()
        self._sync_preset_chip()

    def _sync_preset_chip(self) -> None:
        """开本选中项跟着实际宽高走（宽高是存过的，开本不存，容易和数字不一致）。"""
        if not hasattr(self, "preset"):
            return
        try:
            w, h = int(self.w.value()), int(self.h.value())
        except (TypeError, ValueError):
            return
        if (w, h) == (105, 148):
            idx = 0
        elif (w, h) == (148, 210):
            idx = 1
        else:
            return
        self.preset.blockSignals(True)
        self.preset.set_index(idx)
        self.preset.blockSignals(False)

    def _pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(self.title_color), self, "书名颜色")
        if c.isValid():
            self.title_color = c.name()
            self.color_btn.setStyleSheet(
                f"text-align:left; padding-left:10px; border-left:4px solid {self.title_color};")
            self._changed()

    def _preset_changed(self, i):
        w, h = [(105, 148), (148, 210)][i]
        self.w.set_value(w)
        self.h.set_value(h)
        self._changed()

    def _changed(self):
        if hasattr(self, "_timer"):
            self._timer.start(280)

    # ---------------- 渲染 ----------------
    def _render(self, dpi):
        return cover_core.render_cover(
            self.w.value(), self.h.value(), self.spine.value(), self.bleed.value(),
            dpi=dpi,
            title=self.title_edit.text().strip() or ("" if self.front_img.path else "书名"),
            subtitle=self.sub_edit.text(), author=self.author_edit.text(),
            spine_pt=self.spine_pt.value(), vertical=self.vertical.isChecked(),
            spine_text=self.spine_edit.text().strip() or None,
            front_img=self.front_img.path or None,
            back_img=self.back_img.path or None,
            spine_img=self.spine_img.path or None,
            title_font=self.font_box.currentText(),
            template=["classic", "modern", "minimal", "image"][self.template.index()],
            palette=list(cover_core.PALETTES.keys())[self.palette.index()],
            publisher=self.pub_edit.text().strip(),
            series=self.series_edit.text().strip(),
            barcode=self.barcode.isChecked(),
            title_color=self.title_color,
            back_text=self.back_edit.toPlainText(),
            crop_marks=self.marks.isChecked(),
            fit=["contain", "cover", "stretch"][self.fit_mode.index()],
            sheet="a4" if self.sheet_mode.index() == 0 else "cover",
        )

    def refresh_preview(self):
        if not self.is_active():
            return
        self.note_preview()
        try:
            img = self._render(150)
        except Exception as e:
            self.status(f"预览失败：{e}")
            return
        q = QImage(img.tobytes("raw", "RGB"), img.width, img.height,
                   img.width * 3, QImage.Format_RGB888).copy()
        self.preview.set_image(QPixmap.fromImage(q))
        bw = self.w.value() * 2 + self.spine.value() + self.bleed.value() * 2
        bh = self.h.value() + self.bleed.value() * 2
        dpi = 300 if self.dpi.currentIndex() == 0 else 600
        self.set_stats(f"{bw:.0f}", f"{bh:.0f}", f"{int(bw/25.4*dpi)}×{int(bh/25.4*dpi)}")
        if self.sheet_mode.index() == 0:
            bw = self.w.value() * 2 + self.spine.value() + self.bleed.value() * 2
            bh = self.h.value() + self.bleed.value() * 2
            sc = min(1.0, (297 - 10) / bw, (210 - 10) / bh)
            note = "" if sc > 0.995 else f" · 缩到 {sc*100:.0f}%"
            self.preview_caption.setText(f"A4 居中{note} · 实线为裁切/折页线")
            self.sheet_hint.setText(
                "A4 横向纸上居中。" if sc > 0.995 else
                f"封面比 A4 大，已等比缩到 {sc*100:.0f}% 才能整张打出来；"
                "要 1:1 请改选「仅封面图」。")
        else:
            self.preview_caption.setText("展开图：封底 | 书脊 | 封面（含出血）")
            self.sheet_hint.setText("1:1 输出展开图，尺寸就是上面算的成品尺寸加出血。")
        self.main.set_status(f"封面尺寸：{bw:.0f} × {bh:.0f} mm")

    def run(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存封面", "封面.pdf", "PDF (*.pdf)")
        if not path:
            return
        try:
            dpi = 300 if self.dpi.currentIndex() == 0 else 600
            cover_core.save_pdf(self._render(dpi), path, dpi=dpi)
            self.out_path = path
            self.main.set_status(f"已生成：{path}")
            self.main.offer_open(path)
        except Exception as e:
            self.main.fail(str(e))


# ------------------------------------------------------------------ 四堆叠放
