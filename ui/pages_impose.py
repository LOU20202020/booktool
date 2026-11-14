"""拼版三页：小册子 / 四堆叠 / 4合1。三页共用同一套「纸张比例 + 边距提示」逻辑。"""
from __future__ import annotations

import logging
import math
import os

import pymupdf as fitz

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QGridLayout, QPushButton, QToolButton)
from core import pdfops
from . import icons, theme
from .page_base import ToolPage, margin_note, TMP
from .widgets import (CANCEL, Card, ChipGroup, FileCard, Hint, SectionLabel, Stepper, submit)


class BookletPage(ToolPage):
    title = "小册子打印"
    crumb = "书籍制作工具 / 排版"
    action_text = "开始拼版"

    def build_left(self):
        self.file = FileCard()
        self.file.picked.connect(self.file_loaded)
        self.add_card(self.file)

        self.batch_btn = QPushButton("批量：整个文件夹…")
        self.batch_btn.setToolTip("把文件夹里所有 PDF 按当前参数各拼一本")
        self.batch_btn.clicked.connect(self.run_batch)
        self.file.lay.addWidget(self.batch_btn)

        presets = Card()
        presets.lay.addWidget(SectionLabel("预设"))
        self.preset = ChipGroup(["骑马钉", "胶装分册", "自定义"])
        self.preset.changed.connect(self._on_preset)
        presets.lay.addWidget(self.preset)
        self.preset_hint = Hint("每册 20 面（5 张纸）")
        presets.lay.addWidget(self.preset_hint)
        self.add_card(presets)

        basic = Card()
        basic.lay.addWidget(SectionLabel("基本"))
        self.pages_per_sig = Stepper(20, 4, 200, 4, "面")
        self.pages_per_sig.valueChanged.connect(self._sig_changed)
        self.add_row(basic.lay, "每册页数", self.pages_per_sig)
        basic.lay.addWidget(Hint("4 的倍数；填 20 就是每册 5 张纸"))

        self.start_page = Stepper(1, 1, 9999, 1, "页")
        self.start_page.valueChanged.connect(lambda _=0: self._params_changed())
        self.add_row(basic.lay, "从第几页开始", self.start_page)
        self.start_hint = Hint("从第 1 页开始；点预览下方「看原稿」可以翻着选")
        basic.lay.addWidget(self.start_hint)
        self.binding = ChipGroup(["左边装订", "右边装订"])
        self.binding.changed.connect(lambda _=0: self._params_changed())
        basic.lay.addWidget(self.binding)

        basic.lay.addWidget(SectionLabel("成书规格"))
        self.book_size = ChipGroup(["A5（A4 对折）", "A6（对折后横切）"])
        self.book_size.changed.connect(self._size_changed)
        basic.lay.addWidget(self.book_size)
        self.size_hint = Hint("A4 一张 = 2 面 A5；对折即成一册")
        basic.lay.addWidget(self.size_hint)
        self.scale_hint = Hint("")
        self.scale_hint.setWordWrap(True)
        basic.lay.addWidget(self.scale_hint)
        self.add_card(basic)

        adv_lay = self.add_collapsible("高级设置", "缩放 · 页边距 · 起始页 · 镜像")
        self.mode = QComboBox()
        self.mode.addItems(["等比适应", "等比填满", "拉伸填满"])
        self.mode.setFixedWidth(132)
        self.mode.currentIndexChanged.connect(lambda _=0: self._params_changed())
        self.add_row(adv_lay, "页面缩放", self.mode)
        self.margin = Stepper(0, 0, 30, 0.5, "mm", 1)
        self.margin.valueChanged.connect(lambda _=0: self._params_changed())
        self.add_row(adv_lay, "页边距", self.margin)
        self.skip = Stepper(0, 0, 999, 1, "页")
        self.skip.valueChanged.connect(lambda _=0: self._params_changed())
        self.add_row(adv_lay, "跳过前几页", self.skip)
        self.mirror = QCheckBox("整体镜像（印出来左右反了才勾）")
        self.mirror.stateChanged.connect(lambda _=0: self._params_changed())
        adv_lay.addWidget(self.mirror)
        tip = Card()
        tip.lay.addWidget(SectionLabel("打印提示"))
        tip.lay.addWidget(Hint("双面打印 · 短边翻转 · 缩放 100%\n"
                               "沿中线对折，左半张往后翻，书脊在左\n"
                               "先打 1 张验：正面左 = 本册末页，右 = 第 1 页"))
        self.add_card(tip)

        self.stats_card()
        self.set_stats("—", "—", "—")
        self.stat_hint.setText("选一个 PDF 就会自动排页")

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._preview_now)

    def _on_preset(self, i):
        if getattr(self, "_lock", False):
            return
        self._lock = True
        try:
            if i == 0:
                self.pages_per_sig.set_value(20)
                self.preset_hint.setText("每册 20 面（5 张纸），骑马钉")
            elif i == 1:
                self.pages_per_sig.set_value(40)
                self.preset_hint.setText("每册 40 面（10 张纸），胶装分册")
            else:
                self.preset_hint.setText("直接在「每册页数」里填，要 4 的倍数")
                self.pages_per_sig.edit.setFocus()
                self.pages_per_sig.edit.selectAll()
        finally:
            self._lock = False
        self._params_changed()

    def _size_changed(self, _i=0):
        if self.book_size.index() == 1:
            self.size_hint.setText("A4 一张出 2 份 A6：先对折、再沿中线横切，两张各自装订")
        else:
            self.size_hint.setText("A4 一张 = 2 面 A5；对折即成一册")
        self._params_changed()

    def setting_widgets(self):
        return {"每册页数": self.pages_per_sig, "起始页": self.start_page,
                "装订": self.binding, "成书": self.book_size,
                "缩放": self.mode, "页边距": self.margin, "镜像": self.mirror}

    def _sig_changed(self, _v=0):
        if getattr(self, "_lock", False):
            return
        self._lock = True
        try:
            n = int(self.pages_per_sig.value())
            if n % 4:                      # 自动吸附到 4 的倍数
                n = max(4, int(round(n / 4.0)) * 4)
                self.pages_per_sig.set_value(n)
            if n == 20:
                self.preset.set_index(0)
                self.preset_hint.setText("每册 20 面（5 张纸），骑马钉")
            elif n == 40:
                self.preset.set_index(1)
                self.preset_hint.setText("每册 40 面（10 张纸），胶装分册")
            else:
                self.preset.set_index(2)
                self.preset_hint.setText(f"自定义：每册 {n} 面（{n // 4} 张纸）")
        finally:
            self._lock = False
        self._params_changed()

    def _params_changed(self):
        n = int(self.start_page.value())
        self.start_hint.setText(
            f"从第 {n} 页开始排版" + (f"，前 {n - 1} 页不参与" if n > 1 else "（全书）")
            + "；点预览下方「看原稿」可以翻着选")
        self._update_stats()
        self._timer.start(420)

    def _update_stats(self):
        if not self.file.path:
            return
        try:
            with fitz.open(self.file.path) as d:
                n = len(d)
        except Exception:
            return
        self._update_scale_hint(n)
        per_sig = max(1, int(self.pages_per_sig.value()) // 4)
        plan = pdfops.booklet_plan(n, per_sig, max(0, int(self.start_page.value()) - 1), 1)
        sheets = sum(len(p["sheets"]) for p in plan)
        blanks = sum(1 for p in plan for s in p["sheets"]
                     for x in s if x is None or x > p["count"])
        shown_sheets = math.ceil(sheets / 2) if self.book_size.index() == 1 else sheets
        self.set_stats(len(plan), shown_sheets, blanks)
        if plan:
            self.stat_hint.setText(
                f"每帖页数：{' / '.join(str(p['count']) for p in plan[:6])}"
                + (" …" if len(plan) > 6 else "")
                + f"　预计 {max(1, sheets * 0.02):.1f} 秒")
        else:
            self.stat_hint.setText("没有可排的页面")

    def refresh_preview(self):
        """切回本页、或文件被别人换掉时也要重画。"""
        self._preview_now()

    def _update_scale_hint(self, pages: int):
        """告诉用户原稿会被缩到多少——这是最容易印完才发现的问题。"""
        try:
            with fitz.open(self.file.path) as d:
                r = d[0].rect
                src_w, src_h = r.width, r.height
                if d[0].rotation % 180:
                    src_w, src_h = src_h, src_w
        except Exception:
            return
        target = (297.64, 419.53) if self.book_size.index() == 1 else (419.53, 595.28)
        m = self.margin.value() * 72 / 25.4 * 2
        cw, ch = target[0] - m, target[1] - m
        scale = min(cw / src_w, ch / src_h) if src_w and src_h else 1.0
        mm = lambda v: v * 25.4 / 72
        name = lambda w, h: ("A4" if abs(mm(w) - 210) < 4 and abs(mm(h) - 297) < 4 else
                             "A5" if abs(mm(w) - 148) < 4 and abs(mm(h) - 210) < 4 else
                             "A6" if abs(mm(w) - 105) < 4 and abs(mm(h) - 148) < 4 else
                             f"{mm(w):.0f}×{mm(h):.0f}mm")
        book = "A6" if self.book_size.index() == 1 else "A5"
        if scale >= 0.98:
            self.scale_hint.setText(f"原稿 {name(src_w, src_h)} → 成品 {book}：1:1，内容不缩放")
            self.scale_hint.setStyleSheet("color:#7A7365;")
        else:
            pct = round(scale * 100)
            self.scale_hint.setText(
                f"注意：原稿 {name(src_w, src_h)} → 成品 {book}，内容会缩到 {pct}%；"
                f"正文 10pt 印出来约 {10 * scale:.1f}pt。想保持原大，请按 {book} 尺寸重排原稿。")
            self.scale_hint.setStyleSheet(f"color:{theme.RED};")

    def _preview_now(self):
        if not self.is_active() or not self.file.path:
            return
        if self.btn_src.isChecked():
            return
        self.note_preview()
        self._update_stats()
        path = self.file.path
        try:
            with fitz.open(path) as d:
                n = len(d)
            if n > 600:
                # 页数太多不做整本拼版预览，但原稿缩略图照样给，点了也能翻
                self._last_preview = path
                self._last_fold = False
                self._thumb_unit = "页（原稿）"
                self.preview.show_pdf(path, 0)
                self.thumbs.load(path, limit=12, dpi=20)
                self.preview_caption.setText(
                    f"原稿第 1 页（{n} 页太多，只做原稿预览；点右侧可翻页）")
                return
            out = os.path.join(TMP, "preview_booklet.pdf")
            is_a6 = self.book_size.index() == 1
            pdfops.impose_booklet(path, out, max(1, int(self.pages_per_sig.value()) // 4),
                                  "left" if self.binding.index() == 0 else "right",
                                  self.mirror.isChecked(), ["contain", "cover", "stretch"][self.mode.currentIndex()],
                                  self.margin.value(), max(0, int(self.start_page.value()) - 1),
                                  book_size="A6" if is_a6 else "A5")
            self.preview.show_pdf(out, 0, fold=not is_a6)
            self._last_preview = out
            self._last_fold = not is_a6
            self.thumbs.load(out, limit=12, dpi=20)
            self.preview_caption.setText(
                "第 1 张纸 · 正面（上下各一份 A6，沿中线横切）" if is_a6
                else "第 1 张纸 · 正面（左侧 = 本册末页）")
        except Exception as e:
            self.status(f"预览失败：{e}")

    def file_loaded(self, path):
        try:
            with fitz.open(path) as d:
                self.enable_source_nav(len(d))
        except Exception:
            pass
        self._update_stats()
        self._timer.start(120)

    def on_use_page(self, page: int):
        self.start_page.set_value(page)

    def run(self):
        if not self.file.path:
            self.status("先选一个 PDF")
            return
        src = self.file.path
        out = self.main.out_path_for(src, "-小册子.pdf")
        args = dict(max_sheets=max(1, int(self.pages_per_sig.value()) // 4),
                    binding="left" if self.binding.index() == 0 else "right",
                    mirror=self.mirror.isChecked(),
                    mode=["contain", "cover", "stretch"][self.mode.currentIndex()],
                    margin_mm=self.margin.value(),
                    skip=max(0, int(self.start_page.value()) - 1),
                    book_size="A6" if self.book_size.index() == 1 else "A5")
        self.main.busy(True)
        self.status("正在拼版…")

        def job(cb):
            st = pdfops.impose_booklet(src, out, progress=cb, **args)
            st["path"] = out
            return st

        self._job = submit(job,
               on_progress=self.main.progress,
               on_done=lambda st: self._done(st),
               on_fail=self.main.fail)

    def _params(self) -> dict:
        return dict(max_sheets=max(1, int(self.pages_per_sig.value()) // 4),
                    binding="left" if self.binding.index() == 0 else "right",
                    mirror=self.mirror.isChecked(),
                    mode=["contain", "cover", "stretch"][self.mode.currentIndex()],
                    margin_mm=self.margin.value(),
                    skip=max(0, int(self.start_page.value()) - 1),
                    book_size="A6" if self.book_size.index() == 1 else "A5")

    def run_batch(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        folder = QFileDialog.getExistingDirectory(self, "选择放 PDF 的文件夹")
        if not folder:
            return
        pdfs = sorted(f for f in os.listdir(folder)
                      if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(folder, f)))
        if not pdfs:
            return self.status("这个文件夹里没有 PDF")
        if QMessageBox.question(self, "批量拼版",
                                f"共 {len(pdfs)} 个 PDF，按当前参数各拼一本？",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        args = self._params()
        done, failed = [], []

        def job(cb):
            for i, name in enumerate(pdfs, 1):
                if CANCEL.is_set():
                    break
                src = os.path.join(folder, name)
                out = self.main.out_path_for(src, "-小册子.pdf")
                try:
                    pdfops.impose_booklet(src, out, **args)
                    done.append(out)
                except Exception as e:  # noqa: BLE001
                    logging.getLogger(__name__).exception("批量失败：%s", name)
                    failed.append(f"{name}：{e}")
                cb(i, len(pdfs))
            return {"done": done, "failed": failed}

        self.main.busy(True)
        self.status(f"批量拼版 0/{len(pdfs)}…")
        self._batch_job = submit(job,
               on_progress=lambda d, t: self.status(f"批量拼版 {d}/{t}…"),
               on_done=self._batch_done,
               on_fail=self.main.fail)

    def _batch_done(self, res):
        self.main.busy(False)
        msg = f"完成 {len(res['done'])} 本"
        if res["failed"]:
            msg += f"，失败 {len(res['failed'])} 个"
            logging.error("批量失败：%s", "; ".join(res["failed"]))
        self.status(msg)
        self.main.set_status(msg)
        if res["done"]:
            self.main.offer_open(res["done"][0])

    def _done(self, st):
        self.main.busy(False)
        self.out_path = st["path"]
        self._last_preview = self.out_path
        self._last_fold = st.get("size") != "A6"
        self.preview.show_pdf(self.out_path, 0, fold=st.get("size") != "A6")
        self.thumbs.load(self.out_path)
        self.preview_caption.setText("第 1 张纸 · 正面")
        self.main.set_status(
            f"完成：{st['signatures']} 帖 / {st['sheets']} 张 "
            f"{'A6 双份' if st.get('size') == 'A6' else ''} / 空白 {st['blanks']} 页".replace("  /", "/")
            + margin_note(st, self.margin.value()))
        self.main.offer_open(self.out_path)


# ------------------------------------------------------------------ 封面


class FourStackPage(ToolPage):
    title = "四堆叠放"
    crumb = "书籍制作工具 / 排版"
    action_text = "开始编排"

    def build_left(self):
        self.file = FileCard()
        self.file.picked.connect(self.file_loaded)
        self.add_card(self.file)

        c = Card()
        c.lay.addWidget(SectionLabel("参数"))
        self.binding = ChipGroup(["左边装订", "右边装订"])
        self.binding.changed.connect(lambda _=0: self._changed())
        c.lay.addWidget(self.binding)
        self.mode = QComboBox()
        self.mode.addItems(["等比适应", "等比填满", "拉伸填满"])
        self.mode.setFixedWidth(132)
        self.mode.currentIndexChanged.connect(lambda _=0: self._changed())
        self.add_row(c.lay, "页面缩放", self.mode)
        self.margin = Stepper(0, 0, 30, 0.5, "mm", 1)
        self.margin.valueChanged.connect(lambda _=0: self._changed())
        self.add_row(c.lay, "页边距", self.margin)
        self.start_page = Stepper(1, 1, 9999, 1, "页")
        self.start_page.valueChanged.connect(self._start_changed)
        self.add_row(c.lay, "从第几页开始", self.start_page)
        self.start_hint = Hint("从第 1 页开始")
        c.lay.addWidget(self.start_hint)
        c.lay.addWidget(Hint("每张纸 8 页（A6 ×4）：横竖各一刀，切成 4 叠后按叠序装订"))
        self.scale_hint = Hint("")
        self.scale_hint.setWordWrap(True)
        c.lay.addWidget(self.scale_hint)
        self.add_card(c)

        self.stats_card(("张 A4", "输出面数", "空白格"))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh_preview)

    def _start_changed(self, _v=0):
        n = int(self.start_page.value())
        self.start_hint.setText(
            f"从第 {n} 页开始" + (f"，前 {n - 1} 页不参与" if n > 1 else "（全书）"))
        self._changed()

    def file_loaded(self, path):
        try:
            with fitz.open(path) as d:
                self.enable_source_nav(len(d))
                self._update_scale_hint(d[0])
        except Exception:
            pass
        self.refresh_preview()

    def _update_scale_hint(self, page):
        """A6 格子只有 A4 的一半，明说会缩多少。"""
        try:
            r = page.rect
            w, h = (r.height, r.width) if page.rotation % 180 else (r.width, r.height)
        except Exception:
            return
        m = self.margin.value() * 72 / 25.4 * 2
        cw, ch = 297.64 - m, 419.53 - m
        scale = min(cw / w, ch / h) if w and h else 1.0
        mm = lambda v: v * 25.4 / 72
        if scale >= 0.98:
            self.scale_hint.setText(f"原稿 {mm(w):.0f}×{mm(h):.0f}mm → A6 格：1:1，不缩放")
            self.scale_hint.setStyleSheet("color:#7A7365;")
        else:
            self.scale_hint.setText(
                f"注意：原稿 {mm(w):.0f}×{mm(h):.0f}mm → A6 格，内容会缩到 {round(scale*100)}%；"
                f"正文 10pt 印出来约 {10*scale:.1f}pt。")
            self.scale_hint.setStyleSheet("color:#B23A2E;")

    def on_use_page(self, page: int):
        self.start_page.set_value(page)

    def setting_widgets(self):
        return {"装订": self.binding, "缩放": self.mode, "页边距": self.margin,
                "起始页": self.start_page}

    def _changed(self):
        self._timer.start(400)

    def refresh_preview(self):
        if not self.is_active() or not self.file.path:
            return
        self.note_preview()
        if self.btn_src.isChecked():
            return
        try:
            out = os.path.join(TMP, "preview_fs.pdf")
            st = pdfops.impose_fourstack(self.file.path, out,
                                    "left" if self.binding.index() == 0 else "right",
                                    ["contain", "cover", "stretch"][self.mode.currentIndex()],
                                    self.margin.value(), skip=max(0, int(self.start_page.value()) - 1))
            self._last_preview = out
            self._last_fold = False
            self.preview.show_pdf(out, 0)
            self.thumbs.load(out, limit=12, dpi=20)
            with fitz.open(out) as d:
                n = len(d)
            self.set_stats(n // 2, n, "—")
            self.preview_caption.setText("第 1 张纸 · 正面（点右侧缩略图可切换）")
        except Exception as e:
            self.status(f"预览失败：{e}")

    def run(self):
        if not self.file.path:
            return self.status("先选一个 PDF")
        out = self.main.out_path_for(self.file.path, "-四堆叠.pdf")
        self.main.busy(True)
        self._job = submit(lambda cb: dict(pdfops.impose_fourstack(
            self.file.path, out,
            "left" if self.binding.index() == 0 else "right",
            ["contain", "cover", "stretch"][self.mode.currentIndex()],
            self.margin.value(), skip=max(0, int(self.start_page.value()) - 1),
            progress=cb), path=out),
            on_progress=self.main.progress,
            on_done=lambda st: self._done(st), on_fail=self.main.fail)

    def _done(self, st):
        self.main.busy(False)
        self.out_path = st["path"]
        self.preview.show_pdf(self.out_path, 0)
        self.thumbs.load(self.out_path)
        self.set_stats(st["sheets"], st["pages"], st["blanks"])
        self.main.set_status(f"完成：{st['sheets']} 张 / {st['pages']} 面"
                             + margin_note(st, self.margin.value()))
        self.main.offer_open(self.out_path)


# ------------------------------------------------------------------ 4合1


class FourUpPage(ToolPage):
    title = "4 合 1 拼图"
    crumb = "书籍制作工具 / 排版"
    action_text = "开始拼版"

    def build_left(self):
        self.file = FileCard()
        self.file.picked.connect(self.file_loaded)
        self.add_card(self.file)

        c = Card()
        c.lay.addWidget(SectionLabel("排列方式"))
        grid = QGridLayout()
        grid.setSpacing(8)
        self.layout_group = QButtonGroup(self)
        self.layout_group.setExclusive(True)
        for k, mode in enumerate("ABCD"):
            b = QToolButton()
            b.setObjectName("ArrBtn")
            b.setCheckable(True)
            b.setText(f"模式 {mode}")
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIcon(icons.arrangement(mode, theme.INK))
            b.setIconSize(QSize(52, 52))
            b.setFixedHeight(100)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(k == 0)
            self.layout_group.addButton(b, k)
            grid.addWidget(b, k // 2, k % 2)
        self.layout_group.idClicked.connect(lambda _=0: self._changed())
        c.lay.addLayout(grid)
        c.lay.addWidget(Hint("格子里的数字 = 这张纸上该放第几页"))
        self.start = Stepper(1, 1, 9999, 1, "页")
        self.start.valueChanged.connect(self._start_changed)
        self.add_row(c.lay, "从第几页开始", self.start)
        self.start_hint = Hint("从第 1 页开始")
        c.lay.addWidget(self.start_hint)
        self.margin = Stepper(10, 0, 30, 1, "mm")
        self.margin.valueChanged.connect(lambda _=0: self._changed())
        self.add_row(c.lay, "页边距", self.margin)
        self.add_card(c)

        self.stats_card(("张 A4", "输出面数", "空白格"))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh_preview)

    def _start_changed(self, _v=0):
        n = int(self.start.value())
        self.start_hint.setText(
            f"从第 {n} 页开始" + (f"，前 {n - 1} 页不参与" if n > 1 else "（全书）"))
        self._changed()

    def file_loaded(self, path):
        try:
            with fitz.open(path) as d:
                self.enable_source_nav(len(d))
        except Exception:
            pass
        self.refresh_preview()

    def on_use_page(self, page: int):
        self.start.set_value(page)

    def setting_widgets(self):
        return {"排法": self.layout_group, "起始页": self.start, "页边距": self.margin}

    def _changed(self):
        self._timer.start(400)

    def refresh_preview(self):
        if not self.is_active() or not self.file.path:
            return
        self.note_preview()
        if self.btn_src.isChecked():
            return
        try:
            out = os.path.join(TMP, "preview_4up.pdf")
            pdfops.impose_fourup(self.file.path, out, "ABCD"[self.layout_group.checkedId()],
                                 self.margin.value(), int(self.start.value()))
            self._last_preview = out
            self._last_fold = False
            self.preview.show_pdf(out, 0)
            self.thumbs.load(out, limit=12, dpi=20)
            with fitz.open(out) as d:
                n = len(d)
            self.set_stats(n, n, max(0, n * 4 - (len(fitz.open(self.file.path)) - int(self.start.value()) + 1)))
            self.preview_caption.setText("第 1 张 · A4（点右侧缩略图可切换）")
        except Exception as e:
            self.status(f"预览失败：{e}")

    def run(self):
        if not self.file.path:
            return self.status("先选一个 PDF")
        out = self.main.out_path_for(self.file.path, "-4合1.pdf")
        self.main.busy(True)
        self._job = submit(lambda cb: dict(pdfops.impose_fourup(
            self.file.path, out, "ABCD"[self.layout_group.checkedId()],
            self.margin.value(), int(self.start.value()), progress=cb), path=out),
            on_progress=self.main.progress,
            on_done=lambda st: self._done(st), on_fail=self.main.fail)

    def _done(self, st):
        self.main.busy(False)
        self.out_path = st["path"]
        self.preview.show_pdf(self.out_path, 0)
        self.thumbs.load(self.out_path)
        self.main.set_status(f"完成：{st['sheets']} 张 A4" + margin_note(st, self.margin.value()))
        self.main.offer_open(self.out_path)


# ------------------------------------------------------------------ 合并
