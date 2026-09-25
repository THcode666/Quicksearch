"""界面公共小部件与工具函数。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QMessageBox, QWidget

from app.store import STATUS_RESOLVED
from .theme import STATUS_COLORS


def elide(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"


def confirm(parent: QWidget, title: str, text: str) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Question)
    box.setText(text)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.setDefaultButton(QMessageBox.No)
    box.button(QMessageBox.Yes).setText("确定")
    box.button(QMessageBox.No).setText("取消")
    return box.exec() == QMessageBox.Yes


def info(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)


def warn(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)


class FlashLabel(QLabel):
    """操作后的轻提示，几秒后自动消失（不弹窗打断作业）。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Flash")
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def flash(self, text: str, ms: int = 3500) -> None:
        self.setText(text)
        self.show()
        self._timer.start(ms)


def make_status_chip(status: str) -> QLabel:
    """状态彩色标签：待补充（橙）/ 已解决（绿）。"""
    bg, fg = STATUS_COLORS.get(status, ("#eef1f6", "#42506a"))
    lab = QLabel("待补充" if status != STATUS_RESOLVED else "已解决")
    lab.setAlignment(Qt.AlignCenter)
    lab.setStyleSheet(
        f"background:{bg}; color:{fg}; border-radius:9px; padding:3px 10px; font-weight:600;")
    return lab
