"""书架数据模型：系列 → 卷（Project）→ 条目（Item）。

这一层只做两件事：
1. 存"这本书现在有什么"（路径、页数、体积、参数指纹）；
2. 派生"走到第几步、哪一步过期了"。

不碰 Qt，不读 PDF 内容（页数由调用方填），所以可以离线单元测试。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime

# ── 产物类型 ────────────────────────────────────────────────────────────────
KIND_COVER_SRC = "cover_src"     # -封面素材.pdf
KIND_BODY = "body"               # -正文.pdf
KIND_COVER_BACK = "back_cover"   # -封底素材.pdf
KIND_COVER = "cover"             # -成品封面.pdf / 封面.pdf
KIND_PAGED = "paged"             # -加页码.pdf
KIND_BOOKLET = "booklet"         # -小册子.pdf
KIND_FOURSTACK = "fourstack"     # -四堆叠.pdf
KIND_FOURUP = "fourup"           # -4合1.pdf
KIND_A4A4 = "a4a4"               # -A4拼版.pdf
KIND_DUP = "dup"                 # -2/-3 这种重复副本
KIND_OTHER = "other"             # 同前缀但认不出

LAYOUT_KINDS = (KIND_BOOKLET, KIND_FOURSTACK, KIND_FOURUP, KIND_A4A4)

KIND_LABELS = {
    KIND_COVER_SRC: "封面素材",
    KIND_COVER_BACK: "封底素材",
    KIND_BODY: "正文",
    KIND_COVER: "成品封面",
    KIND_PAGED: "加页码",
    KIND_BOOKLET: "小册子",
    KIND_FOURSTACK: "四堆叠",
    KIND_FOURUP: "4合1",
    KIND_A4A4: "A4拼版",
    KIND_DUP: "副本",
    KIND_OTHER: "其它",
}

# 每一种排版产物对应的工具参数键（用于过期判断/参数回填）
KIND_TOOL = {
    KIND_COVER: "CoverPage",
    KIND_PAGED: "NumberPage",
    KIND_BOOKLET: "BookletPage",
    KIND_FOURSTACK: "FourStackPage",
    KIND_FOURUP: "FourUpPage",
    KIND_A4A4: "A5A4Page",
}

# ── 七步 ────────────────────────────────────────────────────────────────────
STEP_IMPORT, STEP_SPLIT, STEP_COVER, STEP_PAGER, STEP_LAYOUT, STEP_PRINT, STEP_FINAL = range(1, 8)
STEPS = (STEP_IMPORT, STEP_SPLIT, STEP_COVER, STEP_PAGER, STEP_LAYOUT, STEP_PRINT, STEP_FINAL)
STEP_NAMES = {
    STEP_IMPORT: "导入",
    STEP_SPLIT: "分割",
    STEP_COVER: "封面",
    STEP_PAGER: "页码",
    STEP_LAYOUT: "排版",
    STEP_PRINT: "打印",
    STEP_FINAL: "装订/定稿",
}

# ── 节点状态 ────────────────────────────────────────────────────────────────
ST_DONE, ST_TODO, ST_STALE, ST_SKIP, ST_BLOCKED, ST_FAILED = (
    "done", "todo", "stale", "skip", "blocked", "failed",
)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def iso_ts(text: str) -> float:
    """把 now_iso() 写的字符串换回时间戳；认不出来就当 0（最旧）。"""
    try:
        return datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError):
        return 0.0


def params_hash(params: dict | None) -> str:
    """参数指纹：只用来判断"跑完之后有没有被改过"。"""
    if not params:
        return ""
    blob = json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


@dataclass
class Source:
    """一个输入文件（原稿或附加素材）。"""

    path: str
    size: int = 0
    mtime: float = 0.0
    pages: int | None = None
    fp: str | None = None          # 首页指纹，用于文件被改名/搬走后认回
    role: str = "primary"          # primary | extra

    @classmethod
    def of(cls, path: str, role: str = "primary") -> "Source":
        src = cls(path=os.path.abspath(path), role=role)
        src.refresh()
        return src

    def refresh(self) -> None:
        try:
            st = os.stat(self.path)
            self.size, self.mtime = st.st_size, st.st_mtime
        except OSError:
            self.size, self.mtime = 0, 0.0

    @property
    def exists(self) -> bool:
        return bool(self.path) and os.path.exists(self.path)

    def to_dict(self) -> dict:
        return dict(path=self.path, size=self.size, mtime=self.mtime,
                    pages=self.pages, fp=self.fp, role=self.role)

    @classmethod
    def from_dict(cls, d: dict) -> "Source":
        return cls(path=d.get("path", ""), size=d.get("size", 0),
                   mtime=d.get("mtime", 0.0), pages=d.get("pages"),
                   fp=d.get("fp"), role=d.get("role", "primary"))


@dataclass
class Item:
    """一个产物。"""

    path: str
    kind: str = KIND_OTHER
    size: int = 0
    mtime: float = 0.0
    pages: int | None = None
    params: dict = field(default_factory=dict)
    params_hash: str = ""
    created: str = ""
    manual: bool = False           # 用户手动加入/指定，清理时不动

    @classmethod
    def of(cls, path: str, kind: str, params: dict | None = None) -> "Item":
        it = cls(path=os.path.abspath(path), kind=kind, params=dict(params or {}),
                 created=now_iso())
        it.refresh()
        it.params_hash = params_hash(it.params)
        return it

    def refresh(self) -> None:
        try:
            st = os.stat(self.path)
            self.size, self.mtime = st.st_size, st.st_mtime
        except OSError:
            self.size, self.mtime = 0, 0.0

    @property
    def exists(self) -> bool:
        return bool(self.path) and os.path.exists(self.path)

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, "其它")

    def matches_params(self, current: dict | None) -> bool:
        """参数改过没有。没记录指纹的老条目一律当作"没改"。"""
        if not self.params_hash:
            return True
        return self.params_hash == params_hash(current)

    def to_dict(self) -> dict:
        return dict(path=self.path, kind=self.kind, size=self.size, mtime=self.mtime,
                    pages=self.pages, params=self.params, params_hash=self.params_hash,
                    created=self.created, manual=self.manual)

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        return cls(path=d.get("path", ""), kind=d.get("kind", KIND_OTHER),
                   size=d.get("size", 0), mtime=d.get("mtime", 0.0),
                   pages=d.get("pages"), params=d.get("params") or {},
                   params_hash=d.get("params_hash", ""),
                   created=d.get("created", ""), manual=bool(d.get("manual")))


@dataclass
class PrintEvent:
    at: str = ""
    tag: str = ""                  # single / duplex / manual-duplex / odd-only / cover / all
    sheets: int = 0                # 这次实际消耗的纸（张）
    job: str = ""                  # 打印机名（""=系统默认）
    pages: int = 0                 # 这份成品一共几面
    copies: int = 1
    sample: bool = False           # 只打样张：账上留着，但不算这一步做完
    note: str = ""

    def to_dict(self) -> dict:
        return dict(at=self.at, tag=self.tag, sheets=self.sheets, job=self.job,
                    pages=self.pages, copies=self.copies, sample=self.sample,
                    note=self.note)

    @classmethod
    def from_dict(cls, d: dict) -> "PrintEvent":
        return cls(at=d.get("at", ""), tag=d.get("tag", ""),
                   sheets=int(d.get("sheets", 0) or 0), job=d.get("job", ""),
                   pages=int(d.get("pages", 0) or 0),
                   copies=int(d.get("copies", 1) or 1),
                   sample=bool(d.get("sample")), note=d.get("note", ""))


@dataclass
class Project:
    """一卷 = 一个项目。这本书所有的东西都挂在这里。"""

    id: str
    name: str
    series_id: str | None = None
    index: int | None = None
    created: str = field(default_factory=now_iso)
    opened: str = ""

    source: Source | None = None
    extras: list[Source] = field(default_factory=list)
    source_history: list[Source] = field(default_factory=list)

    items: list[Item] = field(default_factory=list)
    final: str | None = None
    missing: list[str] = field(default_factory=list)

    params: dict = field(default_factory=dict)        # {"BookletPage": {...}}
    print_plan: dict = field(default_factory=dict)
    prints: list[PrintEvent] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)  # 被跳过的步骤号
    view: dict = field(default_factory=dict)          # 选中节点/缩放/滚动
    notes: str = ""

    # ── 条目操作 ──
    def add_item(self, item: Item) -> Item:
        """同一个路径只留一条（重跑会覆盖信息，不叠加）。"""
        self.items = [i for i in self.items if os.path.abspath(i.path) != os.path.abspath(item.path)]
        self.items.append(item)
        return item

    def first(self, *kinds: str) -> Item | None:
        for it in self.items:
            if it.kind in kinds and it.exists:
                return it
        return None

    def layout_item(self) -> Item | None:
        return self.first(*LAYOUT_KINDS)

    def item_for_step(self, step: int) -> Item | None:
        if step == STEP_SPLIT:
            return self.first(KIND_BODY) or self.first(KIND_COVER_SRC)
        if step == STEP_COVER:
            return self.first(KIND_COVER)
        if step == STEP_PAGER:
            return self.first(KIND_PAGED)
        if step == STEP_LAYOUT:
            return self.layout_item()
        return None

    # ── 状态派生 ──
    @property
    def source_exists(self) -> bool:
        return bool(self.source and self.source.exists)

    def _input_mtime(self, step: int) -> float:
        """这一步"应该比什么新"：取它真正的上游。"""
        if step == STEP_COVER:
            src = self.first(KIND_COVER_SRC)
            return max(self.source.mtime if self.source else 0.0, src.mtime if src else 0.0)
        if step == STEP_PAGER:
            body = self.first(KIND_BODY)
            return body.mtime if body else (self.source.mtime if self.source else 0.0)
        if step == STEP_LAYOUT:
            up = self.first(KIND_PAGED) or self.first(KIND_BODY)
            return up.mtime if up else (self.source.mtime if self.source else 0.0)
        return self.source.mtime if self.source else 0.0

    def _params_for_item(self, item: Item) -> dict | None:
        key = KIND_TOOL.get(item.kind)
        return self.params.get(key) if key else None

    def step_state(self, step: int) -> tuple[str, str]:
        """返回 (状态, 一句话原因)，界面直接拿去显示。"""
        if step in self.skipped:
            return ST_SKIP, "已跳过"

        if step == STEP_IMPORT:
            if self.source_exists:
                return ST_DONE, f"{self.source.pages or '?'} 页"
            return ST_TODO, "还没导入原稿"

        if step == STEP_SPLIT:
            body = self.first(KIND_BODY)
            if body:
                if body.mtime < (self.source.mtime if self.source else 0) - 1:
                    return ST_STALE, "原稿变过，需要重新分割"
                return ST_DONE, f"正文 {body.pages or '?'} 页"
            if not self.source_exists:
                return ST_BLOCKED, "先导入原稿"
            return ST_TODO, "还没分割"

        item = self.item_for_step(step)
        if item:
            if item.mtime < self._input_mtime(step) - 1:
                return ST_STALE, "上游变过，需要重跑"
            if not item.matches_params(self._params_for_item(item)):
                return ST_STALE, "参数改过，需要重跑"
            return ST_DONE, f"{item.pages or '?'} 页"

        if step == STEP_COVER:
            return (ST_TODO, "还没做封面") if self.source_exists else (ST_BLOCKED, "先导入原稿")
        if step == STEP_PAGER:
            return (ST_TODO, "还没加页码") if self.source_exists else (ST_BLOCKED, "先导入原稿")
        if step == STEP_LAYOUT:
            body = self.first(KIND_BODY) or self.first(KIND_PAGED)
            if not body:
                return ST_BLOCKED, "先分割出正文"
            return ST_TODO, "还没排版"
        if step == STEP_PRINT:
            if not self.layout_item():
                return ST_BLOCKED, "内容还没排版"
            done = [e for e in self.prints if not e.sample]
            if not done:
                if not self.first(KIND_COVER):
                    return ST_TODO, "还没打印（封面未做，可选）"
                return ST_TODO, "还没打印"
            layout = self.layout_item()
            if layout is not None:
                # 直接问磁盘上的时间：别的页重跑排版后，这里不用先"重新扫描"也知道过期
                try:
                    fresh = os.path.getmtime(layout.path)
                except OSError:
                    fresh = layout.mtime
                if iso_ts(done[-1].at) < fresh - 1:
                    return ST_STALE, "排版改过，需要重新打印"
            return ST_DONE, f"已打 {len(done)} 次"
        if step == STEP_FINAL:
            if self.final:
                return ST_DONE, "已定稿"
            return ST_TODO, "还没定稿"
        return ST_TODO, ""

    @property
    def done_steps(self) -> int:
        return sum(1 for s in STEPS if self.step_state(s)[0] == ST_DONE)

    @property
    def real_prints(self) -> list["PrintEvent"]:
        """真正打完的记录（样张不算）。"""
        return [e for e in self.prints if not e.sample]

    @property
    def status(self) -> str:
        """书架上的一行状态（比七步粗一档）。"""
        if self.final:
            return "定稿"
        if self.real_prints:
            return "已打印"
        if self.layout_item():
            return "已排版"
        if self.first(KIND_BODY):
            return "已分割"
        if self.source_exists:
            return "已导入"
        return "缺原稿"

    @property
    def size_total(self) -> int:
        total = self.source.size if self.source else 0
        return total + sum(i.size for i in self.items if i.exists) \
            + sum(e.size for e in self.extras if e.exists)

    def overdue_final(self) -> bool:
        """定稿是不是可能过期了（原稿或上游产物比定稿新）。"""
        if not self.final:
            return False
        try:
            final_mtime = os.stat(self.final).st_mtime
        except OSError:
            return False
        for it in ([self.source] if self.source else []) + list(self.items):
            if it and it.exists and it.path != self.final and it.mtime > final_mtime + 1:
                return True
        return False

    def set_final(self, path: str | None) -> None:
        self.final = os.path.abspath(path) if path else None

    def mark_skipped(self, step: int, skip: bool = True) -> None:
        if skip and step not in self.skipped:
            self.skipped.append(step)
        if not skip and step in self.skipped:
            self.skipped.remove(step)

    # ── 序列化 ──
    def to_dict(self) -> dict:
        return dict(
            id=self.id, name=self.name, series_id=self.series_id, index=self.index,
            created=self.created, opened=self.opened,
            source=self.source.to_dict() if self.source else None,
            extras=[e.to_dict() for e in self.extras],
            source_history=[s.to_dict() for s in self.source_history],
            items=[i.to_dict() for i in self.items],
            final=self.final, missing=list(self.missing),
            params=self.params, print_plan=self.print_plan,
            prints=[p.to_dict() for p in self.prints],
            skipped=list(self.skipped), view=self.view, notes=self.notes,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        pr = cls(id=d.get("id", ""), name=d.get("name", ""),
                 series_id=d.get("series_id"), index=d.get("index"),
                 created=d.get("created", ""), opened=d.get("opened", ""),
                 source=Source.from_dict(d["source"]) if d.get("source") else None,
                 extras=[Source.from_dict(x) for x in d.get("extras", [])],
                 source_history=[Source.from_dict(x) for x in d.get("source_history", [])],
                 items=[Item.from_dict(x) for x in d.get("items", [])],
                 final=d.get("final"), missing=list(d.get("missing", [])),
                 params=d.get("params") or {}, print_plan=d.get("print_plan") or {},
                 prints=[PrintEvent.from_dict(x) for x in d.get("prints", [])],
                 skipped=[int(x) for x in d.get("skipped", [])],
                 view=d.get("view") or {}, notes=d.get("notes", ""))
        return pr


DEFAULT_SERIES_ID = "s-single"
DEFAULT_SERIES_NAME = "单本"


@dataclass
class Series:
    """系列只放系列级的东西，不放单本的细节。"""

    id: str
    name: str
    cover: str | None = None
    defaults: dict = field(default_factory=dict)
    created: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return dict(id=self.id, name=self.name, cover=self.cover,
                    defaults=self.defaults, created=self.created)

    @classmethod
    def from_dict(cls, d: dict) -> "Series":
        return cls(id=d.get("id", ""), name=d.get("name", ""), cover=d.get("cover"),
                   defaults=d.get("defaults") or {}, created=d.get("created", ""))


@dataclass
class Shelf:
    version: int = 1
    series: list[Series] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)

    def by_id(self, pid: str) -> Project | None:
        return next((p for p in self.projects if p.id == pid), None)

    def series_by_id(self, sid: str | None) -> Series | None:
        return next((s for s in self.series if s.id == sid), None) if sid else None

    def projects_of(self, sid: str | None) -> list[Project]:
        out = [p for p in self.projects if p.series_id == sid]
        return sorted(out, key=lambda p: (p.index if p.index is not None else 10**6, p.name))

    def ensure_default_series(self) -> Series:
        """「单本」是内置系列：一本书必须属于某个系列，散本就归它。"""
        s = self.series_by_id(DEFAULT_SERIES_ID)
        if s is None:
            s = Series(id=DEFAULT_SERIES_ID, name=DEFAULT_SERIES_NAME)
            self.series.append(s)
        return s

    def add_project(self, p: Project) -> Project:
        """加入书架时强制归系列：没有或系列已不存在 → 进「单本」。"""
        self.ensure_default_series()
        if not p.series_id or not self.series_by_id(p.series_id):
            p.series_id = DEFAULT_SERIES_ID
        self.projects = [x for x in self.projects if x.id != p.id]
        self.projects.append(p)
        return p

    def to_dict(self) -> dict:
        return dict(version=self.version,
                    series=[s.to_dict() for s in self.series],
                    projects=[p.to_dict() for p in self.projects])

    @classmethod
    def from_dict(cls, d: dict) -> "Shelf":
        shelf = cls(version=int(d.get("version", 1)),
                    series=[Series.from_dict(x) for x in d.get("series", [])],
                    projects=[Project.from_dict(x) for x in d.get("projects", [])])
        # 读盘时就修好"没有系列"的旧数据，保证界面上永远有系列可归
        shelf.ensure_default_series()
        for p in shelf.projects:
            if not p.series_id or not shelf.series_by_id(p.series_id):
                p.series_id = DEFAULT_SERIES_ID
        return shelf
