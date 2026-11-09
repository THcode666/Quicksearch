"""搜索记录页：自动记录每次搜索（日期、时间、所搜报警代码、是否找到SOP、报错截图）。

- 已搜到 → 绿色"已搜到"；缺少 SOP → 橙红"⚠ 缺少对应SOP"，工程师据此补 SOP
- 产线人员提交的机台报错截图显示为"📎 有截图"，双击行或点"查看截图"放大查看、可另存
- 存储为追加式日志（多机并发安全），页面只显示最近记录，可一键导出 Excel（CSV）
"""
from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from app.store import Store
from .common import FlashLabel, confirm, info, warn

COLS = ["日期", "时间", "所搜报警代码", "结果", "截图"]
SOURCE_READ = 2000   # 每次刷新读取的最近记录条数（筛选在这个范围内进行）


def _safe_filename(text: str, limit: int = 40) -> str:
    """把报警内容整理成合法文件名片段（去掉 Windows 非法字符）。"""
    text = re.sub(r'[\\/:*?"<>|\r\n\t]', " ", str(text)).strip()
    return text[:limit] or "截图"


class ShotViewDialog(QDialog):
    """放大查看一条搜索记录的机台报错截图，可另存到指定位置。"""

    def __init__(self, query: str, shot_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("机台报错截图")
        self.resize(720, 560)
        self.shot_path = Path(shot_path)
        self.query = query
        self._img = QImage(str(self.shot_path))

        lay = QVBoxLayout(self)
        lab = QLabel(f"报警内容：{query}")
        lab.setObjectName("CardTitle")
        lab.setWordWrap(True)
        lay.addWidget(lab)
        area = QScrollArea()
        area.setWidgetResizable(True)
        canvas = QLabel()
        canvas.setAlignment(Qt.AlignCenter)
        if self._img.isNull():
            canvas.setText("截图加载失败")
        else:
            canvas.setPixmap(QPixmap.fromImage(self._img))
        area.setWidget(canvas)
        lay.addWidget(area, 1)
        row = QHBoxLayout()
        save_btn = QPushButton("💾 另存为…")
        save_btn.setToolTip("把这张截图保存到指定的文件夹（可选 PNG / JPG 格式）")
        save_btn.setEnabled(not self._img.isNull())
        save_btn.clicked.connect(self._save_as)
        row.addWidget(save_btn)
        row.addStretch(1)
        tip = QLabel("默认位于数据目录 shots 文件夹内。")
        tip.setObjectName("Muted")
        row.addWidget(tip)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def _save_as(self) -> None:
        suggest = f"报错截图_{_safe_filename(self.query, 30)}.png"
        desktop = Path.home() / "Desktop"
        start_dir = str(desktop / suggest) if desktop.exists() else suggest
        path, _selected = QFileDialog.getSaveFileName(
            self, "另存截图", start_dir,
            "PNG 图片 (*.png);;JPEG 图片 (*.jpg);;BMP 图片 (*.bmp)")
        if not path:
            return
        if self._save_to(Path(path)):
            info(self, "已保存", f"截图已保存到：\n{path}")

    def _save_to(self, dest: Path) -> bool:
        """把截图按 dest 的扩展名写出；成功返回 True。"""
        if self._img.isNull():
            warn(self, "提示", "截图未能加载，无法保存。")
            return False
        if not dest.suffix:
            dest = dest.with_suffix(".png")
        if not self._img.save(str(dest)):
            warn(self, "保存失败", f"无法写入：\n{dest}\n请检查该位置是否可写。")
            return False
        return True


class SearchLogPage(QWidget):
    MAX_RENDER = Store.MAX_RENDER_ROWS   # 一次最多渲染的行数，记录再多也不卡

    def __init__(self, store: Store, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("搜索记录")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        tip = QLabel("（自动记录产线人员的每一次搜索，缺SOP的用 ⚠ 标出，方便工程师补充）")
        tip.setObjectName("Muted")
        head.addWidget(tip)
        head.addStretch(1)
        self.flash = FlashLabel()
        head.addWidget(self.flash)
        root.addLayout(head)

        bar = QHBoxLayout()
        self.export_btn = QPushButton("📥 导出Excel…")
        self.export_btn.setToolTip("把全部搜索记录（含归档）导出为 Excel 可直接打开的 CSV 文件")
        self.export_btn.clicked.connect(self._export_csv)
        self.shot_btn = QPushButton("🖼 查看截图")
        self.shot_btn.setToolTip("查看该记录提交的机台报错截图")
        self.del_btn = QPushButton("🗑 删除选中")
        self.del_btn.setObjectName("Danger")
        self.clear_btn = QPushButton("清空记录")
        self.clear_btn.setObjectName("Danger")
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("筛选所搜内容…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setMinimumWidth(150)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部", "仅缺少SOP", "有截图"])
        self.refresh_btn = QPushButton("⟳ 刷新")
        self.refresh_btn.setToolTip("多机共享时，查看其他电脑产生的搜索记录")
        bar.addWidget(self.export_btn)
        bar.addWidget(self.shot_btn)
        bar.addWidget(self.del_btn)
        bar.addWidget(self.clear_btn)
        bar.addStretch(1)
        bar.addWidget(self.count_label)
        bar.addWidget(self.filter_edit)
        bar.addWidget(QLabel("筛选："))
        bar.addWidget(self.status_filter)
        bar.addWidget(self.refresh_btn)
        root.addLayout(bar)

        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        self.table.itemSelectionChanged.connect(self._set_buttons_enabled)
        root.addWidget(self.table, 1)

        self.empty_label = QLabel("暂无搜索记录。产线人员在首页点击“搜索”后会自动记录在这里。")
        self.empty_label.setObjectName("Muted")
        self.empty_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.empty_label)

        self.shot_btn.clicked.connect(self._view_shot)
        self.del_btn.clicked.connect(self._delete_selected)
        self.clear_btn.clicked.connect(self._clear_all)
        self.refresh_btn.clicked.connect(self.refresh)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self.filter_edit.textChanged.connect(self.refresh)
        self._set_buttons_enabled()

    # ---------- 展示 ----------
    def set_store(self, store: Store) -> None:
        self.store = store
        self.refresh()

    def refresh(self) -> None:
        mode = self.status_filter.currentIndex()   # 0全部 1仅缺少SOP 2有截图
        # 只读取日志尾部（最近 SOURCE_READ 条，新→旧）：记录总量再多也毫秒级
        rows = self.store.read_search_logs(limit=SOURCE_READ)
        text = self.filter_edit.text().strip().casefold()
        if text:
            rows = [r for r in rows if text in r.query.casefold()]
        if mode == 1:
            rows = [r for r in rows if not r.found]
        elif mode == 2:
            rows = [r for r in rows if r.shot]

        # 只渲染最近 MAX_RENDER 条：表格行数恒定，弱配电脑不卡
        truncated = len(rows) > self.MAX_RENDER
        shown = rows[:self.MAX_RENDER]

        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(shown))
            for row, r in enumerate(shown):
                date, _, time_part = r.time.partition(" ")
                items = [
                    QTableWidgetItem(date),
                    QTableWidgetItem(time_part),
                    QTableWidgetItem(r.query),
                    QTableWidgetItem("已搜到" if r.found else "⚠ 缺少对应SOP"),
                    QTableWidgetItem("📎 有截图" if r.shot else "—"),
                ]
                items[0].setData(Qt.UserRole, r.id)
                for col, it in enumerate(items):
                    if col != 2:
                        it.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row, col, it)
                if r.found:
                    items[3].setForeground(QColor("#1e7f4f"))
                else:
                    items[3].setForeground(QColor("#d13438"))
                    f = items[3].font()
                    f.setBold(True)
                    items[3].setFont(f)
                if r.shot:
                    items[4].setForeground(QColor("#2f6fed"))
        finally:
            self.table.setUpdatesEnabled(True)
        missing = sum(1 for r in rows if not r.found)
        label = (f"日志共 {self.store.count_search_logs()} 条 | "
                 f"显示最近 {len(shown)} 条，其中缺少SOP {missing} 条")
        if truncated:
            label += "（更早记录请点“导出Excel”查看）"
        self.count_label.setText(label)
        self.empty_label.setVisible(len(shown) == 0)
        self._set_buttons_enabled()

    def _export_csv(self) -> None:
        """把全部搜索记录（含归档）导出为 Excel 可直接打开的 CSV。"""
        recs = self.store.read_all_search_logs()
        if not recs:
            info(self, "提示", "还没有任何搜索记录可导出。")
            return
        default_name = f"搜索记录导出_{datetime.now():%Y%m%d_%H%M%S}.csv"
        desktop = Path.home() / "Desktop"
        start_dir = str(desktop / default_name) if desktop.exists() else default_name
        path, _ = QFileDialog.getSaveFileName(
            self, "导出搜索记录（Excel 可直接打开）", start_dir,
            "CSV 文件 (*.csv);;所有文件 (*.*)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["日期", "时间", "所搜报警代码", "结果", "报错截图"])
                for r in recs:   # 旧→新，便于按时间阅读
                    d, _, t = r.time.partition(" ")
                    w.writerow([d, t, r.query,
                                "已搜到" if r.found else "缺少对应SOP",
                                "有截图" if r.shot else "无"])
        except OSError as e:
            warn(self, "导出失败",
                 f"写入失败：{e}\n\n若目标文件正被 Excel 打开，请先关闭它，"
                 "或另选一个保存位置。")
            return
        info(self, "导出完成",
             f"已导出 {len(recs)} 条搜索记录到：\n{path}\n\n"
             "用 Excel/WPS 打开即可查看与统计（含归档文件中的全部记录）。")

    # ---------- 操作 ----------
    def _selected_id(self) -> str | None:
        sel = self.table.selectionModel()
        rows = sel.selectedRows() if sel else []
        if not rows:
            return None
        it = self.table.item(rows[0].row(), 0)
        return it.data(Qt.UserRole) if it else None

    def _selected_record(self):
        """从最近读取的记录里按 id 找当前选中行对应的记录。"""
        log_id = self._selected_id()
        if not log_id:
            return None
        for r in self.store.read_search_logs(limit=SOURCE_READ):
            if r.id == log_id:
                return r
        return None

    def _set_buttons_enabled(self) -> None:
        rec = self._selected_record()
        self.del_btn.setEnabled(rec is not None)
        self.shot_btn.setEnabled(bool(rec and rec.shot))

    def _view_shot(self) -> None:
        rec = self._selected_record()
        if not rec or not rec.shot:
            return
        path = self.store.search_log_shot_path(rec)
        if path is None:
            warn(self, "提示", "截图文件不存在（可能已被移动或删除）。")
            return
        ShotViewDialog(rec.query, path, self).exec()

    def _on_double_click(self, item) -> None:
        rec = self._selected_record()
        if rec and rec.shot:
            self._view_shot()
        elif rec:
            info(self, "提示", "该记录没有提交截图。")

    def _delete_selected(self) -> None:
        log_id = self._selected_id()
        if not log_id:
            return
        self.store.delete_search_log(log_id)
        self.refresh()
        self.flash.flash("✔ 已删除该条记录。")

    def _clear_all(self) -> None:
        total = self.store.count_search_logs()
        if not total:
            return
        if confirm(self, "清空搜索记录",
                   f"确定清空全部 {total} 条搜索记录吗？\n\n"
                   "已提交的报错截图也会一并删除，此操作不可恢复。"):
            self.store.clear_search_logs()
            self.refresh()
            self.flash.flash("✔ 已清空搜索记录。")
