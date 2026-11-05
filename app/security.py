"""SOP 库访问密码（防误动级别的保护）。

- 哈希存放在数据目录 security.json：多机共享数据目录时，全网络使用同一套密码；
  工程师在“设置”里修改后，其他电脑即时生效（每次校验都从磁盘读取）。
- 源码与文档中只保留默认密码的加盐哈希，不出现明文；
  忘记密码时可删除数据目录下的 security.json 恢复出厂密码。
- 定位是防止随手误入与误操作，不是对抗专业破解的安全机制。
"""
from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

from .store import save_json_atomic

_DEFAULT_SALT = "quicksearch-sop-lib"
# 出厂密码的加盐哈希（明文不出现在源码/文档/仓库中；修改密码后随机换盐）
_DEFAULT_HASH = "e5d807a2a2cd4b217504c1afe3c794d0cd85a2e7a2cd08d6418866590ee95add"


def _hash(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


class PasswordGate:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "security.json"

    def _read(self) -> tuple[str, str]:
        """从数据目录读取盐+哈希；不存在/损坏时初始化为出厂密码。"""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            salt = str(raw.get("salt") or "")
            h = str(raw.get("hash") or "")
        except Exception:
            salt = h = ""
        if not (salt and h):
            salt, h = _DEFAULT_SALT, _DEFAULT_HASH
            self._write(salt, h)
        return salt, h

    def _write(self, salt: str, h: str) -> None:
        save_json_atomic(self.path,
                         {"version": 1, "salt": salt, "hash": h},
                         indent=None)

    def verify(self, password: str) -> bool:
        salt, h = self._read()
        return bool(password) and _hash(password, salt) == h

    def using_default(self) -> bool:
        salt, h = self._read()
        return (salt, h) == (_DEFAULT_SALT, _DEFAULT_HASH)

    def set_password(self, new: str) -> None:
        new = new.strip()
        if not new:
            raise ValueError("密码不能为空")
        salt = secrets.token_hex(8)
        self._write(salt, _hash(new, salt))

    def change(self, old: str, new: str) -> bool:
        """校验旧密码后设置新密码；旧密码错误返回 False。"""
        if not self.verify(old):
            return False
        self.set_password(new)
        return True
