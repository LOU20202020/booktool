"""电子书 → PDF（MOBI / AZW3 / EPUB / FB2 / TXT …）。

后端用 Calibre 的 `ebook-convert`（Linux 上是 /usr/bin/ebook-convert）：
它是这类转换的事实标准，MOBI/AZW3/KF8 都能读，章节、目录、图片都能带出来。
这里的职责只有三件：拼参数、跑子进程、把 calibre 的报错翻译成人话。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from typing import Callable, Iterable

from core.pdfops import unique_path

MM2PT = 72 / 25.4

# calibre 能读、且这个页面愿意接受的输入
SUPPORTED_EXT = (
    ".mobi", ".azw", ".azw3", ".prc", ".pdb",
    ".epub", ".kepub", ".fb2", ".fbz",
    ".lit", ".pml", ".rb", ".snb", ".tcr",
    ".txt", ".txtz", ".md",
    ".html", ".htm", ".htmlz", ".xhtml",
    ".rtf", ".docx", ".odt", ".cbz", ".cbr",
)

# 纸张：A5/A4 用 calibre 内置名字，B6（单行本）用自定义尺寸
PAPERS = {
    "A5": {"paper": "a5", "label": "A5（148×210）"},
    "A4": {"paper": "a4", "label": "A4（210×297）"},
    "B6": {"custom": (128, 182), "label": "B6 单行本（128×182）"},
}

# 页边距档位：(上, 下, 左, 右) 毫米
MARGINS = {
    "无": (0, 0, 0, 0),
    "窄": (12, 12, 14, 14),
    "中": (16, 14, 18, 18),
    "宽": (22, 20, 24, 24),
}

# 书型：文字书要页边距和页码；漫画是整页图片，边距必须为 0 才铺满
KINDS = {
    "文字书": {"margins": True, "page_numbers": True, "chapter_break": True},
    "漫画": {"margins": False, "page_numbers": False, "chapter_break": False},
}

SERIF = "SimSun"
SANS = "Microsoft YaHei"
MONO = "Consolas"


def bundle_root() -> str:
    """程序自己所在的目录：打包后是 exe 旁边，开发时是工程根目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bundled_binary() -> str:
    """随程序一起发的那份 Calibre（免安装，拷过来就能用）。"""
    root = bundle_root()
    for sub in ("Calibre", os.path.join("Calibre", "app"), "calibre"):
        exe = os.path.join(root, sub, "ebook-convert.exe")
        if os.path.isfile(exe):
            return exe
    return ""


def is_bundled(exe: str = "") -> bool:
    exe = exe or binary()
    if not exe:
        return False
    root = os.path.join(bundle_root(), "Calibre")
    try:
        return os.path.abspath(exe).lower().startswith(os.path.abspath(root).lower() + os.sep)
    except ValueError:                       # 不同盘符
        return False


def sub_env() -> dict[str, str]:
    """跑转换子进程用的环境：内置那份要把配置目录放在自己旁边，
    不然它会去写用户的 AppData，换台机器就带不走。"""
    env = os.environ.copy()
    exe = binary()
    if exe and is_bundled(exe):
        cfg = os.path.join(bundle_root(), "Calibre", "config")
        try:
            os.makedirs(cfg, exist_ok=True)
            env["CALIBRE_CONFIG_DIRECTORY"] = cfg
            env["CALIBRE_TEMP_DIR"] = os.path.join(cfg, "tmp")
            os.makedirs(env["CALIBRE_TEMP_DIR"], exist_ok=True)
        except OSError:
            pass
    return env


def engine_label() -> str:
    exe = binary()
    if not exe:
        return ""
    return ("转换引擎已就绪：内置 Calibre（不用另装）" if is_bundled(exe)
            else "转换引擎已就绪：Calibre")


