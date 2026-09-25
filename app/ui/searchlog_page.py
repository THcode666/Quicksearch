"""搜索记录页：自动记录每次搜索（日期、时间、所搜报警代码、是否找到SOP、报错截图）。

- 已搜到 → 绿色"已搜到"
- 缺少 SOP → 橙红"⚠ 缺少对应SOP"（三角警示符），工程师据此补 SOP
- 产线人员提交的机台报错截图显示为"📎 有截图"，双击行或点"查看截图"放大查看，
  查看窗里可"另存为…"把截图保存到指定位置
记录超过上限（10000 条）时自动丢弃最旧的。
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QPushButton, QScrollArea,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from app.store import Store
from .common import FlashLabel, confirm, info, warn

COLS = ["日期", "时间", "所搜报警代码", "结果", "截图"]


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
        self.shot_btn = QPushButton("🖼 查看截图")
        self.shot_btn.setToolTip("查看该记录提交的机台报错截图")
        self.del_btn = QPushButton("🗑 删除选中")
        self.del_btn.setObjectName("Danger")
        self.clear_btn = QPushButton("清空记录")
        self.clear_btn.setObjectName("Danger")
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["全部", "仅缺少SOP", "有截图"])
        self.refresh_btn = QPushButton("⟳ 刷新")
        self.refresh_btn.setToolTip("多机共享时，查看其他电脑产生的搜索记录")
        bar.addWidget(self.shot_btn)
        bar.addWidget(self.del_btn)
        bar.addWidget(self.clear_btn)
        bar.addStretch(1)
        bar.addWidget(self.count_label)
        bar.addWidget(QLabel("筛选："))
        bar.addWidget(self.filter_combo)
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
        self.filter_combo.currentIndexChanged.connect(self.refresh)
        self._set_buttons_enabled()

    # ---------- 展示 ----------
    def set_store(self, store: Store) -> None:
        self.store = store
        self.refresh()

    def refresh(self) -> None:
        mode = self.filter_combo.currentIndex()   # 0全部 1仅缺少SOP 2有截图
        rows = list(self.store.search_logs)
        if mode == 1:
            rows = [r for r in rows if not r.found]
        elif mode == 2:
            rows = [r for r in rows if r.shot]
        # 按时间新→旧；同一秒内按记录产生顺序（后产生的在前）
        seq = list(enumerate(rows))
        seq.sort(key=lambda p: (p[1].time, p[0]), reverse=True)
        rows = [r for _i, r in seq]

        # 批量填充：记录很多时也只重绘一次
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(rows))
            missing = 0
            for row, r in enumerate(rows):
                if not r.found:
                    missing += 1
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
        self.count_label.setText(f"共 {len(rows)} 条，其中缺少SOP {missing} 条")
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

    def _selected_record(self):
        log_id = self._selected_id()
        if not log_id:
            return None
        return next((r for r in self.store.search_logs if r.id == log_id), None)

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
        if not self.store.search_logs:
            return
        if confirm(self, "清空搜索记录",
                   f"确定清空全部 {len(self.store.search_logs)} 条搜索记录吗？\n\n"
                   "已提交的报错截图也会一并删除，此操作不可恢复。"):
            self.store.clear_search_logs()
            self.refresh()
            self.flash.flash("✔ 已清空搜索记录。")
