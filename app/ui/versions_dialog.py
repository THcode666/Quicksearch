"""版本记录对话框：查看 SOP 的历史版本，可回滚到任一版本。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

from app.store import Sop, Store
from .common import confirm, info


class VersionsDialog(QDialog):
    def __init__(self, store: Store, sop: Sop, parent=None):
        super().__init__(parent)
        self.store = store
        self.sop = sop
        self.rolled_back = False
        self.setWindowTitle(f"版本记录 — {sop.name}")
        self.setMinimumSize(760, 520)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        tip = QLabel("每次保存会自动记录一个版本（保留最近 "
                     f"{Store.MAX_VERSIONS} 个）。“回滚到此版本”会把该版本的内容恢复为当前版本，"
                     "回滚前的状态也会自动存为一个新版本，随时可再切回。")
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        root.addWidget(tip)

        mid = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("版本列表（新 → 旧）："))
        self.version_list = QListWidget()
        self.version_list.currentRowChanged.connect(self._show_detail)
        left.addWidget(self.version_list, 1)
        mid.addLayout(left, 5)

        right = QVBoxLayout()
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setAlignment(Qt.AlignTop)
        self.detail.setObjectName("CardTitle")
        right.addWidget(self.detail, 1)
        self.preview = QLabel("")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(240, 160)
        self.preview.setStyleSheet(
            "background:#f4f6fa; border:1px solid #d9e0ea; border-radius:10px;")
        right.addWidget(self.preview)
        mid.addLayout(right, 4)
        root.addLayout(mid, 1)

        row = QHBoxLayout()
        self.rollback_btn = QPushButton("↩ 回滚到此版本")
        self.rollback_btn.setObjectName("Primary")
        self.rollback_btn.clicked.connect(self._rollback)
        row.addWidget(self.rollback_btn)
        row.addStretch(1)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        root.addLayout(row)

        self._load_versions()

    def _load_versions(self) -> None:
        self.versions = self.store.get_versions(self.sop.id)
        self.version_list.clear()
        for v in self.versions:
            it = QListWidgetItem(f"{v.saved_at}　{len(v.pages)} 页　{v.name}")
            it.setData(Qt.UserRole, v.id)
            self.version_list.addItem(it)
        if self.versions:
            self.version_list.setCurrentRow(0)
        else:
            self.detail.setText("暂无版本记录。\n每次在编辑器里点击“保存”都会自动记录一个版本。")
            self.rollback_btn.setEnabled(False)

    def _current_version(self):
        it = self.version_list.currentItem()
        if not it:
            return None
        vid = it.data(Qt.UserRole)
        return next((v for v in self.versions if v.id == vid), None)

    def _show_detail(self, row: int) -> None:
        ver = self._current_version()
        if ver is None:
            return
        codes = "、".join(ver.alarm_codes) or "（未填）"
        self.detail.setText(
            f"版本时间：{ver.saved_at}\n"
            f"SOP 名称：{ver.name}\n"
            f"报警代码：{codes}\n"
            f"页数：{len(ver.pages)}\n"
            f"解决方式：{ver.solution or '（无）'}")
        if ver.pages:
            from app.store import Store  # noqa: F401
            img = QImage(str(self.store.version_dir(ver.sop_id, ver.id) / ver.pages[0]))
            if not img.isNull():
                pm = QPixmap.fromImage(img).scaled(
                    self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.preview.setPixmap(pm)
                self.preview.setText("")
                return
        self.preview.setPixmap(QPixmap())
        self.preview.setText("该版本无页面图片")

    def _rollback(self) -> None:
        ver = self._current_version()
        if ver is None:
            return
        if not confirm(self, "回滚到此版本",
                       f"确定把「{self.sop.name}」回滚到 {ver.saved_at} 的版本吗？\n\n"
                       "· 当前内容会先自动保存为一个新版本，随时可再切回\n"
                       "· 名称、报警代码、解决方式和页面图片都会恢复为该版本的内容"):
            return
        result = self.store.rollback_to_version(self.sop.id, ver.id)
        if result is None:
            info(self, "提示", "回滚失败：版本数据不存在或已被清理。")
            return
        self.rolled_back = True
        self.sop = result
        self._load_versions()
        info(self, "完成", "已回滚，并生成一条新的版本记录。")