def binary() -> str:
    """找 Calibre 的 ebook-convert。

    顺序：环境变量指定 → 程序自带的那份 → PATH → 常见安装目录。
    Windows 上别处的 Calibre 不在 PATH 里，装完还得重开程序，所以整条链路都探一遍。
    """
    forced = os.environ.get("BOOKTOOL_CALIBRE", "")
    if forced and os.path.isfile(forced):
        return forced
    local = bundled_binary()
    if local:
        return local
    hit = shutil.which("ebook-convert") or shutil.which("ebook-convert.exe")
    if hit:
        return hit
    roots = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
        r"D:\Program Files",
    ]
    for root in roots:
        if not root:
            continue
        for sub in ("Calibre2", "Calibre", os.path.join("Programs", "Calibre2"),
                    os.path.join("Programs", "calibre")):
            exe = os.path.join(root, sub, "ebook-convert.exe")
            if os.path.isfile(exe):
                return exe
    return ""


def available() -> bool:
    return bool(binary())


def missing_hint() -> str:
    return ("没找到 Calibre 的 ebook-convert。装一下 Calibre（calibre-ebook.com，"
            "装完重开本程序），或者把它装到默认的 Program Files\\Calibre2 下。")


def accepts(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXT


def friendly_error(err: str, path: str = "") -> str:
    """把 calibre 的 stderr 尾巴翻译成一句能看懂的话。"""
    low = (err or "").lower()
    name = os.path.basename(path) if path else "这个文件"
    if "no such file" in low:
        return f"找不到「{name}」。"
    if "bad file descriptor" in low or "is not a valid" in low or "unknown format" in low:
        return f"「{name}」读不出来：可能不是有效的电子书，或者扩展名跟内容不符。"
    if "drm" in low or "encrypted" in low or "decryption" in low:
        return f"「{name}」带 DRM 保护，转换器读不了。请先用能去掉 DRM 的工具处理。"
    if "no space left" in low:
        return "磁盘空间不够了，清理一下再试。"
    if "permission denied" in low:
        return "没有写入权限：换个输出文件夹再试。"
    if "no ebook-convert" in low or "not found" in low:
        return missing_hint()
    tail = [ln for ln in (err or "").strip().splitlines() if ln.strip()]
    return f"转换失败：{tail[-1] if tail else '未知错误'}"


def _size_kb(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def default_output(src: str) -> str:
    base = os.path.splitext(src)[0]
    return unique_path(base + ".pdf")


def build_args(
    src: str,
    out: str,
    paper: str = "A5",
    font: str = "宋体",
    font_size: float = 11,
    margin: str = "中",
    page_numbers: bool = True,
    chapter_break: bool = True,
    kind: str = "文字书",
) -> list[str]:
    args = [binary() or "ebook-convert", src, out]

    spec = PAPERS.get(paper, PAPERS["A5"])
    if "paper" in spec:
        args += ["--paper-size", spec["paper"]]
    else:
        # 自定义尺寸（B6 单行本 128×182）只能用 --custom-size，而且单位要写全名：
        # Calibre 9.x 的 --paper-size 不认 "custom"，--unit 只认 millimeter 这类全称
        w, h = spec["custom"]
        args += ["--custom-size", f"{w}x{h}", "--unit", "millimeter"]

    # 漫画是整页图片：一律零边距，否则每页四周留白、图被缩小
    comic = kind == "漫画"
    top, bottom, left, right = MARGINS["无"] if comic else MARGINS.get(margin, MARGINS["中"])
    for flag, mm in (
        ("--pdf-page-margin-top", top),
        ("--pdf-page-margin-bottom", bottom),
        ("--pdf-page-margin-left", left),
        ("--pdf-page-margin-right", right),
    ):
        args += [flag, f"{mm * MM2PT:.1f}"]

    if comic:
        # 图片页不需要字体与页码；关掉字号重算，避免图片被二次缩放
        args += ["--disable-font-rescaling"]
        return args

    if font == "黑体":
        args += ["--pdf-standard-font", "sans", "--pdf-sans-family", SANS]
    else:
        args += ["--pdf-standard-font", "serif", "--pdf-serif-family", SERIF]
    args += ["--pdf-mono-family", MONO]
    args += ["--pdf-default-font-size", str(int(font_size))]
    if page_numbers:
        args += ["--pdf-page-numbers"]
    if chapter_break:
        args += ["--chapter-mark", "pagebreak"]
    return args


def convert(
    src: str,
    out: str = "",
    paper: str = "A5",
    font: str = "宋体",
    font_size: float = 11,
    margin: str = "中",
    page_numbers: bool = True,
    chapter_break: bool = True,
    kind: str = "文字书",
    progress: Callable[[float, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict:
    """转换一个电子书文件，返回 {'out', 'pages', 'size', 'bookmarks'}。"""
    if not available():
        raise RuntimeError(missing_hint())
    if not os.path.exists(src):
        raise RuntimeError(f"找不到文件：{src}")
    if not accepts(src):
        raise RuntimeError(f"这个格式还不支持：{os.path.splitext(src)[1] or '（无扩展名）'}")

    target = out or default_output(src)
    if out:
        target = unique_path(out)
    args = build_args(
        src, target, paper, font, font_size, margin, page_numbers, chapter_break, kind
    )

    proc = subprocess.Popen(
        args,
        env=sub_env(),
        cwd=os.path.dirname(target) or None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    tail: list[str] = []
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            tail.append(line)
            del tail[:-12]
            m = re.match(r"^\s*(\d+)%", line)
            if m and progress:
                progress(int(m.group(1)) / 100.0, line.strip()[:40])
            if should_stop and should_stop():
                proc.kill()
                raise RuntimeError("已取消")
    finally:
        code = proc.wait()

    if code != 0:
        raise RuntimeError(friendly_error("\n".join(tail), src))
    if not os.path.exists(target):
        raise RuntimeError("转换器报告成功，但没有生成 PDF。")

    pages = bookmarks = 0
    try:
        import pymupdf as fitz

        with fitz.open(target) as doc:
            pages = doc.page_count
            bookmarks = len(doc.get_toc())
    except Exception:
        pass
    if progress:
        progress(1.0, "完成")
    return {
        "out": target,
        "pages": pages,
        "bookmarks": bookmarks,
        "size": os.path.getsize(target),
        "size_text": _size_kb(os.path.getsize(target)),
    }


def cover_image(path: str, out_dir: str = "") -> str:
    """把电子书的封面图取出来（Calibre 的 ebook-meta，只读元数据，很快）。

    找不到封面 / 没装 Calibre 就返回空串，界面自己决定显示什么。
    """
    exe = binary()
    if not exe or not path or not os.path.exists(path):
        return ""
    meta = os.path.join(os.path.dirname(exe), "ebook-meta.exe")
    if not os.path.exists(meta):
        meta = shutil.which("ebook-meta") or ""
    if not meta:
        return ""
    folder = out_dir or os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "XPlus", "BookTool", "convert-cover")
    os.makedirs(folder, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    safe = re.sub(r"[^0-9A-Za-z一-龥._-]+", "-", stem)[:40].strip("-") or "cover"
    out = os.path.join(folder, safe + ".jpg")
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    try:
        proc = subprocess.run([meta, path, "--get-cover", out], env=sub_env(),
                              capture_output=True, timeout=60)
    except Exception:                                    # noqa: BLE001
        return ""
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return out
    return ""


def probe(path: str) -> dict:
    """读一个转换好的 PDF，给界面填预览与目录。"""
    import pymupdf as fitz

    with fitz.open(path) as doc:
        first = doc[0].get_pixmap(dpi=110).tobytes("png") if doc.page_count else b""
        toc = doc.get_toc() or []
        return {
            "pages": doc.page_count,
            "size_mm": (round(doc[0].rect.width / MM2PT), round(doc[0].rect.height / MM2PT))
            if doc.page_count
            else (0, 0),
            "png": first,
            "toc": [(lvl, title, page) for lvl, title, page in toc],
        }
