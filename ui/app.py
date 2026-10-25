"""主窗口：左导航 + 顶栏 + 六页 + 底部操作条。"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
import time

from PySide6.QtCore import QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QHBoxLayout, QLabel,
                               QMainWindow, QPushButton, QStackedWidget, QToolButton,
                               QVBoxLayout, QWidget)

from . import icons, theme
from .convert_page import ConvertPage
from .home import HomePage
from .pages import (BookletPage, CoverPage, FourStackPage, FourUpPage, MergePage,
                    NumberPage, SplitPage)
from .pipeline_page import PipelinePage
from .print_page import PrintPage
from .shelf_page import ShelfPage
from .split_page import SplitToolPage
from .widgets import CANCEL

APP_VERSION = "1.2.0"

#: 左侧导航 / 页面顺序（唯一真源）
#: 书架和生产是工作台入口放最前；打印必须永远是最后一个（show_print() 认 pages[-1]）。
NAV_PAGES = (
    ("shelf", "书架", "按系列管理所有书与产物", "shelf"),
    ("pipeline", "生产", "这本书的七道工序：分割 → 封面/页码 → 排版 → 打印 → 定稿", "pipeline"),
    ("booklet", "小册子", "A4 对折成 A5，骑马钉 / 胶装分册", "booklet"),
    ("cover", "封面", "封底 + 书脊 + 封面展开图，带出血与裁切线", "cover"),
    ("stack", "四堆叠", "一张 A4 排 8 页，切两刀成 4 叠", "stack"),
    ("fourup", "4合1", "4 页缩到 1 张 A4", "fourup"),
    ("merge", "合并", "多份 PDF 合成一本", "merge"),
    ("split", "分拆", "按页数 / 份数 / 页码切成多份", "split"),
    ("cut", "分割", "前 N 页析出封面素材，其余存成正文", "cut"),
    ("pager", "加页码", "给每页加页码，奇偶镜像", "pager"),
    ("convert", "转换", "MOBI / AZW3 / EPUB → PDF", "convert"),
    ("print", "打印", "选任意 PDF 直接送印", "print"),
)
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()),
                       "XPlus", "BookTool", "logs")


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(LOG_DIR, "app.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    logging.info("---- 启动 v%s ----", APP_VERSION)

    def hook(exc_type, exc, tb):
        logging.exception("未捕获异常", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("书籍制作工具")
        self.resize(1440, 900)
        self.setMinimumSize(1120, 720)
        self.setStyleSheet(theme.QSS)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # ---------------- 左导航
        rail = QWidget()
        rail.setObjectName("Rail")
        rail.setFixedWidth(88)
        rl = QVBoxLayout(rail)
        rl.setContentsMargins(0, 16, 0, 16)
        rl.setSpacing(2)
        logo = QToolButton()
        logo.setObjectName("RailLogo")
        logo.setText("书")
        logo.setToolButtonStyle(Qt.ToolButtonTextOnly)
        logo.setCursor(Qt.PointingHandCursor)
        logo.setFixedSize(44, 44)
        logo.setToolTip("回到首页")
        lw = QHBoxLayout()
        lw.setContentsMargins(0, 0, 0, 18)
        lw.addStretch(1)
        lw.addWidget(logo)
        lw.addStretch(1)
        rl.addLayout(lw)
        self.logo_btn = logo

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []
        # 12 个工具，60px 一格在 768 高的屏上会顶到底，矮屏自动压到 54
        btn_h = 60 if len(NAV_PAGES) <= 9 else 54
        for i, (_key, label, tip, icon_name) in enumerate(NAV_PAGES):
            b = QToolButton()
            b.setObjectName("NavBtn")
            b.setText(label)
            b.setCheckable(True)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIcon(icons.icon(icon_name, "#A79D8F", "#F6F1E7"))
            b.setIconSize(QSize(22, 22) if btn_h == 60 else QSize(20, 20))
            b.setFixedSize(88, btn_h)
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setToolTip(tip)
            self.nav_group.addButton(b, i)
            self.nav_buttons.append(b)
            rl.addWidget(b)
        self.nav_group.idClicked.connect(self.goto)
        rl.addStretch(1)
        h.addWidget(rail)

        # ---------------- 右侧主体
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)

        top = QWidget()
        top.setObjectName("TopBar")
        top.setFixedHeight(58)
        tl = QHBoxLayout(top)
        tl.setContentsMargins(24, 6, 24, 6)
        tl.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(0)
        self.crumb = QLabel("书籍制作工具")
        self.crumb.setObjectName("Crumb")
        self.title = QLabel("小册子打印")
        self.title.setObjectName("Title")
        left.addWidget(self.crumb)
        left.addWidget(self.title)
        tl.addLayout(left)
        tl.addStretch(1)
        self.proj = QLabel("当前文稿　—")
        self.proj.setObjectName("ProjChip")
        tl.addWidget(self.proj)
        help_btn = QPushButton("? 帮助")
        help_btn.clicked.connect(self.show_help)
        tl.addWidget(help_btn)
        about_btn = QPushButton("关于")
        about_btn.clicked.connect(self.show_about)
        tl.addWidget(about_btn)
        bl.addWidget(top)

        self.stack = QStackedWidget()
        page_factory = {
            "shelf": ShelfPage,
            "pipeline": PipelinePage,
            "booklet": BookletPage,
            "cover": CoverPage,
            "stack": FourStackPage,
            "fourup": FourUpPage,
            "merge": MergePage,
            "split": SplitPage,
            "cut": SplitToolPage,
            "pager": NumberPage,
            "convert": ConvertPage,
            "print": PrintPage,
        }
        self.pages = [page_factory[key](self) for key, *_ in NAV_PAGES]
        self.page_index = {key: i for i, (key, *_rest) in enumerate(NAV_PAGES)}
        self.home = HomePage(page_index=self.page_index)
        self.home.open_tool.connect(self.goto)
        self.stack.addWidget(self.home)
        for p in self.pages:
            self.stack.addWidget(p)
            if hasattr(p, "file"):
                p.file.picked.connect(lambda _=0, pg=p: self._on_file(pg))
        bl.addWidget(self.stack, 1)

        # 预览画布(QGraphicsView)的 viewport 会吃掉拖放：把事件转回页面/主窗口，
        # 否则把 PDF 拖到画布上"没反应"（转换页的 mobi、分割页的 PDF 都栽在这上面）
        from .dnd import forward_drops
        for _page in self.pages:
            if type(_page).__name__ in ("ConvertPage", "SplitToolPage"):
                continue                      # 这两页自己接（构造时已装）
            forward_drops(_page, self)

        # 生产线第②步直接连到「分割」页
        self.pipeline_page = self.pages[self.page_index["pipeline"]]
        self.shelf_page = self.pages[self.page_index["shelf"]]
        self.split_tool_page = self.pages[self.page_index["cut"]]
        self._pipeline_page = self.pipeline_page      # 旧插桩层用的名字，保留兼容
        self._shelf_page = self.shelf_page
        try:
            self.pipeline_page.attach_split_page(self.split_tool_page)
        except Exception:
            logging.exception("生产线与分割页连线失败")

        # ---------------- 底部操作条
        bar = QWidget()
        bar.setObjectName("ActionBar")
        bar.setFixedHeight(72)
        bl_ = QHBoxLayout(bar)
        bl_.setContentsMargins(24, 0, 24, 0)
        bl_.setSpacing(12)
        self.status_lab = QLabel("选一个 PDF 开始")
        self.status_lab.setObjectName("Status")
        bl_.addWidget(self.status_lab)
        bl_.addStretch(1)
        self.secondary = QPushButton("打开文件")
        self.secondary.setVisible(False)
        self.secondary.clicked.connect(self._open_out)
        bl_.addWidget(self.secondary)
        self.print_btn = QPushButton("打印")
        self.print_btn.setVisible(False)
        self.print_btn.clicked.connect(self.show_print)
        bl_.addWidget(self.print_btn)
        self.out_btn = QPushButton("输出：原文件夹")
        self.out_btn.setToolTip("选择结果保存到哪里")
        self.out_btn.clicked.connect(self._pick_out_dir)
        bl_.addWidget(self.out_btn)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel)
        bl_.addWidget(self.cancel_btn)
        self.primary = QPushButton("开始")
        self.primary.setObjectName("Primary")
        self.primary.setFixedHeight(40)
        self.primary.setMinimumWidth(140)
        self.primary.clicked.connect(self._run)
        bl_.addWidget(self.primary)
        bl.addWidget(bar)

        h.addWidget(body, 1)

        self.logo_btn.clicked.connect(self.show_home)
        self.show_home()
        self.setAcceptDrops(True)

        # 命令行 / 文件关联 / 拖到 exe 上的 PDF 直接打开
        targets = [a for a in sys.argv[1:]
                   if a.lower().endswith(".pdf") and os.path.exists(a)]
        if targets:
            QTimer.singleShot(250, lambda: self.set_current_doc(targets[0]))

        ico = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "assets", "icon.ico")
        if os.path.exists(ico):
            self.setWindowIcon(QIcon(ico))

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._run)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._run)

        self.settings = QSettings("XPlus", os.environ.get("BOOKTOOL_SETTINGS", "BookTool"))
        self.output_dir = str(self.settings.value("output_dir") or "")
        if self.output_dir:
            self.out_btn.setText("输出：" + (os.path.basename(self.output_dir) or self.output_dir))
        for p in self.pages:
            load = getattr(p, "load_settings", None)
            if not callable(load):
                continue
            try:
                load(self.settings)
            except Exception:
                logging.exception("读取设置失败：%s", type(p).__name__)
        geo = self.settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)
            scr = self.screen().availableGeometry()
            if self.width() > scr.width() or self.height() > scr.height():
                self.resize(min(1440, scr.width()), min(900, scr.height()))
                self.move(scr.left() + 40, scr.top() + 40)
        last = self.settings.value("page")
        if last is not None:
            try:
                last = int(last)
                if last <= 0:
                    self.show_home()
                else:
                    self.goto(last - 1)
            except Exception:
                pass

    # ---------------- 页面切换
    def goto(self, i: int):
        if not (0 <= i < len(self.pages)):
            return
        btn = self.nav_group.button(i)
        if btn and not btn.isChecked():
            btn.setChecked(True)
        self._switch(i)

    def _switch(self, i: int):
        if i < 0:
            return
        self.stack.setCurrentIndex(i + 1)
        page = self.pages[i]
        self.crumb.setText(page.crumb)
        self.title.setText(page.title)
        self.proj.setVisible(True)
        self.primary.setVisible(True)
        self.primary.setText(page.action_text)
        self.primary.setEnabled(True)
        self.secondary.setVisible(False)
        pick_hint = getattr(page, "pick_hint", "选一个 PDF 开始")
        self.set_status("就绪" if page.require_file() else pick_hint)
        page.on_show()
        self.refresh_action_state()

    def _on_file(self, page):
        path = getattr(getattr(page, "file", None), "path", "")
        if path:
            err = self._validate_pdf(path)
            if err:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "这个文件用不了", err)
                try:
                    page.file.set_path("", emit=False)
                except Exception:
                    pass
                self.set_status("换一个 PDF 试试")
                self.refresh_action_state()
                return
            self.set_current_doc(path, source=page)
        self.refresh_action_state()

    def _validate_pdf(self, path: str):
        """选文件时就拦住加密/损坏的 PDF，别等点开始才报错。"""
        import pymupdf as fitz
        from core import pdfops
        try:
            with fitz.open(path) as d:
                if d.needs_pass:
                    return "这个 PDF 设了打开密码。请先用别的软件去掉密码再导入。"
                if len(d) == 0:
                    return "这个 PDF 里没有页面。"
        except Exception as e:  # noqa: BLE001
            return pdfops.friendly_error(e, path)
        return ""

    def set_current_doc(self, path: str, source=None):
        """一份文稿在所有工具页之间共享。"""
        self._doc = path
        self.set_project(os.path.basename(path))
        for p in self.pages:
            if p is source:
                continue
            f = getattr(p, "file", None)
            if f is None or getattr(f, "path", "") == path:
                continue
            f.set_path(path, emit=False)
            try:
                p.file_loaded(path)
            except Exception:
                pass

    def refresh_action_state(self):
        idx = self.stack.currentIndex()
        if idx <= 0:
            return
        page = self.pages[idx - 1]
        if hasattr(page, "file"):
            ok = bool(getattr(page.file, "path", ""))
        elif hasattr(page, "files"):
            ok = bool(page.files)
        elif getattr(page, "always_ready", False):
            ok = True      # 书架 / 生产线：不需要输入文件，主按钮一直可点
        elif hasattr(page, "require_file"):
            # 分割 / 转换：没载入源文件时按钮灰掉
            try:
                ok = bool(page.require_file())
            except Exception:
                ok = True
        else:
            ok = True   # 封面这类不需要输入文件的页

        self.primary.setEnabled(ok)
        if not ok:
            self.primary.setText(page.action_text)
            self.status_lab.setText(getattr(page, "pick_hint", "先选一个 PDF"))
        elif self.status_lab.text() in ("先选一个 PDF", ""):
            self.status_lab.setText("就绪")

    def show_home(self):
        self.stack.setCurrentIndex(0)
        g = self.nav_group
        g.setExclusive(False)
        for b in g.buttons():
            b.setChecked(False)
        g.setExclusive(True)
        self.crumb.setText("书籍制作工具")
        self.title.setText("开始")
        self.primary.setVisible(False)
        self.secondary.setVisible(False)
        self.set_status("点卡片进入功能；点左上角「书」随时回到这里")
        self.proj.setVisible(False)

    def _run(self):
        idx = self.stack.currentIndex()
        if idx <= 0:
            return
        self.pages[idx - 1].run()

    def _open_out(self):
        idx = self.stack.currentIndex()
        if idx <= 0:
            return
        page = self.pages[idx - 1]
        path = getattr(page, "out_path", "")
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ---------------- 状态
    def set_status(self, text: str):
        self.status_lab.setObjectName("Status")
        self.status_lab.setStyleSheet("")
        self.status_lab.setText(text)

    def _pick_out_dir(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "结果保存到", os.path.expanduser("~"))
        if not d:
            self.output_dir = ""
            self.out_btn.setText("输出：原文件夹")
            return
        self.output_dir = d
        self.out_btn.setText("输出：" + os.path.basename(d) or d)
        self.settings.setValue("output_dir", d)

    def out_path_for(self, src: str, suffix: str) -> str:
        """按“输出到”设置算出结果路径，重名自动加序号。"""
        from core import pdfops
        base = os.path.splitext(os.path.basename(src))[0]
        folder = self.output_dir or os.path.dirname(src)
        os.makedirs(folder, exist_ok=True)
        return pdfops.unique_path(os.path.join(folder, base + suffix))

    def _maybe_welcome(self):
        if os.environ.get("BOOKTOOL_SETTINGS"):      # 测试/多实例不弹
            return
        if self.settings.value("seen_welcome", False):
            return
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setWindowTitle("欢迎使用 书籍制作工具")
        box.setText("三步做完一本书：")
        box.setInformativeText(
            "① 把 PDF 拖进窗口，或点左上「选择」\n"
            "② 左侧选预设 / 改页数（20 = 每册 5 张纸）\n"
            "③ 点右下红色按钮，结果存在原文件旁边\n\n"
            "全程本地运行，文件不上传。")
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()
        self.settings.setValue("seen_welcome", True)

    def _cancel(self):
        CANCEL.set()
        self.set_status("正在取消…")

    def busy(self, on: bool):
        self.primary.setEnabled(not on)
        self.cancel_btn.setVisible(on)
        if on:
            CANCEL.clear()
            self.primary.setText("处理中…")
        else:
            # 收尾时必须把按钮文字恢复，否则一直停在 “52/52 · 100%” 像卡死
            idx = max(0, self.stack.currentIndex() - 1)      # 第 0 页是首页
            page = self.pages[idx] if 0 <= idx < len(self.pages) else None
            self.primary.setText(getattr(page, "action_text", "开始"))

    def progress(self, done: int, total: int):
        pct = int(done * 100 / max(total, 1))
        self.primary.setText(f"{done}/{total} · {pct}%")
        self.status_lab.setText(f"正在处理第 {done} / {total} 步")

    def fail(self, msg: str):
        self.busy(False)
        if msg and msg != "已取消":
            from core import pdfops
            msg = pdfops.friendly_error(Exception(msg))
        idx = max(0, self.stack.currentIndex() - 1)
        page = self.pages[idx]
        self.primary.setText(page.action_text)
        self.set_status(f"已取消" if msg == "已取消" else f"出错：{msg}")
        if msg == "已取消":
            return
        logging.error("任务失败：%s", msg)
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("出错了")
        box.setText("这一步没做成：")
        box.setInformativeText(msg)
        box.setDetailedText(f"日志文件：{os.path.join(LOG_DIR, 'app.log')}")
        box.exec()

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

    def offer_open(self, path: str):
        self._last_out = path
        self.print_btn.setVisible(True)
        try:
            QApplication.alert(self, 0)     # 任务栏闪一下
        except Exception:
            pass
        idx = max(0, self.stack.currentIndex() - 1)
        page = self.pages[idx]
        page.out_path = path
        self.secondary.setVisible(True)
        self.secondary.setText("打开结果")

    def closeEvent(self, ev):
        try:
            self.settings.setValue("geometry", self.saveGeometry())
            self.settings.setValue("page", self.stack.currentIndex())
            for p in self.pages:
                save = getattr(p, "save_settings", None)
                if callable(save):
                    save(self.settings)
        except Exception:
            pass
        super().closeEvent(ev)

    def show_about(self):
        from .about import AboutDialog
        AboutDialog(self, APP_VERSION,
                    os.path.join(LOG_DIR, "app.log")).exec()

    def show_help(self):
        from .help import HelpDialog
        dlg = HelpDialog(self)
        dlg.exec()

    # ---------------- 拖放
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            for u in ev.mimeData().urls():
                if u.toLocalFile().lower().endswith(".pdf"):
                    ev.acceptProposedAction()
                    return
        super().dragEnterEvent(ev)

    def dropEvent(self, ev):
        idx = self.stack.currentIndex()
        if idx <= 0:
            return
        page = self.pages[idx - 1]
        for u in ev.mimeData().urls():
            p = u.toLocalFile()
            if not p.lower().endswith(".pdf"):
                continue
            if hasattr(page, "files") and isinstance(page.files, list):
                page.files.append(p)
                page._refresh_list()
            elif hasattr(page, "file"):
                page.file.set_path(p)
                self.proj.setText("当前文稿　" + os.path.basename(p))
        ev.acceptProposedAction()
        self.refresh_action_state()      # 拖进来之后主按钮要立刻可点

    def set_project(self, name: str):
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(self.proj.font())
        self.proj.setText("当前文稿　" + fm.elidedText(name, Qt.ElideMiddle, 260))
        self.proj.setToolTip(name)


def main():
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("书籍制作工具")
    app.setFont(QFont(theme.FONT_BODY, 9))
    w = MainWindow()
    w.show()

    # 冒烟测试：自动跑一遍小册子拼版，把结果写到文件（打包后验证用）
    sample = os.environ.get("BOOKTOOL_SAMPLE")
    if sample:
        page = w.pages[w.page_index["booklet"]]
        page.file.set_path(sample)
        QTimer.singleShot(300, page.run)

        def watch():
            if page.out_path:
                with open(os.environ["BOOKTOOL_JOB_RESULT"], "w", encoding="utf-8") as f:
                    f.write(page.out_path)
                app.quit()
            else:
                QTimer.singleShot(200, watch)

        QTimer.singleShot(600, watch)

    # 界面自检（打包后验证用）：某页载入 PDF → 点第 5 张缩略图 → 看预览有没有换
    uicheck = os.environ.get("BOOKTOOL_UI_CHECK")
    if uicheck:
        sample = os.environ.get("BOOKTOOL_UI_SAMPLE", "")
        idx = int(os.environ.get("BOOKTOOL_UI_PAGE", str(w.page_index["booklet"])))
        page = w.pages[idx]

        def run_check():
            try:
                w.goto(idx)          # 必须真的切到该页，否则预览不渲染
                page.file.set_path(sample)
                if os.environ.get("BOOKTOOL_UI_RUN"):
                    QTimer.singleShot(2000, _run_mode)
                else:
                    QTimer.singleShot(1500, click)
            except Exception as e:  # noqa: BLE001
                _write_ui(f"load-fail {e}")

        def _write_ui(text):
            with open(uicheck, "w", encoding="utf-8") as f:
                f.write(text + "\n")
            sys.exit(0)

        def _run_mode():
            t0 = time.time()
            page.run()

            def poll():
                if page.out_path:
                    return _write_ui(f"version={APP_VERSION} run={time.time() - t0:.1f}s "
                                     f"btn={w.primary.text()}")
                if time.time() - t0 > 120:
                    return _write_ui(f"version={APP_VERSION} run=TIMEOUT "
                                     f"btn={w.primary.text()}")
                QTimer.singleShot(300, poll)

            QTimer.singleShot(200, poll)

        def click():
            n = page.thumbs.list.count()
            if not n:
                return _write_ui(f"thumbs=0 caption={page.preview_caption.text()}")
            before = page.preview.item.pixmap().cacheKey() if page.preview.item else 0
            # 真的用鼠标点（不是直接发信号），才能验证信号接线
            from PySide6.QtTest import QTest
            it = page.thumbs.list.item(min(4, n - 1))
            page.thumbs.list.scrollToItem(it)
            rect = page.thumbs.list.visualItemRect(it)
            QTest.mouseClick(page.thumbs.list.viewport(), Qt.LeftButton,
                             Qt.NoModifier, rect.center())
            QTimer.singleShot(400, lambda: _write_ui(
                f"version={APP_VERSION} thumbs={n} changed="
                f"{before != (page.preview.item.pixmap().cacheKey() if page.preview.item else 0)} "
                f"caption={page.preview_caption.text()}"))

        QTimer.singleShot(400, run_check)

    # 封面预览自检（打包后验证用）：载入电子书 → 停一会儿截图 → 退出
    cover_shot = os.environ.get("BOOKTOOL_COVER_SHOT")
    if cover_shot:
        cover_src = os.environ.get("BOOKTOOL_COVER_SRC", "")
        cover_page = w.pages[w.page_index["convert"]]

        def _cover_check():
            try:
                w.goto(w.page_index["convert"])
                cover_page.set_source(cover_src)
            except Exception as exc:                      # noqa: BLE001
                print("load-fail", exc)
                sys.exit(0)
            QTimer.singleShot(3000, _cover_snap)          # 给封面线程/渲染留时间

        def _cover_snap():
            w.grab().save(cover_shot)
            sys.exit(0)

        QTimer.singleShot(500, _cover_check)

    # 格式转换自检（打包后验证用）：真跑一次转换，结果写进文件再退出
    conv_check = os.environ.get("BOOKTOOL_CONVERT_CHECK")
    if conv_check:
        conv_src = os.environ.get("BOOKTOOL_CONVERT_SRC", "")
        conv_page = w.pages[w.page_index["convert"]]

        def _write_conv(text: str):
            with open(conv_check, "w", encoding="utf-8") as f:
                f.write(text + "\n")
            sys.exit(0)

        def _start_conv():
            try:
                w.goto(w.page_index["convert"])
                conv_page.set_source(conv_src)
            except Exception as exc:                      # noqa: BLE001
                return _write_conv(f"load-fail {exc}")
            QTimer.singleShot(300, _run_conv)

        def _run_conv():
            try:
                conv_page.run()
            except Exception as exc:                      # noqa: BLE001
                return _write_conv(f"run-fail {exc}")
            QTimer.singleShot(400, _poll_conv)

        def _poll_conv():
            t0 = getattr(_poll_conv, "t0", None)
            if t0 is None:
                _poll_conv.t0 = time.time()
            if conv_page.out:
                toc = conv_page.toc.count() if hasattr(conv_page, "toc") else 0
                return _write_conv(
                    f"version={APP_VERSION} out={os.path.basename(conv_page.out)} "
                    f"exists={os.path.exists(conv_page.out)} "
                    f"size={os.path.getsize(conv_page.out) if os.path.exists(conv_page.out) else 0} "
                    f"toc={toc} status={w.status_lab.text()}")
            if time.time() - _poll_conv.t0 > 180:
                return _write_conv(f"version={APP_VERSION} TIMEOUT status={w.status_lab.text()}")
            QTimer.singleShot(400, _poll_conv)

        QTimer.singleShot(500, _start_conv)

    # 打印自检：确认随包组件找得到、打印机列表读得到
    pchk = os.environ.get("BOOKTOOL_PRINT_CHECK")
    if pchk:
        from core import printpdf
        with open(pchk, "w", encoding="utf-8") as f:
            f.write(f"sumatra={printpdf.sumatra_path()}\n")
            f.write(f"available={printpdf.available()}\n")
            f.write(f"default={printpdf.default_printer()}\n")
            f.write("printers=" + " | ".join(printpdf.printers()) + "\n")
        sys.exit(0)

    # 自检模式：截一张窗口图后退出（打包后验证用）
    if os.environ.get("BOOKTOOL_SELFTEST"):
        out = os.environ["BOOKTOOL_SELFTEST"]
        def snap():
            w.grab().save(out)
            app.quit()
        QTimer.singleShot(1200, snap)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
