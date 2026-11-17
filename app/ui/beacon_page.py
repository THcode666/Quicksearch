"""烽火台页：线上遇到没见过的问题，第一时间记录异常汇报。

- 线上人员：点"🔥 新建异常汇报"记录问题（日期自动今天，可贴多张截图）；
- 工程师：历史列表可查看、编辑、生成/打开 HTML 报告、删除误记录。
- 列表只渲染最近 MAX_RENDER 条，配合筛选定位，记录再多也不卡。
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from app.beacons import BeaconStore
from .common import FlashLabel, confirm, elide, info, warn


class BeaconPage(QWidget):
    COLS = ["日期", "机台", "Recipe", "问题描述", "截图"]

    def __init__(self, bstore: BeaconStore, parent: QWidget | None = None):
        super().__init__(parent)
        self.bstore = bstore

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("烽火台")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        tip = QLabel("（线上遇到没见过的问题，第一时间记下来；工程师跟进处理）")
        tip.setObjectName("Muted")
        head.addWidget(tip)
        head.addStretch(1)
        self.flash = FlashLabel()
        head.addWidget(self.flash)
        root.addLayout(head)

        bar = QHBoxLayout()
        self.new_btn = QPushButton("🔥 新建异常汇报")
        self.new_btn.setObjectName("Primary")
        self.edit_btn = QPushButton("✎ 查看 / 编辑")
        self.del_btn = QPushButton("🗑 删除")
        self.del_btn.setObjectName("Danger")
        self.report_btn = QPushButton("📄 生成 / 打开报告")
        self.report_btn.setToolTip("自动生成图文报告（HTML），浏览器打开即可查看、打印或发送")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("筛选：机台 / Recipe / 针卡 / 问题描述…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setMinimumWidth(180)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        self.refresh_btn = QPushButton("⟳ 刷新")
        self.refresh_btn.setToolTip("多机共享时，查看其他电脑记录的异常")
        bar.addWidget(self.new_btn)
        bar.addWidget(self.edit_btn)
        bar.addWidget(self.del_btn)
        bar.addWidget(self.report_btn)
        bar.addStretch(1)
        bar.addWidget(self.count_label)
        bar.addWidget(self.filter_edit)
        bar.addWidget(self.refresh_btn)
        root.addLayout(bar)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.itemDoubleClicked.connect(lambda _it: self._on_edit())
        self.table.itemSelectionChanged.connect(self._set_buttons_enabled)
        root.addWidget(self.table, 1)

        self.empty_label = QLabel("暂无异常记录。线上遇到没见过的问题，"
                                  "点“🔥 新建异常汇报”第一时间记下来。")
        self.empty_label.setObjectName("Muted")
        self.empty_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.empty_label)

        self.new_btn.clicked.connect(self._on_new)
        self.edit_btn.clicked.connect(self._on_edit)
        self.del_btn.clicked.connect(self._on_delete)
        self.report_btn.clicked.connect(self._on_report)
        self.refresh_btn.clicked.connect(self.refresh)
        self.filter_edit.textChanged.connect(self.refresh)
        self._set_buttons_enabled()

    # ---------- 对外 ----------
    def set_store(self, bstore: BeaconStore) -> None:
        self.bstore = bstore
        self.refresh()

    def refresh(self) -> None:
        try:
            self.bstore.reload()
        except OSError:
            pass
        rows = self.bstore.get_all()
        kw = self.filter_edit.text().strip().casefold()
        if kw:
            rows = [b for b in rows
                    if kw in " ".join([b.machine, b.recipe, b.test_od,
                                       b.probe_card, b.probe_card_len,
                                       b.description, b.date]).casefold()]
        truncated = len(rows) > self.bstore.MAX_RENDER_ROWS
        shown = rows[:self.bstore.MAX_RENDER_ROWS]

        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(shown))
            for row, b in enumerate(shown):
                items = [
                    QTableWidgetItem(b.date),
                    QTableWidgetItem(b.machine),
                    QTableWidgetItem(b.recipe),
                    QTableWidgetItem(elide(b.description, 90) or "（未填写描述）"),
                    QTableWidgetItem(str(len(b.shots))),
                ]
                items[0].setData(Qt.UserRole, b.id)
                for col, it in enumerate(items):
                    if col == 4:
                        it.setTextAlignment(int(Qt.AlignCenter))
                    self.table.setItem(row, col, it)
                if not b.description:
                    items[3].setForeground(QColor("#9aa7ba"))
        finally:
            self.table.setUpdatesEnabled(True)
        label = f"共 {len(rows)} 条异常记录"
        if truncated:
            label += f"（显示最近 {self.bstore.MAX_RENDER_ROWS} 条，可用筛选缩小范围）"
        self.count_label.setText(label)
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

    def _selected_beacon(self):
        bid = self._selected_id()
        return self.bstore.get_beacon(bid) if bid else None

    def _set_buttons_enabled(self) -> None:
        has = self._selected_id() is not None
        self.edit_btn.setEnabled(has)
        self.del_btn.setEnabled(has)
        self.report_btn.setEnabled(has)

    def _open_dialog(self, beacon=None) -> bool:
        from .beacon_dialog import BeaconDialog
        dlg = BeaconDialog(self.bstore, beacon, self)
        dlg.exec()
        if dlg.saved_id:
            self.refresh()
            return True
        return False

    def _on_new(self) -> None:
        if self._open_dialog():
            self.flash.flash("✔ 异常汇报已保存，报告已自动生成。")

    def _on_edit(self) -> None:
        beacon = self._selected_beacon()
        if not beacon:
            return
        if self._open_dialog(beacon):
            self.flash.flash("✔ 异常汇报已更新，报告已重新生成。")

    def _on_delete(self) -> None:
        beacon = self._selected_beacon()
        if not beacon:
            return
        if confirm(self, "删除异常记录",
                   f"确定删除 {beacon.date} 的这条异常记录吗？\n\n"
                   "其截图与生成的报告将一并删除，不可恢复。"):
            self.bstore.delete_beacon(beacon.id)
            self.refresh()
            self.flash.flash("✔ 已删除。")

    def _on_report(self) -> None:
        beacon = self._selected_beacon()
        if not beacon:
            return
        from app.reportgen import generate_report
        shot_paths = [self.bstore.shot_path(beacon, i)
                      for i in range(len(beacon.shots))]
        report = generate_report(beacon, shot_paths,
                                 self.bstore.beacon_dir(beacon.id) / "report.html")
        try:
            os.startfile(str(report))   # 用默认浏览器打开（可打印成PDF/转发）
        except Exception as e:
            warn(self, "打开失败",
                 f"报告已生成但无法自动打开：\n{report}\n\n{e}\n"
                 "可手动用浏览器打开该文件。")
