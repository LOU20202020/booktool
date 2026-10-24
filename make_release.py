"""生成免安装发布包：dist → release/（绿色版目录）+ portable zip。

用法：python make_release.py
"""
from __future__ import annotations

import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist", "书籍制作工具")
REL = os.path.join(ROOT, "release")
PKG = os.path.join(ROOT, "packaging")
APP = "书籍制作工具"
VER = "1.1.1"

FIRST_RUN = """{app} {ver}（免安装版）

用法：
1. 把整个文件夹解压到任意位置（U 盘也行，不需要管理员权限）
2. 双击「书籍制作工具\\书籍制作工具.exe」
3. 第一次运行如果提示“Windows 已保护你的电脑” → 更多信息 → 仍要运行
   （程序没有买数字签名证书，不是病毒）
4. 想放桌面：右键 exe → 发送到 → 桌面快捷方式

注意：
· 不要把 exe 单独拖出来，_internal 文件夹是运行库，必须跟它在一起
· 删掉整个文件夹就是卸载，不写注册表、不留残留
· 全程本地运行，文件不上传

作者：LOU0122   B 站：space.bilibili.com/702283845
"""


def main() -> int:
    if not os.path.isdir(DIST):
        print("先打包：python build.py")
        return 1

    shutil.rmtree(REL, ignore_errors=True)
    os.makedirs(REL, exist_ok=True)
    shutil.copytree(DIST, os.path.join(REL, APP))

    guide = os.path.join(PKG, "使用说明.md")
    if os.path.exists(guide):
        shutil.copy(guide, os.path.join(REL, "使用说明.md"))

    with open(os.path.join(REL, "先看这里.txt"), "w", encoding="utf-8-sig") as f:
        f.write(FIRST_RUN.format(app=APP, ver=VER))

    zip_path = os.path.join(ROOT, f"{APP}-{VER}-portable-win64.zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for base, _dirs, files in os.walk(REL):
            for f in files:
                full = os.path.join(base, f)
                z.write(full, os.path.relpath(full, REL))

    size = os.path.getsize(zip_path) / 1e6
    print(f"OK 免安装包：{zip_path}（{size:.0f} MB）")
    print(f"   解开的目录：{REL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
