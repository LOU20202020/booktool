"""书架的持久化：一个 shelf.json + 原子写 + .bak 回滚。

设计原则：
- 书架数据丢了不等于书丢了，所以这里从不删用户文件；
- 写入永远走 tmp → os.replace，断电不会写坏；
- 读取失败先回 .bak，再不行就从空书架起步（并记下原因给界面提示）。
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .model import Shelf


def _state_dir() -> Path:
    """Windows 上跟程序其它数据放一起：%LOCALAPPDATA%\\XPlus\\BookTool。"""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "XPlus" / "BookTool"


DEFAULT_PATH = _state_dir() / "shelf.json"


class ShelfStore:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else DEFAULT_PATH
        self.backup = self.path.with_suffix(".json.bak")
        self.recovered_from = ""      # load() 用了哪个兜底，界面可提示
        self.error = ""               # 主文件坏了的原因

    # ── 读 ──
    def load(self) -> Shelf:
        self.recovered_from, self.error = "", ""
        for candidate, tag in ((self.path, "main"), (self.backup, "bak")):
            if not candidate.exists():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                shelf = Shelf.from_dict(data)
                if tag == "bak":
                    self.recovered_from = "bak"
                return shelf
            except Exception as exc:                     # noqa: BLE001
                if tag == "main":
                    self.error = f"{type(exc).__name__}: {exc}"
                continue
        if self.error:
            self.recovered_from = "empty"
        return Shelf()

    # ── 写 ──
    def save(self, shelf: Shelf) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        payload = json.dumps(shelf.to_dict(), ensure_ascii=False, indent=1)
        tmp.write_text(payload, encoding="utf-8")
        if self.path.exists():
            try:
                shutil.copy2(self.path, self.backup)
            except OSError:
                pass
        os.replace(tmp, self.path)

    # ── 损坏恢复辅助 ──
    def quarantine(self) -> str | None:
        """把坏掉的主文件挪到 .corrupt-时间戳，返回新路径（便于用户事后捞数据）。"""
        if not self.path.exists():
            return None
        stamp = __import__("time").strftime("%Y%m%d-%H%M%S")
        dest = self.path.with_suffix(f".json.corrupt-{stamp}")
        try:
            os.replace(self.path, dest)
            return str(dest)
        except OSError:
            return None
