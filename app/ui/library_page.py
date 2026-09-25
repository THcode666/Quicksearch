"""SOP 库页：工程师维护 SOP（新建 / 编辑 / 删除 / 排序 / 筛选）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from app import search as search_mod
from app.store import Store, natural_key
from .common import FlashLabel, confirm, elide
from .editor_dialog import EditorDialog

COLS = ["SOP 名称", "报警代码", "页数", "修改时间", "解决方式"]


class SortCombo(QComboBox):
    """排序下拉框（屏蔽滚轮误改）。"""

    def wheelEvent(self, e):
        e.ignore()


class LibraryPage(QWidget):
    open_sop = Signal(str)

    def __init__(self, store: Store, cfg, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.cfg = cfg
        self._order_desc = True

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("SOP 库")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.flash = FlashLabel()
        head.addWidget(self.flash)
        root.addLayout(head)

        # ---- 工具栏 ----
        bar = QHBoxLayout()
        self.new_btn = QPushButton("＋ 新建 SOP")
        self.new_btn.setObjectName("Primary")
        self.edit_btn = QPushButton("✎ 编辑")
        self.del_btn = QPushButton("🗑 删除")
        self.del_btn.setObjectName("Danger")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("筛选：名称/代码/解决方式…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setMinimumWidth(150)
        self.sort_combo = SortCombo()
        self.sort_combo.addItems(["按修改时间", "按名称"])
        self.order_btn = QPushButton("↓ 新→旧")
        self.order_btn.setToolTip("切换升序 / 降序")
        self.refresh_btn = QPushButton("⟳ 刷新")
        self.refresh_btn.setToolTip("重新从数据目录读取（多机共享时可见其他电脑的更新）")

        for w in (self.new_btn, self.edit_btn, self.del_btn):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(QLabel("排序："))
        bar.addWidget(self.sort_combo)
        bar.addWidget(self.order_btn)
        bar.addWidget(self.filter_edit)
        bar.addWidget(self.refresh_btn)
        root.addLayout(bar)

        # ---- 表格 ----
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
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
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        self.table.itemSelectionChanged.connect(self._set_buttons_enabled)
        root.addWidget(self.table, 1)

        self.empty_label = QLabel("SOP 库还是空的，点击左上角“＋ 新建 SOP”添加第一条 SOP。")
        self.empty_label.setObjectName("Muted")
        self.empty_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.empty_label)

        # ---- 信号 ----
        self.new_btn.clicked.connect(self._on_new)
        self.edit_btn.clicked.connect(self._on_edit)
        self.del_btn.clicked.connect(self._on_delete)
        self.refresh_btn.clicked.connect(self.refresh)
        self.filter_edit.textChanged.connect(self.refresh)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_mode_changed)
        self.order_btn.clicked.connect(self._toggle_order)
        self._update_order_btn()
        self._set_buttons_enabled()

    # ---------- 展示 ----------
    def set_store(self, store: Store) -> None:
        self.store = store
        self.refresh()

    def refresh(self) -> None:
        sops = list(self.store.sops)
        text = self.filter_edit.text().strip()
        if text:
            q = search_mod.normalize(text)
            sops = [s for s in sops
                    if all(t in search_mod.haystack(s) for t in q.split(" "))]
        if self.sort_combo.currentIndex() == 0:   # 按修改时间
            sops.sort(key=lambda s: (s.updated_at or s.created_at or ""),
                      reverse=self._order_desc)
        else:                                     # 按名称（自然排序）
            sops.sort(key=lambda s: natural_key(s.name), reverse=self._order_desc)
        self._fill(sops)

    def _update_order_btn(self) -> None:
        if self.sort_combo.currentIndex() == 0:
            self.order_btn.setText("↓ 新→旧" if self._order_desc else "↑ 旧→新")
        else:
            self.order_btn.setText("↓ Z→A" if self._order_desc else "↑ A→Z")

    def _toggle_order(self) -> None:
        self._order_desc = not self._order_desc
        self._update_order_btn()
        self.refresh()

    def _on_sort_mode_changed(self) -> None:
        self._update_order_btn()
        self.refresh()

    def _fill(self, sops) -> None:
        # 批量填充：先关掉逐行刷新，几千行也只重绘一次
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(sops))
            for row, sop in enumerate(sops):
                items = [
                    QTableWidgetItem(sop.name or "（未命名）"),
                    QTableWidgetItem("、".join(sop.alarm_codes)),
                    QTableWidgetItem(str(len(sop.pages))),
                    QTableWidgetItem(sop.updated_at or sop.created_at or ""),
                    QTableWidgetItem(elide(sop.solution, 80)),
                ]
                items[0].setData(Qt.UserRole, sop.id)
                for col, it in enumerate(items):
                    if col in (2, 3):
                        it.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row, col, it)
        finally:
            self.table.setUpdatesEnabled(True)
        self.empty_label.setVisible(len(sops) == 0)
        self._set_buttons_enabled()

    # ---------- 操作 ----------
    def _selected_id(self) -> str | None:
        sel_model = self.table.selectionModel()
        rows = sel_model.selectedRows() if sel_model else []
        if not rows:
            return None
        it = self.table.item(rows[0].row(), 0)
        return it.data(Qt.UserRole) if it else None

    def _set_buttons_enabled(self) -> None:
        has = self._selected_id() is not None
        self.edit_btn.setEnabled(has)
        self.del_btn.setEnabled(has)

    def _on_double_click(self, item) -> None:
        sop_id = self.table.item(item.row(), 0).data(Qt.UserRole)
        if sop_id:
            self.open_sop.emit(sop_id)

    def _on_new(self) -> None:
        dlg = EditorDialog(self.store, self.cfg, parent=self)
        if dlg.exec() and dlg.saved_id:
            self.refresh()
            self.flash.flash("✔ SOP 已保存。")

    def _on_edit(self) -> None:
        sop_id = self._selected_id()
        if not sop_id:
            return
        sop = self.store.get_sop(sop_id)
        if not sop:
            return
        dlg = EditorDialog(self.store, self.cfg, sop=sop, parent=self)
        if dlg.exec() and dlg.saved_id:
            self.refresh()
            self.flash.flash("✔ SOP 已更新。")

    def _on_delete(self) -> None:
        sop_id = self._selected_id()
        if not sop_id:
            return
        sop = self.store.get_sop(sop_id)
        if not sop:
            return
        if confirm(self, "删除 SOP",
                   f"确定删除「{sop.name}」吗？\n\n该 SOP 的所有页面文件将一并删除，且不可恢复。"):
            self.store.delete_sop(sop_id)
            self.refresh()
            self.flash.flash("✔ 已删除。")
