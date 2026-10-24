"""帮助窗口：独立白底对话框，避免和暗色主题冲突。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QTextBrowser, QVBoxLayout)

from . import theme

HELP_HTML = """
<style>
  body { color:#1E1B18; font-family:"Microsoft YaHei"; font-size:13px; line-height:1.85; }
  h3 { font-family:SimSun; font-size:16px; letter-spacing:1px; margin:14px 0 6px 0; }
  p  { margin:4px 0 10px 0; color:#3A342B; }
  code { background:#F4F1EA; padding:1px 4px; border-radius:3px; }
  .k { color:#B23A2E; font-weight:600; }
</style>
<h3>做一整本书：书架 → 生产 → 分割</h3>
<p><b>书架</b>：把一个文件夹（文件夹名就是系列名）拖进书架，里面的 PDF 会按卷号自动排好。
每本书做到第几步、有哪些产物（正文 / 封面素材 / 封底素材 / 成品）、定稿是哪份，都在这里看。
做久了会堆派生文件：详情里的 <span class="k">「清理中间产物…」</span> 会先列出要删的文件和体积，
原稿、定稿、手动加入的都不动；默认还保留 <code>-正文.pdf</code>（后面拼版还要用），要删得自己取消勾选。</p>
<p><b>生产</b>：点开一本书就是七道工序的节点图 —— ①导入 → ②分割 → ③封面 → ④页码 → ⑤排版 → ⑥打印 → ⑦定稿。
绿 = 已完成，橙 = 上游改过要重跑，灰 = 还没做。点节点看这一步的说明和产物，右边「打开这一步的工具」直接跳过去。</p>
<p><b>分割</b>：前 N 页析出成<span class="k">封面素材</span>、末尾 M 页当<span class="k">封底素材</span>、其余留成
<span class="k">正文</span>，三个文件都落在原稿旁边。切好的素材可以在这一页直接送进「封面」的图槽。</p>
<p><b>转换</b>：MOBI / AZW3 / EPUB / TXT 等电子书转成 PDF，可选纸张、书型（文字书 / 漫画）、字体、字号、页边距。
转换要用免费的 Calibre，没装时这一页会直接告诉你缺什么、去哪装。</p>

<h3>三步做完一本书的小册子</h3>
<p>① 把 PDF 拖进窗口（或点「选择」）。</p>
<p>② 左侧选预设，或直接改「每册页数」（4 的倍数；20 = 每册 5 张纸）。</p>
<p>③ 点右下角「开始拼版」，结果存在原 PDF 旁边，点「打开结果」查看。</p>

<h3>打印设置</h3>
<p>双面打印 · <span class="k">短边翻转</span> · 缩放 <span class="k">100%</span>（不要选“适合页面”）。</p>
<p>沿中线对折：把左半张往后翻，书脊在左边。</p>
<p>先打 1 张验：正面左 = 本册末页、右 = 第 1 页；背面左 = 第 2 页、右 = 倒数第 2 页。</p>

<h3>几个功能怎么选</h3>
<p><b>小册子</b>：A4 横向对折成 A5，适合 4 的倍数页数、骑马钉或分册胶装。</p>
<p><b>封面</b>：<b>已有设计好的图就优先导入</b>——封面图、书脊图、封底图分开选，
再选“等比适应 / 等比填满 / 拉伸填满”。没有图就用右栏的四套版式＋五套配色现做。
含 3mm 出血与可选裁切线。</p>
<p><b>书脊厚度只认实测</b>：按页数和纸克重估出来的厚度差 1–2mm 很常见，估错就会把书脊文字压到封面/封底上，
所以这个数不再自动算——把书芯压紧量一下填进去。填 0 时书脊上不印字；量好了填上，字自动回来。</p>
<p><b>四堆叠</b>：一张 A4 排 8 页，切三刀后按堆叠装订，做 A6 小本。</p>
<p><b>4合1</b>：4 页缩到 1 张 A4，做讲义、讲义式小册子。</p>
<p><b>合并</b>：多个 PDF 按列表顺序拼成一个（列表可拖动排序）。</p>
<p><b>分拆</b>：把一份 PDF 按「每份页数」或「分成几份」切开。</p>
<p><b>分割</b>：把封面素材 / 封底素材 / 正文分开（和"分拆"不是一件事：分拆是把书切成几本，
分割是把一本拆成做封面要用的图和正文）。</p>
<p><b>加页码</b>：底部居中 / 外侧 / 顶部外侧，可设起始页、跳过封面、奇偶镜像。</p>
<p><b>打印</b>：独立一页，选任意 PDF（原稿也行）→ 选打印机/单双面/面数范围 → 打印。
左边的参数和右边的“将要打印”缩略图能对上再按“开始打印”。</p>

<h3>常见问题</h3>
<p><b>页数是奇数？</b> 会自动补空白页到 4 的倍数，最后一页空白是正常的。</p>
<p><b>打印出来反了？</b> 检查是否选了“短边翻转”；右边装订就选「右边装订」。</p>
<p><b>封面右栏太挤？</b> 封面页右上角的 <span class="k">×</span> 一键收起右栏，画布变宽；
收起时右栏里的文字会临时清空（封面只剩你导入的图），点右边缘竖排的「右侧栏」原样恢复。</p>
<p><b>结果存到哪？</b> 默认存在原 PDF 旁边；底部「输出：原文件夹」可改成别处，重名不会覆盖。</p>
<p><b>一次做好几本？</b> 小册子页点「批量：整个文件夹…」，按当前参数逐个拼。</p>
<p><b>中途想停？</b> 处理时点「取消」，已完成的文件不会删。</p>
<p><b>出错了怎么办？</b> 弹窗里有日志路径，把日志发我即可：
<code>%LOCALAPPDATA%\XPlus\BookTool\logs\app.log</code></p>

<h3>直接打印</h3>
<p>生成结果后，底部会出现 <b>「打印」</b>：点它不会弹小窗，而是<b>带着这份成品跳到「打印」页</b>，
份数、纸张等选项沿用上次，单双面按成品方向自动设好。程序会自动设好
<span class="k">双面 · 短边翻转 · A4 · 100%</span>，不用去打印机属性里改。</p>
<p>第一次建议勾着「只印 1 张样张」：正面左 = 本册末页、右 = 第 1 页，对得上再整本打。</p>
<p><b>只补印几页</b>：「打印面数」选“部分”，按<b>面</b>填（如 5-10,12）；
下方「将要打印」会把这几面逐张列出来，标着面号和正/背，打之前一眼能确认。</p>
<p><b>打原稿</b>：「打印内容」可切到“原稿（未拼版）”，把源 PDF 直接打出来。</p>
<p>注意：打印机面板里别再勾“适合页面”，否则会二次缩放。</p>
<p><b>打印会记账</b>：真送印成功后，书架的详情里会多一行「打印 N 次 · 共 X 张纸 · 最近 …」，
生产线第⑥步也随之变「完成」。只打 1 张样张也会留痕，但不算这一步做完。</p>

<h3>看预览</h3>
<p>右侧「纸张」里的缩略图<b>点一下就切换中间预览</b>，标题栏会显示“第 N 张纸”。
起始页那条「看原稿」也能翻着挑。</p>

<h3>快捷键</h3>
<p><code>Ctrl + Enter</code> 开始处理；文件可直接拖进窗口。</p>
"""


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("帮助")
        self.setMinimumSize(620, 620)
        self.setStyleSheet(f"""
            QDialog {{ background:{theme.SURFACE}; }}
            QTextBrowser {{ background:{theme.SURFACE}; border:0; color:{theme.INK}; }}
            QPushButton#CloseBtn {{
                background:{theme.RED}; color:#FBF7F0; border:0; border-radius:7px;
                padding:8px 26px; font-size:13px; font-weight:600;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 18)
        lay.setSpacing(12)

        title = QLabel("使用帮助")
        title.setStyleSheet(f"font-family:'{theme.FONT_HEAD}';font-size:20px;"
                            f"letter-spacing:2px;color:{theme.INK};")
        lay.addWidget(title)

        body = QTextBrowser()
        body.setHtml(HELP_HTML)
        body.setOpenExternalLinks(True)
        lay.addWidget(body, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        btn = QPushButton("知道了")
        btn.setObjectName("CloseBtn")
        btn.clicked.connect(self.accept)
        row.addWidget(btn)
        lay.addLayout(row)
