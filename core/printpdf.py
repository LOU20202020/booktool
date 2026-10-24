"""打印：调用随包分发的 SumatraPDF 静默打印（双面/纸张/份数都由我们指定）。

用 SumatraPDF 的原因：Windows 上要可靠地设“双面·短边翻转·100%·A4”，
必须改 DEVMODE；自己写 GDI 打印要重画每一页，容易出偏差。
SumatraPDF 是独立程序（GPLv3），我们只是调用它，不链接、不修改。
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes

CREATE_NO_WINDOW = 0x08000000


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sumatra_path() -> str:
    return os.path.join(_base_dir(), "assets", "print", "SumatraPDF.exe")


def available() -> bool:
    return os.path.exists(sumatra_path())


def printers() -> list[str]:
    """列出本机打印机（含网络打印机），不改注册表、不弹窗。"""
    winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)

    class PRINTER_INFO_4(ctypes.Structure):
        _fields_ = [("pPrinterName", wintypes.LPWSTR),
                    ("pServerName", wintypes.LPWSTR),
                    ("Attributes", wintypes.DWORD)]

    flags = 2 | 4  # PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    needed = wintypes.DWORD(0)
    returned = wintypes.DWORD(0)
    winspool.EnumPrintersW(flags, None, 4, None, 0,
                           ctypes.byref(needed), ctypes.byref(returned))
    if needed.value == 0:
        return []
    buf = ctypes.create_string_buffer(needed.value)
    ok = winspool.EnumPrintersW(flags, None, 4, buf, needed.value,
                                ctypes.byref(needed), ctypes.byref(returned))
    if not ok:
        return []
    arr = ctypes.cast(buf, ctypes.POINTER(PRINTER_INFO_4))
    names = [arr[i].pPrinterName for i in range(returned.value) if arr[i].pPrinterName]
    return sorted(set(names))


def default_printer() -> str:
    winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)
    size = wintypes.DWORD(0)
    winspool.GetDefaultPrinterW(None, ctypes.byref(size))
    if not size.value:
        return ""
    buf = ctypes.create_unicode_buffer(size.value)
    if not winspool.GetDefaultPrinterW(buf, ctypes.byref(size)):
        return ""
    return buf.value


def supports_duplex(printer: str = "") -> bool:
    """查打印机驱动是否支持自动双面。

    以前用 gdi32.DeviceCapabilities，但那函数其实在 winspool.drv 里、ctypes 取到的是
    错误符号（返回几千万的垃圾值），导致所有打印机都被判成“不支持”，于是明明能自动
    双面的机器也被要求手动翻纸。现在改成读 DEVMODE：驱动把 DM_DUPLEX 置位就支持。
    """
    import re

    name = printer or default_printer()
    if not name:
        return False
    if re.search(r"(pdf|xps|onenote|fax)", name, re.I):
        return False            # 虚拟打印机没有真正的双面

    class DEVMODEW(ctypes.Structure):
        _fields_ = [
            ("dmDeviceName", ctypes.c_wchar * 32),
            ("dmSpecVersion", wintypes.WORD),
            ("dmDriverVersion", wintypes.WORD),
            ("dmSize", wintypes.WORD),
            ("dmDriverExtra", wintypes.WORD),
            ("dmFields", wintypes.DWORD),
            ("dmOrientation", ctypes.c_short),
            ("dmPaperSize", ctypes.c_short),
            ("dmPaperLength", ctypes.c_short),
            ("dmPaperWidth", ctypes.c_short),
            ("dmScale", ctypes.c_short),
            ("dmCopies", ctypes.c_short),
            ("dmDefaultSource", ctypes.c_short),
            ("dmPrintQuality", ctypes.c_short),
            ("dmColor", ctypes.c_short),
            ("dmDuplex", ctypes.c_short),
            ("dmYResolution", ctypes.c_short),
            ("dmTTOption", ctypes.c_short),
            ("dmCollate", ctypes.c_short),
        ]

    DM_DUPLEX = 0x1000
    DM_OUT_BUFFER = 2
    spool = ctypes.WinDLL("winspool.drv", use_last_error=True)
    spool.OpenPrinterW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.HANDLE),
                                   ctypes.c_void_p]
    spool.DocumentPropertiesW.restype = ctypes.c_long
    spool.DocumentPropertiesW.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.LPCWSTR,
                                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD]
    spool.ClosePrinter.argtypes = [wintypes.HANDLE]

    h = wintypes.HANDLE()
    if not spool.OpenPrinterW(name, ctypes.byref(h), None):
        return False
    try:
        need = spool.DocumentPropertiesW(None, h, name, None, None, 0)
        if need <= 0:
            return False
        buf = ctypes.create_string_buffer(need)
        if spool.DocumentPropertiesW(None, h, name, buf, None, DM_OUT_BUFFER) < 0:
            return False
        dm = DEVMODEW.from_buffer(buf)
        return bool(dm.dmFields & DM_DUPLEX)
    except Exception:
        return False
    finally:
        try:
            spool.ClosePrinter(h)
        except Exception:
            pass


def print_pdf(path: str, printer: str = "", copies: int = 1,
              duplex: str = "short", paper: str = "A4",
              scale: str = "noscale", first_page_only: bool = False,
              subset: str = "", pages: str = "", should_stop=None) -> str:
    """送打印。duplex: short/long/none；scale: noscale/fit/shrink；

    subset: ""=全部 / "odd"=只打正页 / "even"=只打背页（手动双面用）。
    """
    exe = sumatra_path()
    if not os.path.exists(exe):
        raise RuntimeError("打印组件缺失，请重新解压整个文件夹")
    if not os.path.exists(path):
        raise RuntimeError("要打印的文件不在了，请重新生成一次")

    side = {"short": "duplexshort", "long": "duplexlong", "none": "simplex"}.get(duplex, "duplexshort")
    settings = [side, f"paper={paper}", scale]
    if copies > 1:
        settings.append(f"{copies}x")
    if pages.strip():
        settings.append(pages.strip())
    if subset in ("odd", "even"):
        settings.append(subset)
    if first_page_only:
        # 手动双面的第二遍只打背页：此时第 1 页是奇数页，会被 even 过滤成空，得指定第 2 页
        settings.append("2" if subset == "even" else "1")
    settings.append("ignore-pdf-print-settings")

    cfg = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                       "XPlus", "BookTool", "sumatra")
    os.makedirs(cfg, exist_ok=True)
    args = [exe, "-silent", "-appdata", cfg,
            "-print-to" if printer else "-print-to-default"]
    if printer:
        args.append(printer)
    args += ["-print-settings", ",".join(settings), path]

    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=CREATE_NO_WINDOW)
    import time
    deadline = time.time() + 120
    while proc.poll() is None:
        if should_stop and should_stop():
            proc.kill()
            raise RuntimeError("已取消")
        if time.time() > deadline:
            proc.kill()
            raise RuntimeError("打印机没有响应。如果选的是“Microsoft Print to PDF”这类"
                               "虚拟打印机，它可能在等一个保存对话框，换台真打印机再试。")
        time.sleep(0.15)
    out, err = proc.communicate()
    if proc.returncode != 0:
        raw = (err or out or b"").decode("utf-8", "ignore")
        lines = [l for l in raw.splitlines()
                 if l.strip() and not l.startswith("Starting SumatraPDF")
                 and "GetCommandLineW" not in l and not l.strip().startswith(exe)]
        msg = " ".join(lines).strip()
        who = printer or "系统默认打印机"
        raise RuntimeError(msg[:200] or
                           f"打印失败：{who} 没响应。确认打印机已开机、名字没选错，再试一次。")
    return printer or default_printer() or "默认打印机"
