"""回收站对话框：误删的 SOP 在这里恢复或彻底删除。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from app.store import Store
from .common import FlashLabel, confirm


class TrashDialog(QDialog):
    COLS = ["SOP 名称", "报警代码", "页数", "删除时间"]

    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self.restored_any = False
        self.setWindowTitle("回收站 — 已删除的 SOP")
        self.setMinimumSize(680, 460)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        tip = QLabel("删除的 SOP 会在这里保留（页面文件一并保存），可随时恢复；"
                     "“彻底删除”或“清空回收站”后不可恢复。")
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        root.addWidget(tip)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._set_buttons_enabled)
        root.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.restore_btn = QPushButton("♻ 恢复选中")
        self.restore_btn.setObjectName("Primary")
        self.restore_btn.clicked.connect(self._restore)
        self.purge_btn = QPushButton("✕ 彻底删除")
        self.purge_btn.setObjectName("Danger")
        self.purge_btn.clicked.connect(self._purge)
        self.empty_btn = QPushButton("清空回收站")
        self.empty_btn.setObjectName("Danger")
        self.empty_btn.clicked.connect(self._empty)
        row.addWidget(self.restore_btn)
        row.addWidget(self.purge_btn)
        row.addWidget(self.empty_btn)
        row.addStretch(1)
        self.flash = FlashLabel()
        row.addWidget(self.flash)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        root.addLayout(row)

        self.refresh()
        self._set_buttons_enabled()

    def refresh(self) -> None:
        entries = self.store.get_trash()
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(entries))
            for row, e in enumerate(entries):
                items = [
                    QTableWidgetItem(e.sop.name or "（未命名）"),
                    QTableWidgetItem("、".join(e.sop.alarm_codes)),
                    QTableWidgetItem(str(len(e.sop.pages))),
                    QTableWidgetItem(e.deleted_at),
                ]
                items[0].setData(Qt.UserRole, e.sop.id)
                for col, it in enumerate(items):
                    if col in (2, 3):
                        it.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row, col, it)
        finally:
            self.table.setUpdatesEnabled(True)
        self._set_buttons_enabled()

    def _selected_id(self) -> str | None:
        sel = self.table.selectionModel()
        rows = sel.selectedRows() if sel else []
        if not rows:
            return None
        it = self.table.item(rows[0].row(), 0)
        return it.data(Qt.UserRole) if it else None

    def _set_buttons_enabled(self) -> None:
        has = self._selected_id() is not None
        self.restore_btn.setEnabled(has)
        self.purge_btn.setEnabled(has)
        self.empty_btn.setEnabled(bool(self.store.trash))

    def _restore(self) -> None:
        sop_id = self._selected_id()
        if not sop_id:
            return
        sop = self.store.restore_sop(sop_id)
        if sop is None:
            self.refresh()
            return
        self.restored_any = True
        self.refresh()
        self.flash.flash(f"✔ 已恢复「{sop.name}」到 SOP 库。")

    def _purge(self) -> None:
        sop_id = self._selected_id()
        if not sop_id:
            return
        entry = next((e for e in self.store.trash if e.sop.id == sop_id), None)
        if entry and confirm(self, "彻底删除",
                             f"确定彻底删除「{entry.sop.name}」吗？\n\n"
                             "页面文件与版本记录将一并清除，不可恢复。"):
            self.store.purge_sop(sop_id)
            self.refresh()
            self.flash.flash("✔ 已彻底删除。")

    def _empty(self) -> None:
        if not self.store.trash:
            return
        if confirm(self, "清空回收站",
                   f"确定清空回收站中的 {len(self.store.trash)} 条记录吗？\n\n"
                   "全部页面文件与版本记录将一并清除，不可恢复。"):
            self.store.empty_trash()
            self.refresh()
            self.flash.flash("✔ 回收站已清空。")
