"""烽火台数据层：线上异常汇报的记录、编辑、截图管理。

- 数据：Data/beacons.json（索引，紧凑JSON）+ Data/beacons/<id>/（截图 shot_NN.png、生成的 report.html）
- 多机共享：追加/修改前强制读盘合并（与 Store 的多机策略一致）
- 写入均为原子替换，断电不损坏
"""
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

from .store import load_json, save_json_atomic


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Beacon:
    """一条线上异常汇报。"""
    id: str = ""
    date: str = ""              # 异常发生日期 yyyy-mm-dd（新建时默认电脑当前日期）
    machine: str = ""           # 机台（选填）
    recipe: str = ""            # Recipe（选填）
    test_od: str = ""           # 测试OD（选填）
    probe_card: str = ""        # 针卡（选填）
    probe_card_len: str = ""    # 针卡长度（选填）
    description: str = ""       # 问题描述/现象
    shots: list = field(default_factory=list)   # 截图文件名（相对 beacons/<id>/）
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
    def from_dict(d: dict) -> "Beacon":
        return Beacon(
            id=str(d.get("id") or new_id()),
            date=str(d.get("date") or ""),
            machine=str(d.get("machine") or ""),
            recipe=str(d.get("recipe") or ""),
            test_od=str(d.get("test_od") or ""),
            probe_card=str(d.get("probe_card") or ""),
            probe_card_len=str(d.get("probe_card_len") or ""),
            description=str(d.get("description") or ""),
            shots=[str(s) for s in (d.get("shots") or [])],
            created_at=str(d.get("created_at") or ""),
            updated_at=str(d.get("updated_at") or ""),
        )


class BeaconStore:
    MAX_RENDER_ROWS = 500

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.index_path = self.data_dir / "beacons.json"
        self.records: list[Beacon] = []
        self._sig = object()
        self.load_all()

    # ---------- 基础 ----------
    @staticmethod
    def _file_sig(path: Path):
        try:
            st = os.stat(path)
            return (st.st_mtime, st.st_size)
        except OSError:
            return None

    def _changed(self) -> bool:
        return BeaconStore._file_sig(self.index_path) != self._sig

    def _mark(self) -> None:
        self._sig = BeaconStore._file_sig(self.index_path)

    def load_all(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        raw = load_json(self.index_path, {"version": 1, "records": []})
        self.records = [Beacon.from_dict(d) for d in raw.get("records", [])]
        self._mark()

    def reload(self) -> None:
        self.load_all()

    def save(self) -> None:
        records = [b.to_dict() for b in self.records]
        records.sort(key=lambda d: (d.get("date") or "", d.get("created_at") or ""),
                     reverse=True)
        save_json_atomic(self.index_path, {"version": 1, "records": records}, indent=None)
        self._mark()

    def beacon_dir(self, beacon_id: str) -> Path:
        return self.data_dir / "beacons" / beacon_id

    # ---------- 增改查删 ----------
    def get_beacon(self, beacon_id: str) -> Beacon | None:
        for b in self.records:
            if b.id == beacon_id:
                return b
        return None

    def upsert_beacon(self, beacon: Beacon, shot_sources: list[Path] | None = None) -> None:
        """按 id 插入或更新。shot_sources：各截图的来源文件（与截图顺序一致），
        会被统一转存为 beacons/<id>/shot_NN.<ext>；
        传 None 表示不改动现有截图文件。先读盘合并，保留其他电脑的新增。"""
        self.load_all()
        for i, b in enumerate(self.records):
            if b.id == beacon.id:
                self.records[i] = beacon
                break
        else:
            self.records.append(beacon)
        folder = self.beacon_dir(beacon.id)
        folder.mkdir(parents=True, exist_ok=True)
        if shot_sources is not None:
            names: list[str] = []
            for i, src in enumerate(shot_sources, 1):
                ext = Path(src).suffix.lower() or ".png"
                dst = folder / f"shot_{i:02d}{ext}"
                try:
                    if Path(src).resolve() != dst.resolve():
                        shutil.copyfile(src, dst)
                except shutil.SameFileError:
                    pass
                names.append(dst.name)
            # 清理已移除的旧截图
            for old in folder.glob("shot_*"):
                if old.name not in names:
                    try:
                        old.unlink()
                    except OSError:
                        pass
            beacon.shots = names
        beacon.updated_at = now_str()
        self.save()

    def delete_beacon(self, beacon_id: str) -> bool:
        self.load_all()
        if self.get_beacon(beacon_id) is None:
            return False
        self.records = [b for b in self.records if b.id != beacon_id]
        self.save()
        shutil.rmtree(self.beacon_dir(beacon_id), ignore_errors=True)
        return True

    def shot_path(self, beacon: Beacon, index: int) -> Path:
        return self.beacon_dir(beacon.id) / beacon.shots[index]

    def get_all(self) -> list[Beacon]:
        """按日期新→旧（同日按创建顺序后→前）。"""
        seq = list(enumerate(self.records))
        seq.sort(key=lambda p: (p[1].date or "", p[1].created_at or "", p[0]),
                 reverse=True)
        return [b for _i, b in seq]
