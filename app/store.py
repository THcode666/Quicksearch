"""数据层：SOP 与反馈记录的内存模型 + JSON 持久化（原子写入，兼容网络共享盘）。"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
PPT_EXTS = {".ppt", ".pptx"}

STATUS_PENDING = "pending"
STATUS_RESOLVED = "resolved"
STATUS_TEXT = {STATUS_PENDING: "待补充", STATUS_RESOLVED: "已解决"}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def natural_key(text: str) -> list:
    """自然排序键：数字按数值比较、字母忽略大小写，中文按原顺序稳定排列。"""
    return [int(t) if t.isdigit() else t.casefold() for t in re.split(r"(\d+)", str(text))]


def save_json_atomic(path: Path, obj, indent=1) -> None:
    """原子化写 JSON。网络盘上 os.replace 可能因他人占用失败，退化为直接覆盖并重试。

    indent=None 生成紧凑 JSON：大体量的数据文件（搜索记录/反馈）体积更小、读写更快。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=indent)
    tmp = path.with_name(path.name + ".tmp")
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            try:
                os.replace(tmp, path)
            except OSError:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                try:
                    tmp.unlink()
                except OSError:
                    pass
            return
        except PermissionError as e:  # 共享盘上文件正被其他电脑读取
            last_err = e
            time.sleep(0.15 * (attempt + 1))
    raise OSError(f"写入失败：{path}（{last_err}）")


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception:
        # 文件损坏时不让软件崩溃：备份坏文件后从头开始
        try:
            path.rename(path.with_name(f"{path.name}.corrupt-{new_id()}"))
        except OSError:
            pass
        return default


@dataclass
class Sop:
    id: str = ""
    name: str = ""
    alarm_codes: list = field(default_factory=list)   # 关联的报警代码，可多个
    solution: str = ""                                # 解决方式说明
    pages: list = field(default_factory=list)         # 页面文件名（相对 media/<id>/）
    originals: list = field(default_factory=list)     # 保留的 PPT 原文件 [{"file","name"}]
    source: str = "image"                             # image | ppt | mixed
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = new_id()
        if not self.created_at:
            self.created_at = now_str()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Sop":
        s = Sop(
            id=str(d.get("id") or new_id()),
            name=str(d.get("name") or ""),
            alarm_codes=[str(c) for c in (d.get("alarm_codes") or [])],
            solution=str(d.get("solution") or ""),
            pages=[str(p) for p in (d.get("pages") or [])],
            originals=[{"file": str(o.get("file")), "name": str(o.get("name"))}
                       for o in (d.get("originals") or []) if isinstance(o, dict)],
            source=str(d.get("source") or "image"),
            created_at=str(d.get("created_at") or ""),
            updated_at=str(d.get("updated_at") or ""),
        )
        return s

    @property
    def code_text(self) -> str:
        return " ".join(self.alarm_codes)


@dataclass
class Feedback:
    id: str = ""
    query: str = ""            # 报错名称 / 搜索内容
    remark: str = ""           # 备注
    status: str = STATUS_PENDING
    created_at: str = ""
    resolved_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = new_id()
        if not self.created_at:
            self.created_at = now_str()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Feedback":
        return Feedback(
            id=str(d.get("id") or new_id()),
            query=str(d.get("query") or ""),
            remark=str(d.get("remark") or ""),
            status=str(d.get("status") or STATUS_PENDING),
            created_at=str(d.get("created_at") or ""),
            resolved_at=str(d.get("resolved_at") or ""),
        )


@dataclass
class SearchLog:
    """一条搜索记录：谁在什么时候搜了什么、有没有找到 SOP、是否提交了报错截图。"""
    id: str = ""
    query: str = ""
    time: str = ""             # "2026-09-21 10:23:45"，日期与时间可按空格拆分显示
    found: bool = True
    shot: str = ""             # 机台报错截图，相对 data_dir 的路径（如 shots/<id>.png）

    def __post_init__(self):
        if not self.id:
            self.id = new_id()
        if not self.time:
            self.time = now_str()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "SearchLog":
        return SearchLog(
            id=str(d.get("id") or new_id()),
            query=str(d.get("query") or ""),
            time=str(d.get("time") or ""),
            found=bool(d.get("found", True)),
            shot=str(d.get("shot") or ""),
        )


