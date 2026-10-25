"""一键构建：先跑回归 + 界面冒烟，全通过才打包。

用法：python build.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(title: str, script: str) -> bool:
    print(f"\n=== {title} ===")
    code = subprocess.call([PY, os.path.join(ROOT, script)], cwd=ROOT)
    if code != 0:
        print(f"❌ {title} 未通过，停止打包")
        return False
    return True


def main() -> int:
    env = dict(os.environ, PYTHONUTF8="1")
    os.environ.update(env)

    engine = os.path.join(ROOT, "assets", "print", "SumatraPDF.exe")
    if not os.path.exists(engine):
        print("❌ 缺少打印引擎：assets/print/SumatraPDF.exe")
        print("   这不是源码的一部分（GPLv3 独立程序，不进仓库），先取一次：")
        print("   python tools/fetch_print_engine.py")
        return 1

    # 转换引擎（Calibre 精简版，GPLv3 独立程序，不进仓库）
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        from fetch_convert_engine import ensure as ensure_engine
        engine_exe = ensure_engine()
    except SystemExit as exc:
        print(f"❌ 转换引擎缺失：{exc}")
        print("   先跑一次：python tools/fetch_convert_engine.py")
        return 1

    if not run("内核回归", "tests/regression.py"):
        return 1
    if not run("界面冒烟", "tests/ui_smoke.py"):
        return 1
    if not run("新页端到端", "tests/test_new_pages.py"):
        return 1

    print("\n=== 打包 ===")
    code = subprocess.call([
        PY, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--onedir", "--name", "书籍制作工具", "--icon", "assets/icon.ico",
        "--add-data", "assets;assets", "--collect-all", "pymupdf",
        "--exclude-module", "tkinter", "--exclude-module", "test", "run.py",
    ], cwd=ROOT)
    if code != 0:
        print("❌ 打包失败")
        return code

    out = os.path.join(ROOT, "dist", "书籍制作工具")

    # 把精简 Calibre 放到 exe 旁边（与 _internal 同级）：整个文件夹拷走就能用，
    # 换台没装 Calibre 的电脑也能直接转换
    dst = os.path.join(out, "Calibre")
    print(f"\n=== 内置转换引擎 → {dst} ===")
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(os.path.dirname(engine_exe), dst,
                    ignore=shutil.ignore_patterns("config", "engine.json"),
                    dirs_exist_ok=True)
    size_mb = sum(os.path.getsize(os.path.join(b, f))
                  for b, _d, fs in os.walk(dst) for f in fs) / 1048576
    print(f"   已放入 Calibre：{size_mb:.0f} MB")

    print(f"\n✅ 构建完成：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
