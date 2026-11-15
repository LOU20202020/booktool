"""打印流程：把成品送到打印页、真送印、打印记账。

原来这四个方法是 `MainWindow` 里的一整块（170 行），夹在界面杂事中间，
改打印逻辑要在近九百行的窗口里翻。搬出来以后 `ui/app.py` 只剩窗口自己的事。

仍以 mixin 挂在 `MainWindow` 上（`class MainWindow(QMainWindow, PrintFlow)`），
方法体一字未改 —— 它们本来就靠 `self.*` 读窗口状态（状态栏、页面栈、busy、shelf）。
"""
from __future__ import annotations

import logging
import os


class PrintFlow:
    """`MainWindow` 的打印部分。单独成文件只为好找，不引入新的抽象。"""

    def show_print(self):
        """把成品带到「打印」页，选项沿用上次，不再弹小窗口。"""
        path = getattr(self, "_last_out", "")
        if not path or not os.path.exists(path):
            self.set_status("先生成一次，再打印")
            return
        from core import printpdf
        if not printpdf.available():
            return self.fail("打印组件缺失：请重新解压整个文件夹（不要只拿 exe）")
        self.goto(len(self.pages) - 1)
        page = self.pages[-1]
        page.load_target(path)
        self.set_status("已带到打印页：确认选项后点「开始打印」")

    def start_print(self, target: str, args: dict, sample: bool = False):
        """统一送印：后台线程 + 手动双面两遍。args 里可含 flip。

        送印成功后顺手把这次写进书架的打印账（core/printlog），
        生产线第⑥步和书架的「打印 N 次 / 已打印」才不是死的。
        """
        from core import printpdf
        from .widgets import CANCEL, submit
        flip_side = args.pop("flip", "short")
        manual = args.get("duplex") != "none" and not printpdf.supports_duplex(
            args.get("printer", ""))
        if manual:
            args["duplex"] = "none"

        duplex = "short" if flip_side == "short" else "long"
        printer = args.get("printer", "")
        copies = int(args.get("copies", 1) or 1)
        pages_text = str(args.get("pages", "") or "")
        total_pages = self._pdf_page_count(target)

        def log_print(tag: str, note: str = "", who: str = ""):
            """记一笔账；这份 PDF 不归书架任何一本书时就静默跳过。"""
            try:
                from core import printlog
                ev = printlog.record_print(
                    target, printer=who or printer, tag=tag, pages=total_pages,
                    copies=copies, duplex=duplex, pages_text=pages_text,
                    sample=sample, note=note)
            except Exception:                     # noqa: BLE001
                logging.getLogger(__name__).exception("打印记账失败")
                ev = None
            if ev is not None:
                for page in (getattr(self, "shelf_page", None),
                             getattr(self, "pipeline_page", None)):
                    try:
                        page.refresh()
                    except Exception:            # noqa: BLE001
                        pass
            return ev

        def call(subset=""):
            return printpdf.print_pdf(target, subset=subset,
                                      should_stop=CANCEL.is_set, **args)

        def second_done(w2):
            self.busy(False)
            self.set_status(f"手动双面完成：正面 + 背面（{w2}）")
            log_print("manual-duplex", who=w2)

        def first_done(who):
            self.busy(False)
            if not manual:
                self.set_status(f"已送到打印机：{who} · "
                                + ("1 张样张" if sample else "整本"))
                log_print("single" if duplex == "none" else "duplex", who=who)
                return
            flip = ("上下翻（沿纸的短边，像翻日历）" if flip_side == "short"
                    else "左右翻（沿纸的长边，像合书）")
            from PySide6.QtWidgets import QMessageBox
            box = QMessageBox(self)
            box.setWindowTitle("手动双面：正面已打完")
            box.setText("正面打好了，接下来打背面。")
            box.setInformativeText(
                "1. 把整叠纸原样取出，不要打乱顺序\n"
                f"2. {flip}\n"
                "3. 原样放回纸盒（方向和进纸口保持一致）\n"
                "4. 点「继续打背面」\n\n"
                "第一次建议先用「只印 1 张样张」确认没套歪。")
            box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            box.button(QMessageBox.Ok).setText("继续打背面")
            box.button(QMessageBox.Cancel).setText("先不打了")
            if box.exec() != QMessageBox.Ok:
                self.set_status("正面已打完，背面没打")
                log_print("odd-only", "只打了正面", who=who)
                return
            self.busy(True)
            self.set_status("正在打背面…")
            self._print_job = submit(lambda cb: call("even"),
                                     on_done=second_done,
                                     on_fail=self.fail)

        self.busy(True)
        self.set_status("正在送印…")
        self._print_job = submit(lambda cb: call("odd" if manual else ""),
                                 on_done=first_done,
                                 on_fail=self.fail)

    @staticmethod
    def _pdf_page_count(path: str) -> int:
        try:
            import pymupdf
            with pymupdf.open(path) as doc:
                return doc.page_count
        except Exception:                        # noqa: BLE001
            return 0
