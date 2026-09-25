"""生成 assets/icon.png 与 assets/icon.ico（exe 图标，多尺寸）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter

    app = QGuiApplication(sys.argv)   # noqa: F841 绘制前需先有 QApplication

    from app.icons import paint_logo

    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)

    img = QImage(1024, 1024, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    paint_logo(p, 1024)
    p.end()

    png = assets / "icon.png"
    if not img.save(str(png)):
        print("保存 icon.png 失败")
        return 1

    from PIL import Image
    pil = Image.open(png)
    sizes = [(256, 256), (128, 128), (96, 96), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    pil.save(assets / "icon.ico", sizes=sizes)
    print(f"已生成 {png} 和 {assets / 'icon.ico'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
