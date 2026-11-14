"""测试断言小工具：四个自测脚本共用一份实现。

以前每个脚本各自抄一遍 `check()`，还抄出了两种参数顺序和两种输出格式：

- `regression.py` / `real_books.py` / `ui_smoke.py`：`check(名字, 条件, 细节)`，两列 `PASS  / FAIL`
- `test_new_pages.py`：`check(条件, 说明, 细节)`，紧凑 `✔ / ✘`

两种都保留（各自的输出已经看惯了、也贴过截图），但实现只留这一份：
失败的统计、最后的汇总行、退出码都在这里，脚本里不再各写一遍。

用法：

    import sys
    from _check import Checker

    C = Checker()
    check = C.check                     # 或者 C.check_compact
    ...
    sys.exit(C.finish("✅ 全部通过"))
"""

from __future__ import annotations


class Checker:
    """收集失败项，最后统一汇总。退出码 0 = 全过，1 = 有失败。"""

    def __init__(self) -> None:
        self.failures: list[str] = []

    # ---- 两种既有的输出格式 ----

    def check(self, name: str, cond, detail: str = "") -> bool:
        """两列格式：`PASS  名字` / `FAIL  名字   [细节]`。"""
        ok = bool(cond)
        print(("PASS  " if ok else "FAIL  ") + str(name) + ("" if ok else f"   [{detail}]"))
        if not ok:
            self.failures.append(str(name))
        return ok

    def check_compact(self, cond, what: str, extra: str = "") -> bool:
        """紧凑格式：`  ✔ 说明  细节` / `  ✘ 说明  细节`，返回条件本身。"""
        ok = bool(cond)
        print(("  ✔ " if ok else "  ✘ ") + str(what) + (f"  {extra}" if extra else ""))
        if not ok:
            self.failures.append(str(what))
        return ok

    # ---- 收尾 ----

    def finish(
        self,
        ok_message: str = "✅ 全部通过",
        fail_template: str = "❌ {n} 项失败：{names}",
        sep: str = "、",
        blank_line: bool = True,
    ) -> int:
        """打印汇总并返回退出码（0 全过 / 1 有失败）。"""
        if blank_line:
            print()
        if self.failures:
            print(fail_template.format(n=len(self.failures), names=sep.join(self.failures)))
            return 1
        print(ok_message)
        return 0
