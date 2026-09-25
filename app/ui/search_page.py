"""首页：快速查找。

- 输入报警代码/关键词，点“🔍 搜索”（或回车）执行搜索：
  唯一命中直接打开；多个命中弹结果列表选择；
  未找到 → 弹窗提示“此报错暂无对应SOP”，引导产线人员粘贴机台报错截图，
  截图随搜索记录一起保存，工程师在“搜索记录”里可查看。
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)

from app import search
from app.store import Store
from .common import FlashLabel, confirm, elide, info, warn

IMAGE_FILE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


class ShotSubmitDialog(QDialog):
    """未找到 SOP 时弹出：引导用户粘贴机台报错截图（Ctrl+V 或按钮）。"""

    def __init__(self, store: Store, log_id: str, query: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.log_id = log_id
        self._img: QImage | None = None
        self._file: Path | None = None

        self.setWindowTitle("提交机台报错截图")
        self.setMinimumWidth(520)

        tip = QLabel(f"⚠ 此报错暂无对应 SOP：\n「{elide(query, 80)}」\n\n"
                     "请提交机台报错截图，工程师会根据截图尽快补充对应 SOP。")
        tip.setObjectName("NotFoundHint")
        tip.setWordWrap(True)
        tip.setAlignment(Qt.AlignLeft)

        self.preview = QLabel("按 Ctrl+V 粘贴截图，\n或点下方“选择照片”从文件夹里选一张\n"
                              "（支持 PrintScreen/聊天工具截图、手机照片等图片文件）")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(420, 240)
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet(
            "background:#f7f9fc; border:2px dashed #c9d6ee; border-radius:10px; color:#8a97ac;")

        paste_btn = QPushButton("📋 粘贴截图 (Ctrl+V)")
        paste_btn.clicked.connect(self._paste)
        file_btn = QPushButton("📁 选择照片…")
        file_btn.setToolTip("从电脑文件夹里选择一张机台报错照片")
        file_btn.clicked.connect(self._pick_file)

        btns = QDialogButtonBox()
        ok = btns.addButton("提交", QDialogButtonBox.AcceptRole)
        ok.setObjectName("Primary")
        skip = btns.addButton("暂不提交截图", QDialogButtonBox.AcceptRole)
        btns.addButton("关闭", QDialogButtonBox.RejectRole)
        btns.accepted.connect(self._submit)          # 提交 / 暂不提交 都走这里
        btns.rejected.connect(self.reject)
        self._skip_btn = skip

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(tip)
        lay.addWidget(self.preview, 1)
        row = QHBoxLayout()
        row.addWidget(paste_btn)
        row.addWidget(file_btn)
        row.addStretch(1)
        row.addWidget(btns)
        lay.addLayout(row)

        sc = QShortcut(QKeySequence("Ctrl+V"), self)
        sc.activated.connect(self._paste)

    # ---------- 粘贴 ----------
    def _paste(self) -> None:
        from PySide6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        md = cb.mimeData()
        if md.hasUrls():
            for url in md.urls():
                p = Path(url.toLocalFile())
                if p.suffix.lower() in IMAGE_FILE_EXTS and p.exists():
                    img = QImage(str(p))
                    if not img.isNull():
                        self._set_image(img, p)
                        return
            info(self, "提示", "剪贴板里复制的文件不是图片。\n请复制 png/jpg 图片文件，或直接截图后再按 Ctrl+V。")
            return
        if md.hasImage():
            img = cb.image()
            if not img.isNull():
                self._set_image(img, None)
                return
        info(self, "提示", "剪贴板里没有图片。\n请先截图（PrintScreen 或聊天工具截图），"
                           "或在资源管理器里复制图片文件后再按 Ctrl+V。")

    def _pick_file(self) -> None:
        """从文件夹选择一张报错照片（不依赖剪贴板）。"""
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "选择机台报错照片", "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*.*)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            warn(self, "提示", f"无法读取该图片文件：\n{path}")
            return
        self._set_image(img, Path(path))

    def _set_image(self, img: QImage, src_file: Path | None) -> None:
        self._img = img
        self._file = src_file
        from PySide6.QtGui import QPixmap
        pm_scaled = img.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(QPixmap.fromImage(pm_scaled))
        self.preview.setText("")

    # ---------- 提交 ----------
    def _submit(self) -> None:
        if self.sender() is self._skip_btn:
            self.accept()   # 只保留自动记录，不提交图片
            return
        if self._img is None:
            if not confirm(self, "尚未粘贴截图",
                           "还没有粘贴截图。只保留本次记录、不提交图片吗？"):
                return
            self.accept()
            return
        tmpdir = Path(tempfile.mkdtemp(prefix="qs_shot_"))
        try:
            # 文件选择保留原扩展名；剪贴板截图统一存 PNG
            ext = (self._file.suffix.lower() if self._file else ".png") or ".png"
            tmp = tmpdir / f"{self.log_id}{ext}"
            if self._file is not None:
                shutil.copyfile(self._file, tmp)
            else:
                self._img.save(str(tmp))
            self.store.set_search_log_shot(self.log_id, tmp)
        except OSError as e:
            warn(self, "保存失败", f"截图保存失败：{e}\n若使用共享目录请检查网络与权限。")
            return
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        self.accept()


class FeedbackDialog(QDialog):
    """产线人员反馈：没搜到的报警 + 可选备注。"""

    def __init__(self, query: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("反馈报错 — SOP 缺失")
        self.setMinimumWidth(460)
        lab1 = QLabel("报警 / 故障内容（必填）：")
        self.query_edit = QLineEdit(query.strip())
        self.query_edit.setPlaceholderText("例如：E4303 module not found")
        lab2 = QLabel("备注（选填）：")
        self.remark_edit = QPlainTextEdit()
        self.remark_edit.setPlaceholderText("可以补充现象、机台号、处理经过等，方便工程师补充SOP")
        self.remark_edit.setFixedHeight(90)
        tip = QLabel("提交后工程师会在“反馈记录”里跟进并补充对应 SOP。")
        tip.setObjectName("Muted")

        btns = QDialogButtonBox()
        ok = btns.addButton("提交反馈", QDialogButtonBox.AcceptRole)
        btns.addButton("取消", QDialogButtonBox.RejectRole)
        ok.setObjectName("Primary")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.addWidget(lab1)
        lay.addWidget(self.query_edit)
        lay.addWidget(lab2)
        lay.addWidget(self.remark_edit)
        lay.addWidget(tip)
        lay.addWidget(btns)

    def values(self) -> tuple[str, str]:
        return self.query_edit.text().strip(), self.remark_edit.toPlainText().strip()


class SearchPage(QWidget):
    open_sop = Signal(str)   # 携带 sop_id

    def __init__(self, store: Store, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self._results: list = []

        root = QVBoxLayout(self)
        root.setContentsMargins(48, 40, 48, 32)

        # 顶部标题
        title = QLabel("SOP 快速查找")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignHCenter)
        sub = QLabel("输入机台报警代码或故障关键词，点击“搜索”，如：E4303、4303、module not found")
        sub.setObjectName("Subtitle")
        sub.setAlignment(Qt.AlignHCenter)

        # 搜索框 + 搜索按钮
        row = QHBoxLayout()
        row.setSpacing(10)
        self.input = QLineEdit()
        self.input.setObjectName("SearchInput")
        self.input.setPlaceholderText("在此输入报警代码 / 故障描述…")
        self.input.setClearButtonEnabled(True)
        self.input.returnPressed.connect(self._do_search)
        self.search_btn = QPushButton("🔍 搜 索")
        self.search_btn.setObjectName("SearchButton")
        self.search_btn.setCursor(Qt.PointingHandCursor)
        self.search_btn.clicked.connect(self._do_search)
        row.addWidget(self.input, 1)
        row.addWidget(self.search_btn)

        # 结果区
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        self.count_label.setVisible(False)
        self.result_list = QListWidget()
        self.result_list.setObjectName("ResultList")
        self.result_list.itemClicked.connect(self._item_clicked)
        self.result_list.setVisible(False)
        self.result_list.setMaximumHeight(400)
        self.notfound_hint = QLabel("")
        self.notfound_hint.setObjectName("NotFoundHint")
        self.notfound_hint.setAlignment(Qt.AlignHCenter)
        self.notfound_hint.setWordWrap(True)
        self.notfound_hint.setVisible(False)

        # 底部操作
        bottom = QHBoxLayout()
        self.feedback_btn = QPushButton("⚠ 反馈报错（找不到SOP时点这里，可写备注）")
        self.feedback_btn.setObjectName("Warn")
        self.feedback_btn.clicked.connect(self._submit_feedback)
        self.flash = FlashLabel()
        bottom.addWidget(self.feedback_btn)
        bottom.addWidget(self.flash)
        bottom.addStretch(1)

        root.addWidget(title)
        root.addWidget(sub)
        root.addSpacing(18)
        root.addLayout(row)
        root.addSpacing(10)
        root.addWidget(self.count_label)
        root.addWidget(self.result_list)
        root.addWidget(self.notfound_hint)
        root.addSpacing(8)
        root.addStretch(1)
        root.addLayout(bottom)

    # ---------- 对外 ----------
    def refresh(self) -> None:
        """回到首页时只聚焦输入框，保留上次结果，不重复搜索/记录。"""
        self.input.setFocus()

    def set_store(self, store: Store) -> None:
        self.store = store

    # ---------- 正式搜索 ----------
    def _do_search(self) -> None:
        query = self.input.text().strip()
        self.result_list.clear()
        self._results = []
        self.count_label.setVisible(False)
        self.result_list.setVisible(False)
        self.notfound_hint.setVisible(False)
        if not query:
            self.flash.flash("请先输入报警代码或故障关键词。")
            self.input.setFocus()
            return

        self._results = search.search(self.store.sops, query)
        found = len(self._results) > 0
        # 自动写入搜索记录（日期/时间/内容/是否找到）
        try:
            rec = self.store.add_search_log(query, found)
        except OSError:
            rec = None   # 共享盘暂不可写时不影响搜索本身

        if not found:
            self.notfound_hint.setText(
                f"⚠ 未找到此报警：{elide(query, 60)}\n"
                "已自动记录到“搜索记录”，请在弹窗中提交机台报错截图，方便工程师补充 SOP。")
            self.notfound_hint.setVisible(True)
            if rec is not None and self.isVisible():
                dlg = ShotSubmitDialog(self.store, rec.id, query, self)
                dlg.exec()
            return
        if len(self._results) == 1:
            self.open_sop.emit(self._results[0][0].id)   # 唯一结果直接打开
            return
        # 多个命中 → 列表供选择
        for sop, _score in self._results:
            self._make_item(sop)
        self.count_label.setText(f"共 {len(self._results)} 条匹配，单击选择对应 SOP")
        self.count_label.setVisible(True)
        self.result_list.setVisible(True)

    def _make_item(self, sop) -> None:
        codes = "、".join(sop.alarm_codes) if sop.alarm_codes else "（未填报警代码）"
        sub = f"报警代码：{codes}    |    {len(sop.pages)} 页    |    {elide(sop.solution, 60)}"
        item = QListWidgetItem()
        item.setData(Qt.UserRole, sop.id)
        item.setSizeHint(QSize(10, 64))
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(2)
        name = QLabel(f"{sop.name}")
        name.setObjectName("ResultName")
        sublab = QLabel(sub)
        sublab.setObjectName("ResultSub")
        lay.addWidget(name)
        lay.addWidget(sublab)
        self.result_list.addItem(item)
        self.result_list.setItemWidget(item, widget)

    def _item_clicked(self, item: QListWidgetItem) -> None:
        sop_id = item.data(Qt.UserRole)
        if sop_id:
            self.open_sop.emit(sop_id)

    def _submit_feedback(self) -> None:
        dlg = FeedbackDialog(self.input.text(), self)
        if dlg.exec() == QDialog.Accepted:
            query, remark = dlg.values()
            if not query:
                warn(self, "提示", "请填写报警 / 故障内容。")
                return
            self.store.add_feedback(query, remark)
            self.flash.flash("✔ 已记录反馈，工程师会尽快补充对应 SOP。")
