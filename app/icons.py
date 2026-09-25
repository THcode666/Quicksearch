"""程序图标：一本打开的书 + 放大镜。

运行时用 QPainter 直接绘制生成 QIcon（无需附带资源文件），
打包脚本另用 tools/make_icon.py 生成 .ico 作为 exe 图标。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QIcon, QPainter, QPainterPath, QPen,
                           QPixmap)

CANVAS = 512.0
BLUE_COVER = QColor("#24539f")
PAGE_FILL = QColor("#f8fbff")
LINE_BLUE = QColor("#a9c7f2")
INK = QColor("#17335f")
GLASS = QColor(210, 232, 255, 175)


def _wing(path: QPainterPath, mirror: bool) -> QPainterPath:
    """一片书页（左页或右页），带弯曲的页边。"""
    s = -1.0 if mirror else 1.0
    cx = 250.0
    p = QPainterPath()
    p.moveTo(cx, 222)
    p.cubicTo(cx + s * 54, 196, cx + s * 118, 184, cx + s * 172, 198)
    p.lineTo(cx + s * 172, 352)
    p.cubicTo(cx + s * 118, 338, cx + s * 54, 348, cx, 380)
    p.closeSubpath()
    path.addPath(p)
    return path


def _book(painter: QPainter) -> None:
    # 封面（略低一点，露出下边缘）
    painter.save()
    painter.translate(0, 16)
    pen = QPen(BLUE_COVER, 8)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QBrush(BLUE_COVER))
    painter.drawPath(_wing(QPainterPath(), False))
    painter.drawPath(_wing(QPainterPath(), True))
    painter.restore()

    # 书页
    pen = QPen(BLUE_COVER, 8)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QBrush(PAGE_FILL))
    painter.drawPath(_wing(QPainterPath(), False))
    painter.drawPath(_wing(QPainterPath(), True))

    # 书脊
    pen = QPen(BLUE_COVER, 8)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawLine(QPointF(250, 224), QPointF(250, 378))

    # 页面上的文字线条
    pen = QPen(LINE_BLUE, 13)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    lines = [
        (108, 252, 224, 238), (108, 296, 224, 288), (108, 338, 224, 334),
        (288, 238, 404, 252), (288, 288, 404, 296), (288, 334, 404, 338),
    ]
    for x1, y1, x2, y2 in lines:
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _magnifier(painter: QPainter) -> None:
    cx, cy, r = 350.0, 202.0, 82.0
    # 镜片
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(GLASS))
    painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
    # 手柄（先画，压在镜框下面）
    pen = QPen(INK, 42)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawLine(QPointF(cx + r * 0.707, cy + r * 0.707),
                     QPointF(cx + r * 0.707 + 62, cy + r * 0.707 + 66))
    # 镜框
    pen = QPen(INK, 28)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
    # 高光
    pen = QPen(QColor(255, 255, 255, 165), 14)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawArc(QRectF(cx - 55, cy - 55, 110, 110), 105 * 16, 55 * 16)


def paint_logo(painter: QPainter, size: int) -> None:
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(size / CANVAS, size / CANVAS)
    _book(painter)
    _magnifier(painter)
    painter.restore()


def render_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    paint_logo(p, size)
    p.end()
    return pm


def make_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(render_pixmap(size))
    return icon
