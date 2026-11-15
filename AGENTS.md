# 书籍制作工具（Book Toolkit）

Windows 上的本地 PDF 印刷拼版桌面程序（PySide6）：把 PDF 排成能折、能订、能裁的书。
**全程离线，文件不上传。** 许可证 AGPL-3.0 —— 再分发必须带源码。

## 技术栈与外部引擎

- Python 3.11+、PySide6-Essentials、PyMuPDF、Pillow；**只支持 Windows**（打印链路走 winspool + SumatraPDF）
- 两个外部程序**不进仓库**（都是 GPLv3 独立程序），各用一次性脚本取：
  - 打印引擎 → `python tools/fetch_print_engine.py`（落到 `assets/print/SumatraPDF.exe`）
  - 转换引擎 → `python tools/fetch_convert_engine.py`（Calibre 精简版）

## 命令

| 目的 | 命令 |
|---|---|
| 装依赖 | `pip install -r requirements.txt` |
| 跑起来 | `python run.py` |
| 内核回归 | `python tests/regression.py` |
| 界面冒烟 | `python tests/ui_smoke.py` |
| 新页端到端 | `python tests/test_new_pages.py` |
| 真实书稿逐像素对拍 | `python tests/real_books.py` |
| 打包（自动先跑测试） | `python build.py` |

## 完成标准（硬门槛）

改完代码必须**下面几条全绿**才算完成 —— `build.py` 卡前三条，`ruff` 与 `ui_render` 由 CI 卡：

0. `python -m ruff check .`　静态检查（规则见 `ruff.toml`：只开 E9/F/W605，不开风格）
1. `python tests/regression.py`　内核：页序、张数、补白、A6、4合1、分拆、加页码、封面尺寸
2. `python tests/ui_smoke.py`　界面：十二页能开、文件共享、真出文件
3. `python tests/test_new_pages.py`　书架导入 / 生产线状态 / 分割出三个文件 / 封面联动
4. `python tests/ui_render.py`　渲染：自绘控件真画出像素、paint 期间无异常

补充：

- 动了拼版内核（`core/pdfops.py`、`core/printplan.py`），**还要跑** `tests/real_books.py` 做逐像素对拍
- `tests/test_core.py`、`tests/test_ui.py`、`tests/test_run.py` 是临时探针，不是门禁
- **「页面能打开」不等于「画得对」**：Qt 会吞掉 `paint()` 里的异常，页面照开、测试照绿、屏幕空白。改自绘代码必须跑 `ui_render`
- 不要用"看起来对"收尾；测试没跑就别说完成

## 架构约束

- `core/` **不许** `import ui/`（当前 0 处，保持这个方向）。PDF 与数据逻辑进 `core/`，Qt 只留在 `ui/`
- PDF 运算**一律 PyMuPDF**（`import pymupdf`）。不要引入 pypdf：旧的 pypdf 实现在 206 页上要 13 秒，PyMuPDF 约 0.1 秒 —— 这个 120 倍差距是已验收结论，不是个人偏好
- `ui/page_picker.py` 里还留着 `import fitz`（PyMuPDF 的旧别名），新代码统一写 `import pymupdf`
- 公共控件放 `ui/widgets.py`（`Card` / `ChipGroup` / `Hint` / `PreviewView` / `ImagePicker`），页面里别重复造
- 耗时任务用 `QThread` 子类（见 `ui/convert_page.py::_Worker`）+ 可取消，不要阻塞 UI 线程
- 界面参数持久化走 `QSettings`（小册子页的「每册页数 / 起始页」由 `ui/app.py`、`ui/pipeline_page.py` 读写，`core/printplan.py` 靠调用方传进来）

## 版本号

两处必须同步，漏一处就会出现"安装包 1.2.3、界面显示 1.2.2"：

- `make_release.py` 的 `VER`
- `ui/app.py` 的 `APP_VERSION`

