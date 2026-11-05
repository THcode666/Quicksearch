"""SOP 库密码输入对话框：连续输错 5 次锁定 30 秒，防止随手乱试。"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QLineEdit, QVBoxLayout)

from app.security import PasswordGate


class PasswordDialog(QDialog):
    MAX_FAILS = 5
    LOCKOUT_SECONDS = 30

    def __init__(self, gate: PasswordGate, parent=None, title: str = "进入 SOP 库"):
        super().__init__(parent)
        self.gate = gate
        self._fails = 0
        self.setWindowTitle(title)
        self.setMinimumWidth(400)

        tip = QLabel("SOP 库为工程师维护区域，请输入访问密码：")
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText("输入访问密码")
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#c62828;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        btns = QDialogButtonBox()
        self.ok_btn = btns.addButton("确定", QDialogButtonBox.AcceptRole)
        self.ok_btn.setObjectName("Primary")
        btns.addButton("取消", QDialogButtonBox.RejectRole)
        btns.accepted.connect(self._attempt)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.addWidget(tip)
        lay.addWidget(self.edit)
        lay.addWidget(self.error_label)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(btns)
        lay.addLayout(row)

        self.edit.returnPressed.connect(self._attempt)
        self.edit.setFocus()

    def _attempt(self) -> None:
        if self._fails >= self.MAX_FAILS:
            return   # 冷却锁定中
        if self.gate.verify(self.edit.text()):
            self.accept()
            return
        self._fails += 1
        if self._fails >= self.MAX_FAILS:
            self._start_lockout()
        else:
            self.error_label.setText(
                f"密码错误（第 {self._fails} 次），请重新输入。剩余尝试次数 "
                f"{self.MAX_FAILS - self._fails} 次。")
            self.error_label.show()
        self.edit.clear()
        self.edit.setFocus()

    def _start_lockout(self) -> None:
        remain = self.LOCKOUT_SECONDS
        self.ok_btn.setEnabled(False)
        self.error_label.setText(f"尝试次数过多，已临时锁定 {remain} 秒。")
        self.error_label.show()
        timer = QTimer(self)
        timer.setInterval(1000)

        def tick() -> None:
            nonlocal remain
            remain -= 1
            if remain > 0:
                self.error_label.setText(f"尝试次数过多，已临时锁定 {remain} 秒。")
            else:
                timer.stop()
                self._fails = 0
                self.ok_btn.setEnabled(True)
                self.error_label.hide()

        timer.timeout.connect(tick)
        timer.start()
