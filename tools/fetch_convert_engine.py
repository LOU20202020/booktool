"""把本机装的 Calibre 精简一份放到缓存里，供打包时塞进发行包。

用法：
    python tools/fetch_convert_engine.py            # 用默认缓存位置
    python tools/fetch_convert_engine.py --src "D:\\Calibre Portable\\Calibre"

为什么要有这一步：Calibre 是 GPLv3 的独立程序（跟 SumatraPDF 一样），
不进源码仓库；打包时从本机拿一份、去掉用不到的部分，再跟程序一起发。

精简规则（都是实测出来的，删了会直接报错，别乱加）：
  - translations/           界面翻译，命令行用不到            -41 MB
  - app/resources/localization  ← 必须留！iso639 在里面，删了起动就崩
  - onnxruntime.dll / DirectML.dll   AI 排版，转换用不到      -41 MB
  - opengl32sw.dll           软件 OpenGL 兜底                -20 MB
  - av*.dll                  音视频解码，转换用不到          -18 MB
  - d3dcompiler_47.dll       WebEngine 在用 GPU 时要         -4.6 MB
结果：670 MB → 543 MB，mobi→PDF 与 epub→PDF 都实测通过。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                     "XPlus", "BookTool", "engines", "calibre")
MANIFEST = os.path.join(CACHE, "engine.json")

SKIP_DIRS = {"translations"}
SKIP_FILES = {
    "onnxruntime.dll", "DirectML.dll", "opengl32sw.dll", "d3dcompiler_47.dll",
    "avcodec-61.dll", "avfilter-10.dll", "avformat-61.dll", "avutil-59.dll",
    "swscale-8.dll", "swresample-5.dll",
}


def find_source() -> str:
    """找一个装好的 Calibre（返回含 ebook-convert.exe 的目录）。"""
    for env in ("BOOKTOOL_CALIBRE_SRC", "ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(env, "")
        if not root:
            continue
        for sub in ("Calibre2", "Calibre", os.path.join("Programs", "Calibre2"),
                    os.path.join("Programs", "calibre")):
            cand = root if env == "BOOKTOOL_CALIBRE_SRC" else os.path.join(root, sub)
            if os.path.isfile(os.path.join(cand, "ebook-convert.exe")):
                return cand
    hit = shutil.which("ebook-convert")
    if hit:
        return os.path.dirname(hit)
    return ""


def dir_size(path: str) -> int:
    total = 0
    for base, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(base, f))
            except OSError:
                pass
    return total


def copy_trimmed(src: str, dst: str) -> None:
    def ignore(folder: str, names: list[str]) -> set[str]:
        drop = {n for n in names if n in SKIP_FILES}
        if os.path.basename(folder) == "app" and "translations" in names:
            drop.add("translations")
        return drop

    shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)


def version_of(src: str) -> str:
    exe = os.path.join(src, "ebook-convert.exe")
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
        for line in (out.stdout or out.stderr).splitlines():
            if line.strip():
                return line.strip()[:40]
    except Exception:                                    # noqa: BLE001
        pass
    return "unknown"


def ensure(src: str = "", force: bool = False) -> str:
    """保证缓存里有精简引擎，返回 ebook-convert.exe 路径。"""
    src = src or find_source()
    exe = os.path.join(CACHE, "ebook-convert.exe")
    if os.path.isfile(exe) and not force:
        return exe
    if not src or not os.path.isfile(os.path.join(src, "ebook-convert.exe")):
        raise SystemExit("找不到本机装的 Calibre：先用 winget 装一份，或用 --src 指定目录")
    print(f"从 {src} 精简复制 → {CACHE}")
    t0 = time.time()
    if os.path.isdir(CACHE):
        shutil.rmtree(CACHE, ignore_errors=True)
    copy_trimmed(src, CACHE)
    info = {
        "version": version_of(src),
        "source": src,
        "size_mb": round(dir_size(CACHE) / 1048576, 1),
        "built": time.strftime("%Y-%m-%d %H:%M"),
        "trimmed": sorted(SKIP_FILES) + ["translations/"],
    }
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(info, fh, ensure_ascii=False, indent=1)
    print(f"完成：{info['size_mb']} MB，用时 {time.time() - t0:.1f} 秒，版本 {info['version']}")
    return exe


def manifest() -> dict:
    try:
        with open(MANIFEST, encoding="utf-8") as fh:
            return json.load(fh)
    except OSError:
        return {}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    path = ensure(args.src, args.force)
    print("ebook-convert:", path)
    sys.exit(0 if os.path.isfile(path) else 1)
