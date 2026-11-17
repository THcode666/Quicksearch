"""烽火台 · 新建/编辑异常汇报对话框。

- 日期自动填电脑当前日期（可改）；
- 机台 / Recipe / 测试OD / 针卡 / 针卡长度 选填；
- 问题描述 + 多张异常截图（Ctrl+V 粘贴或选择图片文件）；
- 保存时自动生成 HTML 报告（截图内嵌，可直接发送/打印）。
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QDateEdit, QDialog, QDialogButtonBox,
                               QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)

from app.beacons import Beacon, BeaconStore, new_id
from app.reportgen import generate_report
from .common import confirm, info, warn


class BeaconDialog(QDialog):
    def __init__(self, bstore: BeaconStore, beacon: Beacon | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.bstore = bstore
        self.beacon = beacon
        self.saved_id: str | None = None
        self.setWindowTitle("编辑异常汇报" if beacon else "新建异常汇报 — 烽火台")
        self.setMinimumSize(720, 620)

        # 暂存区：编辑期间截图先放临时目录，保存时才拷进数据目录
        self._tmpdir = Path(tempfile.mkdtemp(prefix="qs_beacon_"))
        self._shots: list[Path] = []          # 各截图的当前来源路径
        if beacon:
            self._shots = [self.bstore.shot_path(beacon, i)
                           for i in range(len(beacon.shots))]

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ---- 第一行：日期（默认电脑当前日期） ----
        row0 = QHBoxLayout()
        row0.addWidget(QLabel("日期（年月日）："))
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        row0.addWidget(self.date_edit)
        row0.addStretch(1)
        root.addLayout(row0)

        # ---- 选填信息（两列） ----
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.addWidget(QLabel("机台（选填）："), 0, 0)
        self.machine_edit = QLineEdit()
        grid.addWidget(self.machine_edit, 0, 1)
        grid.addWidget(QLabel("Recipe（选填）："), 0, 2)
        self.recipe_edit = QLineEdit()
        grid.addWidget(self.recipe_edit, 0, 3)
        grid.addWidget(QLabel("测试OD（选填）："), 1, 0)
        self.test_od_edit = QLineEdit()
        grid.addWidget(self.test_od_edit, 1, 1)
        grid.addWidget(QLabel("针卡（选填）："), 1, 2)
        self.probe_card_edit = QLineEdit()
        grid.addWidget(self.probe_card_edit, 1, 3)
        grid.addWidget(QLabel("针卡长度（选填）："), 2, 0)
        self.probe_len_edit = QLineEdit()
        grid.addWidget(self.probe_len_edit, 2, 1)
        root.addLayout(grid)

        # ---- 问题描述 ----
        root.addWidget(QLabel("问题描述 / 现象（建议把没见过的问题第一时间记下来）："))
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setPlaceholderText("例如：Wafer end 后 E4303 报警复现，重启后消失，"
                                          "换备用针卡后未再出现……")
        self.desc_edit.setFixedHeight(110)
        root.addWidget(self.desc_edit)

        # ---- 异常截图 ----
        root.addWidget(QLabel("异常截图（可放多张）："))
        mid = QHBoxLayout()
        self.shot_list = QListWidget()
        self.shot_list.setFixedWidth(280)
        self.shot_list.currentRowChanged.connect(self._show_preview)
        mid.addWidget(self.shot_list)
        right = QVBoxLayout()
        self.preview = QLabel("选择左侧截图可预览")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(300, 200)
        self.preview.setStyleSheet(
            "background:#f4f6fa; border:1px solid #d9e0ea; border-radius:10px; color:#8a97ac;")
        right.addWidget(self.preview, 1)
        btns = QHBoxLayout()
        paste_btn = QPushButton("📋 粘贴截图 (Ctrl+V)")
        paste_btn.clicked.connect(self._paste_shot)
        file_btn = QPushButton("🖼 选择图片…")
        file_btn.clicked.connect(self._pick_images)
        rm_btn = QPushButton("移除")
        rm_btn.clicked.connect(self._remove_shot)
        for b in (paste_btn, file_btn, rm_btn):
            btns.addWidget(b)
        right.addLayout(btns)
        mid.addLayout(right, 1)
        root.addLayout(mid, 1)

        # ---- 底部 ----
        foot = QHBoxLayout()
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#c62828;")
        foot.addWidget(self.error_label)
        foot.addStretch(1)
        from PySide6.QtWidgets import QDialogButtonBox
        bb = QDialogButtonBox()
        save_btn = bb.addButton("保存并生成报告", QDialogButtonBox.AcceptRole)
        save_btn.setObjectName("Primary")
        bb.addButton("取消", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        foot.addWidget(bb)
        root.addLayout(foot)

        from PySide6.QtGui import QKeySequence, QShortcut
        sc = QShortcut(QKeySequence("Ctrl+V"), self)
        sc.activated.connect(self._paste_shot)

        if beacon:
            parsed = QDate.fromString(beacon.date, "yyyy-MM-dd")
            self.date_edit.setDate(parsed if parsed.isValid() else QDate.currentDate())
            self.machine_edit.setText(beacon.machine)
            self.recipe_edit.setText(beacon.recipe)
            self.test_od_edit.setText(beacon.test_od)
            self.probe_card_edit.setText(beacon.probe_card)
            self.probe_len_edit.setText(beacon.probe_card_len)
            self.desc_edit.setPlainText(beacon.description)
            self._refresh_shots()

        self.finished.connect(lambda *_: shutil.rmtree(self._tmpdir, ignore_errors=True))

    # ---------- 截图 ----------
    def _refresh_shots(self) -> None:
        self.shot_list.clear()
        for i, p in enumerate(self._shots, 1):
            it = QListWidgetItem(f"截图 {i} — {p.name}")
            self.shot_list.addItem(it)
        if self._shots:
            self.shot_list.setCurrentRow(len(self._shots) - 1)

    def _show_preview(self, row: int) -> None:
        if not (0 <= row < len(self._shots)):
            return
        img = QImage(str(self._shots[row]))
        if img.isNull():
            self.preview.setText("图片无法预览")
            return
        pm = QPixmap.fromImage(img).scaled(
            self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(pm)
        self.preview.setText("")

    def _add_shot_object(self, img) -> None:
        fp = self._tmpdir / f"paste_{new_id()}.png"
        if not img.save(str(fp)):
            warn(self, "提示", "截图保存失败，请重试。")
            return
        self._shots.append(fp)
        self._refresh_shots()
        self.shot_list.setCurrentRow(len(self._shots) - 1)

    def _paste_shot(self) -> None:
        from PySide6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        md = cb.mimeData()
        if md.hasImage():
            img = cb.image()
            if not img.isNull():
                self._add_shot_object(img)
                return
        if md.hasUrls():
            exts = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
            for url in md.urls():
                p = Path(url.toLocalFile())
                if p.suffix.lower() in exts and p.exists():
                    self._shots.append(p)
                    self._refresh_shots()
                    self.shot_list.setCurrentRow(len(self._shots) - 1)
                    return
            info(self, "提示", "剪贴板里复制的文件不是图片。")
            return
        info(self, "提示", "剪贴板里没有图片。请先截图，或在资源管理器里复制图片文件。")

    def _pick_images(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择异常截图（可多选）", "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*.*)")
        if not files:
            return
        for f in sorted(files):
            self._shots.append(Path(f))
        self._refresh_shots()
        self.shot_list.setCurrentRow(len(self._shots) - 1)

    def _remove_shot(self) -> None:
        row = self.shot_list.currentRow()
        if 0 <= row < len(self._shots):
            del self._shots[row]
            self._refresh_shots()

    # ---------- 保存 ----------
    def _save(self) -> None:
        qd = self.date_edit.date()
        if self.beacon is None:
            self.beacon = Beacon(id=new_id())
        b = self.beacon
        b.date = qd.toString("yyyy-MM-dd")
        b.machine = self.machine_edit.text().strip()
        b.recipe = self.recipe_edit.text().strip()
        b.test_od = self.test_od_edit.text().strip()
        b.probe_card = self.probe_card_edit.text().strip()
        b.probe_card_len = self.probe_len_edit.text().strip()
        b.description = self.desc_edit.toPlainText().strip()

        if not b.description and not self._shots:
            if not confirm(self, "内容为空",
                           "问题描述和截图都是空的，确定这样保存吗？\n（建议至少简单记录一下现象）"):
                return

        # 校验来源文件都存在
        missing = [str(p) for p in self._shots if not Path(p).exists()]
        if missing:
            warn(self, "提示", "部分截图文件不存在，请移除后重试。")
            return

        try:
            self.bstore.upsert_beacon(b, self._shots)
        except OSError as e:
            warn(self, "保存失败", f"写入失败：{e}\n若使用共享目录请检查网络与权限。")
            return

        # 自动生成 HTML 报告
        try:
            shot_paths = [self.bstore.shot_path(b, i) for i in range(len(b.shots))]
            generate_report(b, shot_paths, self.bstore.beacon_dir(b.id) / "report.html")
        except Exception:
            pass   # 报告生成失败不影响保存，可稍后重新生成
        self.saved_id = b.id
        self.accept()
