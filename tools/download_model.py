"""下载高清修复所需的开源超分模型（首次打包前运行一次）。

模型来源：GitHub 开源项目 Saafke/FSRCNN_Tensorflow（FSRCNN x2，约 38KB）。
为尊重上游发布方式，仓库不直接附带模型文件，打包前自动下载。
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_URL = "https://github.com/Saafke/FSRCNN_Tensorflow/raw/master/models/FSRCNN_x2.pb"
DEST = ROOT / "assets" / "models" / "FSRCNN_x2.pb"
MIN_SIZE = 30000   # 完整模型约 38KB，小于此视为下载不完整


def main() -> int:
    if DEST.exists() and DEST.stat().st_size >= MIN_SIZE:
        print(f"模型已存在：{DEST}")
        return 0
    DEST.parent.mkdir(parents=True, exist_ok=True)
    print("正在下载超分模型 FSRCNN_x2.pb ...")
    try:
        urllib.request.urlretrieve(MODEL_URL, DEST)
    except Exception as e:
        print(f"下载失败：{e}\n请手动从 {MODEL_URL} 下载后放到 {DEST}")
        return 1
    if not DEST.exists() or DEST.stat().st_size < MIN_SIZE:
        print("下载不完整，请重试或手动下载。")
        return 1
    print(f"已保存：{DEST}（{DEST.stat().st_size} 字节）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