class Store:
    """SOP 库 + 反馈记录 + 搜索记录。所有数据都在 data_dir 下：

    Data/
      sops.json        SOP 索引（只含元数据，启动时整体载入内存，体积极小）
      feedback.json    反馈记录
      searchlog.json   搜索记录（自动记录，超过上限自动丢弃最旧的）
      media/<sop_id>/  SOP 页面图片（查看时按需加载，不常驻内存）
    """

    MAX_SEARCH_LOGS = 10000   # 搜索记录上限，防止无限增长
    MAX_RENDER_ROWS = 500     # 列表页一次最多渲染的行数（超过部分用筛选缩小范围）

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.media_root = self.data_dir / "media"
        self.sops_path = self.data_dir / "sops.json"
        self.feedback_path = self.data_dir / "feedback.json"
        self.searchlog_path = self.data_dir / "searchlog.json"
        self.sops: list[Sop] = []
        self.feedback: list[Feedback] = []
        self.search_logs: list[SearchLog] = []
        # 各数据文件的 (mtime, size) 签名缓存：文件没变就跳过重新解析（多机同步的重读代价优化）。
        # 只比 mtime 会因 Windows 时间戳粒度漏掉同一时间片内的他机写入（append 必然改变 size，
        # 双特征可关闭该竞态窗口）；哨兵 object() 保证首次必读。
        self._sigs = {"sops": object(), "feedback": object(), "searchlog": object()}
        self.load_all()

    # ---------- 基础 ----------
    @staticmethod
    def _file_sig(path: Path):
        try:
            st = os.stat(path)
            return (st.st_mtime, st.st_size)
        except OSError:
            return None

    def _changed(self, key: str, path: Path) -> bool:
        """文件签名与上次加载/保存时不一致 → 需要重读（首次必读）。"""
        return Store._file_sig(path) != self._sigs[key]

    def _mark(self, key: str, path: Path) -> None:
        self._sigs[key] = Store._file_sig(path)

    def _load_sops(self, force: bool = False) -> None:
        if not force and not self._changed("sops", self.sops_path):
            return
        raw = load_json(self.sops_path, {"version": 1, "sops": []})
        self.sops = [Sop.from_dict(d) for d in raw.get("sops", [])]
        self._mark("sops", self.sops_path)

    def _load_feedback(self, force: bool = False) -> None:
        if not force and not self._changed("feedback", self.feedback_path):
            return
        raw = load_json(self.feedback_path, {"version": 1, "records": []})
        self.feedback = [Feedback.from_dict(d) for d in raw.get("records", [])]
        self._mark("feedback", self.feedback_path)

    def _load_search_logs(self, force: bool = False) -> None:
        if not force and not self._changed("searchlog", self.searchlog_path):
            return
        raw = load_json(self.searchlog_path, {"version": 1, "records": []})
        self.search_logs = [SearchLog.from_dict(d) for d in raw.get("records", [])]
        self._mark("searchlog", self.searchlog_path)

    def load_all(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._load_sops()
        self._load_feedback()
        self._load_search_logs()

    def reload(self) -> None:
        """从磁盘重读全部数据（多机共享时拉取其他电脑的最新内容）。"""
        self.load_all()

    def save_sops(self) -> None:
        save_json_atomic(self.sops_path, {"version": 1, "sops": [s.to_dict() for s in self.sops]})
        self._mark("sops", self.sops_path)

    def save_feedback(self) -> None:
        save_json_atomic(self.feedback_path,
                         {"version": 1, "records": [f.to_dict() for f in self.feedback]},
                         indent=None)   # 紧凑存储：记录多时体积/读写都减半以上
        self._mark("feedback", self.feedback_path)

    def save_search_logs(self) -> None:
        if len(self.search_logs) > self.MAX_SEARCH_LOGS:
            self.search_logs = self.search_logs[-self.MAX_SEARCH_LOGS:]
        save_json_atomic(self.searchlog_path,
                         {"version": 1, "records": [r.to_dict() for r in self.search_logs]},
                         indent=None)   # 紧凑存储
        self._mark("searchlog", self.searchlog_path)

    # ---------- SOP ----------
    def media_dir(self, sop_id: str) -> Path:
        return self.media_root / sop_id

    def page_path(self, sop: Sop, index: int) -> Path:
        return self.media_dir(sop.id) / sop.pages[index]

    def get_sop(self, sop_id: str) -> Sop | None:
        for s in self.sops:
            if s.id == sop_id:
                return s
        return None

    def add_sop(self, sop: Sop) -> None:
        self._load_sops(force=True)   # 先取最新，避免覆盖他机新增
        self.sops.append(sop)
        self.save_sops()

    def upsert_sop(self, sop: Sop) -> None:
        """按 id 更新或插入。强制读盘取最新列表再做替换，保留其他电脑新增的 SOP，
        避免多机维护时互相覆盖（合并路径不依赖时间戳缓存）。"""
        self._load_sops(force=True)
        for i, s in enumerate(self.sops):
            if s.id == sop.id:
                self.sops[i] = sop
                break
        else:
            self.sops.append(sop)
        self.save_sops()

    def update_sop(self) -> None:
        self.save_sops()

    def delete_sop(self, sop_id: str) -> None:
        self._load_sops(force=True)   # 以共享盘最新状态为基准删除
        self.sops = [s for s in self.sops if s.id != sop_id]
        self.save_sops()
        shutil.rmtree(self.media_dir(sop_id), ignore_errors=True)

    # ---------- 反馈 ----------
    def add_feedback(self, query: str, remark: str = "") -> Feedback:
        """先读盘合并再追加：多台电脑同时提交反馈时互相保留。"""
        self._load_feedback(force=True)
        fb = Feedback(query=query.strip(), remark=remark.strip(), status=STATUS_PENDING,
                      created_at=now_str())
        self.feedback.append(fb)
        self.save_feedback()
        return fb

    def get_feedback(self, fb_id: str) -> Feedback | None:
        for f in self.feedback:
            if f.id == fb_id:
                return f
        return None

    def set_feedback_status(self, fb_id: str, resolved: bool) -> None:
        self._load_feedback(force=True)   # 以共享盘最新状态为基准，保留其他电脑的新反馈
        fb = self.get_feedback(fb_id)
        if fb:
            fb.status = STATUS_RESOLVED if resolved else STATUS_PENDING
            fb.resolved_at = now_str() if resolved else ""
            self.save_feedback()

    def set_feedback_remark(self, fb_id: str, remark: str) -> None:
        self._load_feedback(force=True)
        fb = self.get_feedback(fb_id)
        if fb is not None:
            fb.remark = remark.strip()
            self.save_feedback()

    def delete_feedback(self, fb_id: str) -> None:
        self._load_feedback(force=True)
        self.feedback = [f for f in self.feedback if f.id != fb_id]
        self.save_feedback()

    # ---------- 搜索记录 ----------
    def add_search_log(self, query: str, found: bool) -> SearchLog:
        """先读盘合并再追加：多台电脑同时搜索时，记录互相保留而不是整份覆盖。"""
        self._load_search_logs(force=True)
        rec = SearchLog(query=query.strip(), found=found, time=now_str())
        self.search_logs.append(rec)
        self.save_search_logs()
        return rec

    def set_search_log_shot(self, log_id: str, src: Path) -> str:
        """把报错截图复制进数据目录（统一转存为 PNG 命名），返回相对路径。"""
        self._load_search_logs(force=True)
        rec = next((r for r in self.search_logs if r.id == log_id), None)
        if rec is None:
            raise OSError(f"搜索记录不存在：{log_id}")
        shots_dir = self.data_dir / "shots"
        shots_dir.mkdir(parents=True, exist_ok=True)
        target = shots_dir / f"{log_id}{Path(src).suffix.lower() or '.png'}"
        shutil.copyfile(src, target)
        rec.shot = f"shots/{target.name}"
        self.save_search_logs()
        return rec.shot

    def search_log_shot_path(self, rec: SearchLog) -> Path | None:
        if not rec.shot:
            return None
        p = self.data_dir / rec.shot
        return p if p.exists() else None

    def delete_search_log(self, log_id: str) -> None:
        self._load_search_logs(force=True)
        self.search_logs = [r for r in self.search_logs if r.id != log_id]
        self.save_search_logs()
        # 一并清理对应截图
        shot_dir = self.data_dir / "shots"
        for suffix in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
            p = shot_dir / f"{log_id}{suffix}"
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

    def clear_search_logs(self) -> None:
        self._load_search_logs(force=True)
        self.search_logs = []
        self.save_search_logs()
        shutil.rmtree(self.data_dir / "shots", ignore_errors=True)