## 代码风格

- 中文注释与 docstring。模块开头写清**为什么要有这一层**和**规矩**，照 `core/printlog.py`、`core/printplan.py` 的样子 —— 这两个文件是本文档的写法范本
- 提交信息：`vX.Y.Z：<说清改后的后果>`；修 bug **写根因**，不写"修复了问题"。
  例：`封面页主按钮永远灰着：CoverPage 没有输入文件，require_file 判成 False。补 always_ready`
- 不要裸 `except:`（当前 0 处，别开这个口子）
- 函数加类型注解，文件头 `from __future__ import annotations`

## 禁区（做之前必须问）

- 不要改写 `core/printlog.py` 里那套记账规矩（只有真送印成功才记、样张不算第⑥步、手动双面合并计一次、不在书架里的 PDF 不记）
- 不要写死物理尺寸（页边距、出血、书脊厚度）。v1.2.2 修的正是"4合1 写死 3pt 边距"，填 0 就该是真的贴边
- 不要改 `build.py` 的 PyInstaller 参数（`--collect-all pymupdf`、`--add-data assets;assets`、`--exclude-module tkinter` 都是有原因的）
- 不要把 `assets/print/SumatraPDF.exe`、`Calibre/` 目录提交进仓库
- 不要 `git push`、打 tag、改 LICENSE，除非明确要求

## ui/ 文件地图（已经拆过一轮，别再往一个文件里堆）

| 文件 | 放什么 |
|---|---|
| `ui/app.py` | `MainWindow`：页面栈、状态栏、文件交接、拖放。窗口自己的事 |
| `ui/app_print.py` | 打印流程（`show_print` / `start_print` / `_pdf_page_count`），作为 `PrintFlow` mixin 挂在 `MainWindow` 上 |
| `ui/pages.py` | 30 行的汇总导出（shim），老的 `from ui.pages import BookletPage` 路径仍然有效 |
| `ui/page_base.py` | `ToolPage` 基类、`margin_note` 边距提示、`TMP` 临时目录 |
| `ui/pages_impose.py` | 拼版三页：小册子 / 四堆叠 / 4合1 |
| `ui/pages_pdf.py` | PDF 三页：合并 / 分拆 / 加页码 |
| `ui/cover_page.py` | 封面页（最长的一页，单独放） |
| `ui/pipeline_page.py` | 生产线页：工序逻辑、右侧面板、节点布局 |
| `ui/pipeline_canvas.py` | 生产线的自绘原语：`_NodeItem` / `_Canvas` / `_edge` + 几何常量 + `STATE_STYLE` |
| `ui/widgets.py` | 公共控件（`Card` / `ChipGroup` / `Hint` / `PreviewView` / `ImagePicker` / `SectionLabel`…） |
| `ui/theme.py`、`ui/ui_kit.py`、`ui/icons.py` | 配色 / 控件样式 / 图标 |

两个已经踩过的坑：

- **类名不能改**：`core/shelf/model.py` 把页面类名当 `params` 的 key 写进 `shelf.json`，`cover_link.py` 按 `type(p).__name__ == "CoverPage"` 找页面
- **别从 shim 里再导出**：`ui.pages` 曾转发 `SectionLabel`，被 ruff 的 F401 当成"没用到的导入"删掉，三个模块立刻导入失败。要转发就用 `from x import y as y`

## 体量提示

`ui/app.py`（778 行）、`ui/pipeline_page.py`（646 行）仍然偏大。
动它们时先说出打算改哪些函数，再动手；能往 `ui/widgets.py` 或新的 `ui/app_*.py` 抽的就抽。

## 给我（agent）的额外偏好

- 长篇输出先给结论；改多文件前列出要动的文件清单
- 拿不准 API 行为就去读 `core/` 里的现有实现，不要凭猜
- 涉及打印链路的改动，说清"能不能在没有真打印机的机器上验证"，不能就说不能
