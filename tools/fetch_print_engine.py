"""下载打印引擎（SumatraPDF，GPLv3）到 assets/print/。

打包前需要有它，否则「打印」按钮会提示组件缺失。
用法：python tools/fetch_print_engine.py
"""
from __future__ import annotations

import io
import os
import sys
import urllib.request
import zipfile

URL = "https://www.sumatrapdfreader.org/dl/rel/3.5.2/SumatraPDF-3.5.2-64.zip"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "print")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    target = os.path.join(OUT, "SumatraPDF.exe")
    if os.path.exists(target):
        print("已存在：", target)
        return 0
    print("下载中…", URL)
    data = urllib.request.urlopen(URL, timeout=120).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        exe = next(n for n in z.namelist() if n.lower().endswith(".exe"))
        with z.open(exe) as src, open(target, "wb") as dst:
            dst.write(src.read())
    print("已保存：", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
