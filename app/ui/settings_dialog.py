"""设置对话框：数据目录（支持共享路径）、PPT 转换清晰度、数据备份。"""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSpinBox, QVBoxLayout)

from app.config import APP_VERSION, Config
from app.store import Store


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, store: Store, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.store = store
        self.data_dir_changed = False
        self.setWindowTitle("设置")
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ---- 数据目录 ----
        root.addWidget(QLabel("数据目录（SOP 库和反馈记录的存放位置）："))
        row = QHBoxLayout()
        self.dir_edit = QLineEdit()
        self.dir_edit.setReadOnly(True)
        self.dir_edit.setText(str(store.data_dir))
        row.addWidget(self.dir_edit, 1)
        browse = QPushButton("更改…")
        browse.clicked.connect(self._browse)
        open_btn = QPushButton("打开文件夹")
        open_btn.clicked.connect(self._open_dir)
        row.addWidget(browse)
        row.addWidget(open_btn)
        root.addLayout(row)

        tip = QLabel(
            "· 单机使用：保持默认即可（exe 旁边的 Data 文件夹，拷走 exe 时把 Data 一起拷走）。\n"
            "· 多台电脑共用：把数据目录改为局域网共享路径，如 \\\\服务器\\share\\QuicksearchData，\n"
            "  各电脑都指向同一路径即可共用一套 SOP 库（建议同一时间由一名工程师维护）。\n"
            "· 更改后立即生效并重新加载数据。")
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        root.addWidget(tip)

        # ---- PPT 清晰度 ----
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("PPT 转图片的清晰度（宽度像素）："))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(720, 2560)
        self.width_spin.setSingleStep(160)
        self.width_spin.setValue(int(cfg.data.get("ppt_width", 1440) or 1440))
        self.width_spin.setToolTip("数值越大越清晰，图片占用空间也越大。常规 1440 即可。")
        row2.addWidget(self.width_spin)
        row2.addStretch(1)
        root.addLayout(row2)

        # ---- 备份 ----
        backup_row = QHBoxLayout()
        backup_btn = QPushButton("备份数据…")
        backup_btn.clicked.connect(self._backup)
        backup_row.addWidget(backup_btn)
        backup_row.addStretch(1)
        root.addLayout(backup_row)

        # ---- 关于 ----
        about = QLabel(f"Quicksearch v{APP_VERSION} — 机台报警 SOP 快速查找 / SOP 库管理 / 反馈跟踪")
        about.setObjectName("Muted")
        root.addWidget(about)

        bb = QDialogButtonBox()
        save = bb.addButton("保存", QDialogButtonBox.AcceptRole)
        save.setObjectName("Primary")
        bb.addButton("取消", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择数据目录", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def _open_dir(self) -> None:
        try:
            os.startfile(self.dir_edit.text())
        except OSError as e:
            QMessageBox.warning(self, "打开失败", f"无法打开文件夹：\n{e}")

    def _backup(self) -> None:
        dest = QFileDialog.getExistingDirectory(self, "选择备份保存位置")
        if not dest:
            return
        name = f"Quicksearch备份_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        target = Path(dest) / name
        try:
            self.setCursor(Qt.WaitCursor)
            shutil.copytree(self.store.data_dir, target,
                            ignore=shutil.ignore_patterns(".staging_*", "*.tmp"))
        except OSError as e:
            QMessageBox.critical(self, "备份失败", f"{e}")
            return
        finally:
            self.unsetCursor()
        QMessageBox.information(self, "备份完成", f"已备份到：\n{target}")

    def _save(self) -> None:
        new_dir = self.dir_edit.text().strip()
        old_dir = str(self.store.data_dir)
        self.cfg.data["ppt_width"] = self.width_spin.value()
        if new_dir and new_dir != old_dir:
            self.cfg.data["data_dir"] = new_dir
            self.data_dir_changed = True
        self.cfg.save()
        self.accept()
