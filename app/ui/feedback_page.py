"""反馈记录页：查看产线人员的报错反馈，工程师跟进处理（待补充 → 已解决）。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
                               QHeaderView, QLabel, QPlainTextEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from app.store import STATUS_RESOLVED, STATUS_TEXT, Store
from .common import FlashLabel, confirm


class RemarkDialog(QDialog):
    def __init__(self, remark: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑备注")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("备注："))
        self.edit = QPlainTextEdit(remark)
        self.edit.setPlaceholderText("记录处理进展、对应的新SOP名称等…")
        self.edit.setFixedHeight(120)
        lay.addWidget(self.edit)
        bb = QDialogButtonBox()
        ok = bb.addButton("保存", QDialogButtonBox.AcceptRole)
        ok.setObjectName("Primary")
        bb.addButton("取消", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class FeedbackPage(QWidget):
    def __init__(self, store: Store, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("反馈记录")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        tip = QLabel("（产线人员在“快速查找”页找不到SOP时提交的记录）")
        tip.setObjectName("Muted")
        head.addWidget(tip)
        head.addStretch(1)
        self.flash = FlashLabel()
        head.addWidget(self.flash)
        root.addLayout(head)

        bar = QHBoxLayout()
        self.resolve_btn = QPushButton("✔ 标记已解决")
        self.resolve_btn.setObjectName("Primary")
        self.reopen_btn = QPushButton("↩ 恢复待补充")
        self.remark_btn = QPushButton("✎ 编辑备注")
        self.del_btn = QPushButton("🗑 删除记录")
        self.del_btn.setObjectName("Danger")
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部", "待补充", "已解决"])
        self.refresh_btn = QPushButton("⟳ 刷新")
        bar.addWidget(self.resolve_btn)
        bar.addWidget(self.reopen_btn)
        bar.addWidget(self.remark_btn)
        bar.addWidget(self.del_btn)
        bar.addStretch(1)
        bar.addWidget(self.count_label)
        bar.addWidget(QLabel("状态："))
        bar.addWidget(self.status_filter)
        bar.addWidget(self.refresh_btn)
        root.addLayout(bar)

        cols = ["反馈时间", "报警 / 故障内容", "状态", "备注", "解决时间"]
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        self.table.itemSelectionChanged.connect(self._set_buttons_enabled)
        root.addWidget(self.table, 1)

        self.empty_label = QLabel("暂无反馈记录。产线人员在首页搜索不到 SOP 时，"
                                  "可点击“反馈报错”提交，记录会显示在这里。")
        self.empty_label.setObjectName("Muted")
        self.empty_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.empty_label)

        self.resolve_btn.clicked.connect(lambda: self._set_status(True))
        self.reopen_btn.clicked.connect(lambda: self._set_status(False))
        self.remark_btn.clicked.connect(self._edit_remark)
        self.del_btn.clicked.connect(self._delete)
        self.refresh_btn.clicked.connect(self.refresh)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self._set_buttons_enabled()

    # ---------- 展示 ----------
    def set_store(self, store: Store) -> None:
        self.store = store
        self.refresh()

    def refresh(self) -> None:
        mode = self.status_filter.currentIndex()   # 0全部 1待补充 2已解决
        rows = [f for f in self.store.feedback]
        if mode == 1:
            rows = [f for f in rows if f.status != STATUS_RESOLVED]
        elif mode == 2:
            rows = [f for f in rows if f.status == STATUS_RESOLVED]
        # 按时间新→旧；同一秒内按记录产生顺序（后产生的在前）
        seq = list(enumerate(rows))
        seq.sort(key=lambda p: (p[1].created_at, p[0]), reverse=True)
        rows = [f for _i, f in seq]

        # 批量填充：几千条记录也只重绘一次
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(rows))
            pending = 0
            for row, f in enumerate(rows):
                status_color = QColor("#1e7f4f") if f.status == STATUS_RESOLVED else QColor("#b25e09")
                items = [
                    QTableWidgetItem(f.created_at),
                    QTableWidgetItem(f.query),
                    QTableWidgetItem(STATUS_TEXT.get(f.status, f.status)),
                    QTableWidgetItem(f.remark),
                    QTableWidgetItem(f.resolved_at),
                ]
                items[0].setData(Qt.UserRole, f.id)
                items[2].setForeground(status_color)
                f2 = items[2].font()
                f2.setBold(True)
                items[2].setFont(f2)
                items[2].setTextAlignment(Qt.AlignCenter)
                for col, it in enumerate(items):
                    self.table.setItem(row, col, it)
                if f.status != STATUS_RESOLVED:
                    pending += 1
        finally:
            self.table.setUpdatesEnabled(True)
        self.count_label.setText(f"共 {len(rows)} 条，其中待补充 {pending} 条")
        self.empty_label.setVisible(len(rows) == 0)
        self._set_buttons_enabled()

    # ---------- 操作 ----------
    def _selected_id(self) -> str | None:
        sel = self.table.selectionModel()
        rows = sel.selectedRows() if sel else []
        if not rows:
            return None
        it = self.table.item(rows[0].row(), 0)
        return it.data(Qt.UserRole) if it else None

    def _set_buttons_enabled(self) -> None:
        has = self._selected_id() is not None
        for b in (self.resolve_btn, self.reopen_btn, self.remark_btn, self.del_btn):
            b.setEnabled(has)

    def _set_status(self, resolved: bool) -> None:
        fb_id = self._selected_id()
        if not fb_id:
            return
        self.store.set_feedback_status(fb_id, resolved)
        self.refresh()
        self.flash.flash("✔ 已标记为已解决。" if resolved else "↩ 已恢复为待补充。")

    def _edit_remark(self) -> None:
        fb_id = self._selected_id()
        if not fb_id:
            return
        fb = self.store.get_feedback(fb_id)
        if not fb:
            return
        dlg = RemarkDialog(fb.remark, self)
        if dlg.exec() == QDialog.Accepted:
            self.store.set_feedback_remark(fb_id, dlg.edit.toPlainText())
            self.refresh()
            self.flash.flash("✔ 备注已保存。")

    def _on_double_click(self, item) -> None:
        self._edit_remark()

    def _delete(self) -> None:
        fb_id = self._selected_id()
        if not fb_id:
            return
        fb = self.store.get_feedback(fb_id)
        if fb and confirm(self, "删除反馈记录", f"确定删除这条反馈记录吗？\n\n「{fb.query}」"):
            self.store.delete_feedback(fb_id)
            self.refresh()
            self.flash.flash("✔ 已删除记录。")
