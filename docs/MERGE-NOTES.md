# 合并记录：Linux 分支的新工具 → Windows 主程序（v1.1.0）

> 2026-10-24。把 `书籍制作工具-linux-src-2026-10-23.zip` 里的新增功能搬回本仓库，
> 与原有的七个工具合成一个程序。原 `core/`、`ui/` 的七个工具逻辑没有改动（回归对拍通过）。

## 一、搬过来的东西

Linux 包里那层 `btlinux/`（那时是运行时插桩 + 独立目录）已经在 Windows 源码里**变成正常模块**，
不再靠 monkey-patch 挂页面：

| Linux 包里的位置 | 本仓库位置 | 说明 |
|---|---|---|
| `btlinux/shelf/{model,store,collect,thumbs}.py` | `core/shelf/` | 书架数据层：系列→卷→产物、七步状态派生、原子写 + .bak |
| `btlinux/pipeline.py` | `core/pipeline.py` | 分割：封面素材 / 封底素材 / 正文 |
| `btlinux/convert.py` | `core/convert.py` | Calibre `ebook-convert` 封装（已改 Windows 路径与字体名） |
| `btlinux/shelf_page.py` | `ui/shelf_page.py` | 书架页 |
| `btlinux/pipeline_page.py` | `ui/pipeline_page.py` | 生产线七节点图（QGraphicsView 自绘） |
| `btlinux/split_page.py` | `ui/split_page.py` | 分割页（**新增**，没有替换原来的「分拆」） |
| `btlinux/convert_page.py` | `ui/convert_page.py` | 格式转换页 |
| `btlinux/cover_link.py` | `ui/cover_link.py` | 把封面/封底素材送进封面页的三个图槽 |
| `btlinux/page_pick.py` | `ui/page_pick.py` | 从 PDF 里挑一页当图 |
| `btlinux/cover_effects.py` | `ui/cover_effects.py` | 右栏收起时清空/恢复文字 |
| `btlinux/right_rail.py` | `ui/right_rail.py` | 封面页右栏 × 收起把手 |
| `btlinux/preview_kit.py` | `ui/preview_kit.py` | 复用原程序网格画布 + 页面渲染 |
| `btlinux/ui_kit.py` | `ui/ui_kit.py` | 与原程序一致的颜色/行高/列表样式常量 |
| `btlinux/printpdf.py` | **没有搬** | Windows 版 `core/printpdf.py`（SumatraPDF + winspool）本来就在 |

## 二、改成 Windows 的地方

| 位置 | 改了什么 |
|---|---|
| `core/shelf/store.py` | 书架数据 `~/.local/state/...` → `%LOCALAPPDATA%\XPlus\BookTool\shelf.json` |
| `core/shelf/thumbs.py` | 缩略图缓存 → `%LOCALAPPDATA%\XPlus\BookTool\thumbs\` |
| `ui/page_pick.py` | 选页导出的 PNG → `%LOCALAPPDATA%\XPlus\BookTool\cover\` |
| `core/convert.py` | 找 `ebook-convert.exe`（PATH + Program Files\Calibre2 等常见位置）；字体改用 SimSun / Microsoft YaHei / Consolas；缺 Calibre 的提示改成 Windows 说法 |
| `ui/app.py` | 页面顺序改成单一真源 `NAV_PAGES`；<br>新增 argv 打开 PDF；<br>`load_settings` / `save_settings` 改成有就调；<br>状态栏"先选一个 PDF"尊重页面自己的 `pick_hint`；<br>封面页接上右栏把手与图槽省略 |
| `ui/home.py` | 工具卡 8 → 12 张，卡片下标改成"页面下标"映射（顺序变了也不会跳错页）；内容装进滚动区，卡片高度按窗口高度自适应（132–178） |
| `ui/icons.py` | 新增 4 个手绘图标：`shelf` / `pipeline` / `cut` / `convert` |

## 三、页面顺序（导航与 pages 必须一致）

```
0 书架   1 生产   2 小册子  3 封面   4 四堆叠  5 4合1
6 合并   7 分拆   8 分割    9 加页码 10 转换    11 打印
```

三条不能破的约束（原程序写法决定的）：

1. `pages` 与 `QStackedWidget` 同下标（`_switch(i)` 取 `stack[i+1]`，stack[0] 是首页）。
2. **打印页永远在最后**（`show_print()` 写死 `pages[-1]`）。
3. 导航按钮 id 必须等于 pages 下标（`nav_group.idClicked → goto`）。

## 四、故意没搬的

| 项 | 原因 |
|---|---|
| 「书脊厚度只认手填、停用按页数估算」 | 那是 Linux 那边的判断，会改掉你原有封面页的行为，先不动。要的话单独开 |
| CUPS 打印后端 | Windows 已有 SumatraPDF + winspool 的实现，且手动双面抽奇数/偶数页的逻辑在 `core/printpdf.py` 里已处理 |
| 字体替换 / PIL 字体别名 | Windows 上宋体、雅黑本来就在 |

## 五、v1.1.1：把打印记账接上（原来的空洞）

`Project.prints` 之前在模型里、界面上都有，但**没有任何代码往里写过** —— 于是打完整本，
第⑥步永远是「还没打印」，书架状态永远停在「已排版」。

现在：`core/printlog.py` 在送印成功后写一笔（时间 / 类型 / 张数 / 打印机 / 份数 / 是否样张），
`ui/app.py` 的 `start_print` 在三个出口调它（整本、手动双面完成、只打了正面）。
规矩：

| 情况 | 记什么 | 算不算第⑥步完成 |
|---|---|---|
| 整本（单面 / 双面） | `single` / `duplex` | 算 |
| 手动双面两遍都打完 | `manual-duplex`（一 条，张数按整本算） | 算 |
| 手动双面只打了正面就取消 | `odd-only` | 算（纸确实用了） |
| 只打 1 张样张 | 同类型 + `sample=True` | **不算** |

`step_state(STEP_PRINT)` 也改了：有真打印记录 → `done 已打 N 次`；排版文件（磁盘上真实的 mtime）
比最后一次打印新 → `stale 排版改过，需要重新打印`。生产线的 `on_show` 顺手重扫目录，
所以在别的页跑完排版回来，第⑤⑥步会立刻变准，不用手工点「重新扫描」。

## 五、自测（改完必须跑）

```bash
python tests/regression.py       # 内核：页序、张数、补白、封面
python tests/real_books.py       # 真实书稿四册逐页对拍
python tests/ui_smoke.py         # 界面：十二页能开、文件共享、真出文件
python tests/test_new_pages.py   # 新页：书架导入、七步状态、分割出三个文件、封面联动
python tools/shot_new_pages.py   # 出图：home/shelf/pipeline/cover/rail-off/convert
```

`python build.py` 会把前三项 + 新页端到端串起来跑，全过才打包。
