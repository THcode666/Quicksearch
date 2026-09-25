"""路径与配置管理。

- 打包后：exe 所在目录为程序根目录；源码运行：项目根目录。
- 数据目录（SOP 库）默认放在程序根目录下的 Data 文件夹（便携式），
  若该位置不可写则退回到 %LOCALAPPDATA%\\Quicksearch\\Data。
- 程序自身的小配置（数据目录、PPT 导出宽度）存放在 %APPDATA%/Quicksearch/config.json，
  保证只读安装位置下也能正常工作。
- 数据目录优先级：环境变量 QUICKSEARCH_DATA_DIR > 配置文件 > 默认位置。
  局域网共享部署时把数据目录指向 \\\\服务器\\共享目录 即可多机共用一套 SOP 库。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

APP_NAME = "Quicksearch"
APP_VERSION = "1.1.0"
APP_TITLE = "Quicksearch — SOP 快速查找"


def app_base_dir() -> Path:
    """程序根目录：打包后为 exe 所在目录，源码运行为项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def is_dir_writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        fd, probe = tempfile.mkstemp(dir=str(p), prefix=".probe_")
        os.close(fd)
        os.unlink(probe)
        return True
    except OSError:
        return False


def default_data_dir() -> Path:
    cand = app_base_dir() / "Data"
    if is_dir_writable(cand):
        return cand
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / APP_NAME / "Data"


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def resource_dir() -> Path:
    """随 exe 打包的只读资源目录（模型文件等）。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return app_base_dir()


def model_file(name: str) -> Path:
    """超分模型位置：打包后在 _MEIPASS/models；源码运行在 assets/models。"""
    candidates = (resource_dir() / "models" / name,
                  resource_dir() / "assets" / "models" / name)
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


class Config:
    """轻量配置。path 可注入以便测试。"""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else config_dir() / "config.json"
        self.data: dict = {}
        self.load()

    def load(self) -> None:
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(self.data, dict):
                self.data = {}
        except Exception:
            self.data = {}
        self.data.setdefault("data_dir", "")      # 空 = 使用默认位置
        self.data.setdefault("ppt_width", 1440)   # PPT 转图片的目标宽度（像素）

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def resolve_data_dir(self) -> Path:
        override = (os.environ.get("QUICKSEARCH_DATA_DIR") or "").strip()
        if override:
            return Path(override)
        custom = str(self.data.get("data_dir") or "").strip()
        if custom:
            return Path(custom)
        return default_data_dir()
