"""SOP 编辑器（新建 / 编辑）。

页面组织：编辑期间所有待保存页面都记在内存列表 _page_files（绝对路径），
点“保存”时才统一写入 Data/media/<id>/ 并重新编号，中途取消不留垃圾文件。
PPT 通过后台线程调用 PowerPoint/WPS 转成 PNG；原 PPT 一份副本随 SOP 保留。
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QProgressDialog, QPushButton, QVBoxLayout,
                               QWidget)

from app.converter import ConversionError, convert_ppt
from app.store import IMAGE_EXTS, PPT_EXTS, Sop, Store, new_id, now_str


def parse_codes(text: str) -> list[str]:
    """把多行/逗号/空格分隔的报警代码整理成去重列表（忽略大小写去重，保留原大小写）。"""
    raw = re.split(r"[\n\r,，、;；\s]+", text or "")
    seen: set[str] = set()
    codes: list[str] = []
    for c in raw:
        c = c.strip()
        if c and c.casefold() not in seen:
            seen.add(c.casefold())
            codes.append(c)
    return codes


class ConvertWorker(QThread):
    """后台转换 PPT，转换期间界面不卡死。"""

    done = Signal(list, bool)      # (文件路径列表, 是否被用户取消)
    failed = Signal(str)
    prog = Signal(int, int)

    def __init__(self, ppt_path: Path, out_dir: Path, width: int, parent=None):
        super().__init__(parent)
        self.ppt_path = ppt_path
        self.out_dir = out_dir
        self.width = width
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            files = convert_ppt(self.ppt_path, self.out_dir, self.width,
                                progress=lambda i, n: self.prog.emit(i, n),
                                cancel_flag=lambda: self._cancel)
            self.done.emit([str(f) for f in files], self._cancel)
        except ConversionError as e:
            self.failed.emit(str(e))
        except Exception as e:   # COM 等底层错误统一包装
            self.failed.emit(f"转换失败：{e}")


class PdfConvertWorker(QThread):
    """后台把 PDF 逐页渲染为 PNG。"""

    done = Signal(list, bool)
    failed = Signal(str)
    prog = Signal(int, int)

    def __init__(self, pdf_path: Path, out_dir: Path, width: int, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.out_dir = out_dir
        self.width = width
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            from app.pdfconvert import convert_pdf
            files = convert_pdf(self.pdf_path, self.out_dir, self.width,
                                progress=lambda i, n: self.prog.emit(i, n),
                                cancel_flag=lambda: self._cancel)
            self.done.emit([str(f) for f in files], self._cancel)
        except ConversionError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"PDF 转换失败：{e}")


class EditorDialog(QDialog):
    def __init__(self, store: Store, cfg, sop: Sop | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.cfg = cfg
        self.sop = sop
        self.saved_id: str | None = None

        self._page_files: list[Path] = []          # 待保存页面（绝对路径）
        self._originals: list[dict] = []           # {"src","name","stored"}
        self._from_ppt_count = 0
        self._worker: ConvertWorker | None = None
        self._tmpdir = tempfile.mkdtemp(prefix="qs_edit_")
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.finished.connect(self._cleanup)

        self.setWindowTitle("编辑 SOP" if sop else "新建 SOP")
        self.setMinimumSize(QSize(820, 660))

        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ---- 基本信息 ----
        root.addWidget(QLabel("SOP 名称（必填）："))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：E4303 module not found 处理流程")
        root.addWidget(self.name_edit)

        root.addWidget(QLabel("关联报警代码（可多个，每行一个，也可用逗号/空格分隔）："))
        self.codes_edit = QPlainTextEdit()
        self.codes_edit.setPlaceholderText("例如：\nE4303\nE4305")
        self.codes_edit.setFixedHeight(72)
        root.addWidget(self.codes_edit)

        root.addWidget(QLabel("解决方式说明（会显示在查看页顶部，支持中文）："))
        self.solution_edit = QPlainTextEdit()
        self.solution_edit.setPlaceholderText("例如：重新插拔 module；若仍报警则检查模块供电并更换备用模块。")
        self.solution_edit.setFixedHeight(72)
        root.addWidget(self.solution_edit)

        # ---- 页面管理 ----
        root.addWidget(QLabel("SOP 页面（支持多页，图片或 PPT 自动转出的图片）："))
        mid = QHBoxLayout()
        self.pages_list = QListWidget()
        self.pages_list.currentRowChanged.connect(self._show_preview)
        self.pages_list.setFixedWidth(340)
        mid.addWidget(self.pages_list)

        right = QVBoxLayout()
        self.preview = QLabel("选择左侧页面可预览")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(320, 240)
        self.preview.setStyleSheet(
            "background:#f4f6fa; border:1px solid #d9e0ea; border-radius:10px; color:#8a97ac;")
        self.preview.setScaledContents(False)
        right.addWidget(self.preview, 1)

        btns = QHBoxLayout()
        self.add_img_btn = QPushButton("添加图片…")
        self.add_ppt_btn = QPushButton("添加PPT…")
        self.add_pdf_btn = QPushButton("添加PDF…")
        self.paste_btn = QPushButton("📋 粘贴截图")
        self.paste_btn.setToolTip("把刚截的图（PrintScreen/聊天工具截图）或复制的图片文件直接粘贴为页面 (Ctrl+V)")
        self.up_btn = QPushButton("上移")
        self.down_btn = QPushButton("下移")
        self.rm_btn = QPushButton("移除")
        for b in (self.add_img_btn, self.add_ppt_btn, self.add_pdf_btn,
                  self.paste_btn, self.up_btn, self.down_btn, self.rm_btn):
            btns.addWidget(b)
        right.addLayout(btns)

        self.orig_label = QLabel("")
        self.orig_label.setObjectName("Muted")
        self.orig_label.setWordWrap(True)
        right.addWidget(self.orig_label)
        mid.addLayout(right, 1)
        root.addLayout(mid, 1)

        tip = QLabel("提示：PPT 转换需要本机安装 PowerPoint 或 WPS（仅上传电脑需要）；PDF 每页自动转图片；"
                     "截图可直接 Ctrl+V 粘贴为页面；转换失败时可把文件手动导出为图片后“添加图片”。")
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        root.addWidget(tip)

        # ---- 底部按钮 ----
        foot = QHBoxLayout()
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#c62828;")
        foot.addWidget(self.error_label)
        foot.addStretch(1)
        bb = QDialogButtonBox()
        save_btn = bb.addButton("保存", QDialogButtonBox.AcceptRole)
        save_btn.setObjectName("Primary")
        bb.addButton("取消", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        foot.addWidget(bb)
        root.addLayout(foot)

        # ---- 信号 ----
        self.add_img_btn.clicked.connect(self._add_images)
        self.add_ppt_btn.clicked.connect(self._add_ppt)
        self.add_pdf_btn.clicked.connect(self._add_pdf)
        self.paste_btn.clicked.connect(self._paste_screenshot)
        self.up_btn.clicked.connect(lambda: self._move_page(-1))
        self.down_btn.clicked.connect(lambda: self._move_page(1))
        self.rm_btn.clicked.connect(self._remove_page)

        from PySide6.QtGui import QKeySequence, QShortcut
        sc = QShortcut(QKeySequence("Ctrl+V"), self)
        sc.activated.connect(self._paste_screenshot)

        if sop:
            self._load_existing(sop)

    # ---------- 载入已有 SOP ----------
    def _load_existing(self, sop: Sop) -> None:
        self.name_edit.setText(sop.name)
        self.codes_edit.setPlainText("\n".join(sop.alarm_codes))
        self.solution_edit.setPlainText(sop.solution)
        self._page_files = [self.store.page_path(sop, i) for i in range(len(sop.pages))]
        for o in sop.originals:
            self._originals.append({
                "src": str(self.store.media_dir(sop.id) / o["file"]),
                "name": o["name"],
                "stored": o["file"].split("/")[-1],
            })
        if sop.source in ("ppt", "mixed"):
            self._from_ppt_count = len(sop.pages)
        self._refresh_pages()

    # ---------- 页面列表 ----------
    def _refresh_pages(self) -> None:
        self.pages_list.clear()
        for i, p in enumerate(self._page_files, 1):
            it = QListWidgetItem(f"第 {i} 页 — {p.name}")
            self.pages_list.addItem(it)
        if self._page_files:
            self.pages_list.setCurrentRow(0)
        orig_names = "；".join(o["name"] for o in self._originals)
        self.orig_label.setText(f"已保留 PPT 原文件：{orig_names}（查看时可外部打开）"
                                if orig_names else "")

    def _show_preview(self, row: int) -> None:
        if not (0 <= row < len(self._page_files)):
            return
        reader = QImageReader(str(self._page_files[row]))
        reader.setAutoTransform(True)
        img = reader.read()
        if img.isNull():
            self.preview.setText("图片无法预览")
            return
        # 按“适配框”缩放：框最大不超过预览区当前尺寸，保证完整显示一页
        box = self.preview.size().boundedTo(QSize(760, 560))
        if box.width() < 80 or box.height() < 60:
            box = QSize(320, 240)
        pm = QPixmap.fromImage(img).scaled(box, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(pm)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setText("")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._show_preview(self.pages_list.currentRow())

    def _move_page(self, delta: int) -> None:
        row = self.pages_list.currentRow()
        if row < 0:
            return
        new = row + delta
        if not (0 <= new < len(self._page_files)):
            return
        self._page_files[row], self._page_files[new] = self._page_files[new], self._page_files[row]
        self._refresh_pages()
        self.pages_list.setCurrentRow(new)

    def _remove_page(self) -> None:
        row = self.pages_list.currentRow()
        if row < 0:
            return
        del self._page_files[row]
        self._refresh_pages()

    def _add_images(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(IMAGE_EXTS))
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择图片（可多选）", "",
            f"图片 ({exts});;所有文件 (*.*)")
        if not files:
            return
        for f in sorted(files):
            self._page_files.append(Path(f))
        self._refresh_pages()

    def _wait_convert(self, worker: QThread, label: str) -> tuple[list, bool, str]:
        """弹出进度条等一个转换线程跑完。返回 (文件列表, 是否取消, 错误信息)。

        关键点：QProgressDialog 默认在 setValue 到达最大值时**自动关闭**，
        而"完成"信号是跨线程队列送达的——若对话框在信号送达前就退出事件循环，
        会把成功结果误判为空（历史上表现为"没有转换出任何页面"）。
        因此这里禁用自动关闭，在收到 done/failed 信号后再显式关闭，
        并在退出后继续泵事件直到结果真正送达。
        """
        from PySide6.QtCore import QCoreApplication, QEventLoop
        dlg = QProgressDialog(label, "取消", 0, 0, self)
        dlg.setWindowTitle("转换")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoReset(False)
        dlg.setAutoClose(False)
        dlg.show()

        state: dict = {"files": None, "canceled": False, "err": ""}

        def on_prog(i: int, n: int) -> None:
            dlg.setRange(0, n)
            dlg.setValue(i)
            dlg.setLabelText(f"{label} 第 {i}/{n} 页")

        def on_done(files: list, canceled: bool) -> None:
            state["files"] = files
            state["canceled"] = canceled
            dlg.accept()

        def on_fail(msg: str) -> None:
            state["err"] = msg
            dlg.accept()

        worker.prog.connect(on_prog)
        worker.done.connect(on_done)
        worker.failed.connect(on_fail)
        dlg.canceled.connect(worker.cancel)
        worker.start()
        dlg.exec()
        worker.wait()
        worker.deleteLater()
        # 兜底：done 可能在线程退出后才入队（如用户取消），继续泵事件直到送达
        spins = 0
        while state["files"] is None and not state["err"] and spins < 250:
            QCoreApplication.processEvents(QEventLoop.AllEvents, 20)
            spins += 1
        return state["files"] or [], state["canceled"], state["err"]

    def _adopt_converted(self, path: Path, files: list, canceled: bool,
                         keep_original: bool = True) -> None:
        """把转换出的页面追加进列表（可选保留原文件）。"""
        if not files:
            QMessageBox.warning(self, "转换失败",
                                "没有转换出任何页面（可能文件为空或被取消）。")
            return
        if canceled:
            if not (QMessageBox.question(
                    self, "已取消",
                    f"已转换 {len(files)} 页后取消。只使用已转换的页面吗？")
                    in (QMessageBox.Yes, QMessageBox.Ok)):
                return
        self._page_files.extend(Path(f) for f in files)
        self._from_ppt_count += len(files)
        if keep_original:
            orig_copy = Path(self._tmpdir) / f"orig_{new_id()}_{Path(path).name}"
            try:
                shutil.copyfile(path, orig_copy)
                self._originals.append({"src": str(orig_copy), "name": Path(path).name,
                                        "stored": None})
            except OSError:
                pass   # 原文件保留失败不影响主流程
        self._refresh_pages()

    def _add_ppt(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "提示", "正在转换上一个文件，请稍候。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 PPT 文件", "", "演示文稿 (*.pptx *.ppt);;所有文件 (*.*)")
        if not path:
            return
        out = Path(self._tmpdir) / f"conv_{new_id()}"
        out.mkdir(parents=True, exist_ok=True)
        width = int(self.cfg.data.get("ppt_width", 1440) or 1440)

        self._worker = ConvertWorker(Path(path), out, width, self)
        files, canceled, err = self._wait_convert(
            self._worker, "正在转换 PPT（每页导出为图片）…")
        self._worker = None
        if err:
            QMessageBox.warning(
                self, "转换失败", err +
                "\n\n也可以把 PPT 每页另存为图片后，用“添加图片”导入。")
            return
        self._adopt_converted(Path(path), files, canceled, keep_original=True)

    def _add_pdf(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "提示", "正在转换上一个文件，请稍候。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 PDF 文件", "", "PDF 文档 (*.pdf);;所有文件 (*.*)")
        if not path:
            return
        out = Path(self._tmpdir) / f"pdf_{new_id()}"
        out.mkdir(parents=True, exist_ok=True)
        width = int(self.cfg.data.get("ppt_width", 1440) or 1440)

        self._worker = PdfConvertWorker(Path(path), out, width, self)
        files, canceled, err = self._wait_convert(
            self._worker, "正在导入 PDF（每页转为图片）…")
        self._worker = None
        if err:
            QMessageBox.warning(
                self, "导入失败", err +
                "\n\n也可以把 PDF 每页另存为图片后，用“添加图片”导入。")
            return
        self._adopt_converted(Path(path), files, canceled, keep_original=True)

    def _add_image_object(self, img) -> None:
        """把一张 QImage 保存为临时 png 并追加为页面（粘贴截图入口）。"""
        fp = Path(self._tmpdir) / f"paste_{new_id()}.png"
        if not img.save(str(fp)):
            QMessageBox.warning(self, "提示", "截图保存失败，请重试。")
            return
        self._page_files.append(fp)
        self._refresh_pages()
        self.pages_list.setCurrentRow(len(self._page_files) - 1)

    def _paste_screenshot(self) -> None:
        """把剪贴板里的截图（或复制的图片文件）直接添加为一页。"""
        from PySide6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        md = cb.mimeData()
        if md.hasImage():
            img = cb.image()
            if not img.isNull():
                self._add_image_object(img)
                return
        if md.hasUrls():
            from app.store import IMAGE_EXTS
            for url in md.urls():
                p = Path(url.toLocalFile())
                if p.suffix.lower() in IMAGE_EXTS and p.exists():
                    self._page_files.append(p)
                    self._refresh_pages()
                    self.pages_list.setCurrentRow(len(self._page_files) - 1)
                    return
            QMessageBox.information(self, "提示",
                                    "剪贴板里复制的文件不是图片。\n请复制 png/jpg 图片文件，或先截图再粘贴。")
            return
        QMessageBox.information(
            self, "提示",
            "剪贴板里没有图片。\n请先截图（PrintScreen 或聊天工具截图），"
            "或在资源管理器里复制图片文件后再点“粘贴截图”。")

    # ---------- 保存 ----------
    def _save(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.error_label.setText("请填写 SOP 名称。")
            self.name_edit.setFocus()
            return
        missing = [str(p) for p in self._page_files if not Path(p).exists()]
        if missing:
            self.error_label.setText("部分页面文件不存在，请移除后重试。")
            return

        codes = parse_codes(self.codes_edit.toPlainText())
        solution = self.solution_edit.toPlainText().strip()
        if self.sop is None:
            sop = Sop(name=name, alarm_codes=codes, solution=solution, created_at=now_str())
        else:
            sop = self.sop
            sop.name = name
            sop.alarm_codes = codes
            sop.solution = solution

        try:
            pages, originals = self._persist(sop.id)
        except OSError as e:
            QMessageBox.critical(self, "保存失败",
                                 f"写入文件失败：\n{e}\n\n"
                                 "若使用共享目录，请检查网络与权限。")
            return
        sop.pages = pages
        sop.originals = originals
        if self._originals:
            sop.source = "ppt" if self._from_ppt_count == len(pages) else "mixed"
        else:
            sop.source = "image"
        sop.updated_at = now_str()

        if self.sop is None:
            self.store.add_sop(sop)
        else:
            self.store.update_sop()
        self.saved_id = sop.id
        self.accept()

    def _persist(self, sop_id: str) -> tuple[list[str], list[dict]]:
        """把暂存页面/原文件写入 media 目录并重新编号，返回 (pages, originals)。"""
        mdir = self.store.media_dir(sop_id)
        mdir.mkdir(parents=True, exist_ok=True)

        final_names: list[str] = []
        pending: list[tuple[Path, Path, Path]] = []      # (源, 临时名, 目标名)
        for i, src in enumerate(self._page_files, 1):
            ext = Path(src).suffix.lower() or ".png"
            final = f"{i:04d}{ext}"
            final_names.append(final)
            srcp = Path(src).resolve()
            dstp = (mdir / final).resolve()
            if srcp == dstp:
                continue
            tmpn = mdir / f".staging_{i:04d}{ext}"
            pending.append((srcp, tmpn, dstp))

        # 1) 先复制到临时名（此时旧文件都还在）
        for srcp, tmpn, _dstp in pending:
            shutil.copyfile(srcp, tmpn)
        # 2) 删除不再需要的旧编号文件
        keep = set(final_names)
        for old in mdir.iterdir():
            if old.is_file() and re.fullmatch(r"\d{4}\..+", old.name) and old.name not in keep:
                old.unlink()
        # 3) 临时名改到位
        for _srcp, tmpn, dstp in pending:
            os.replace(tmpn, dstp)

        orig_dir = mdir / "original"
        orig_dir.mkdir(exist_ok=True)
        saved: list[dict] = []
        for o in self._originals:
            srcp = Path(o["src"]).resolve()
            stored = o.get("stored") or f"{new_id()}_{o['name']}"
            dstp = (orig_dir / stored).resolve()
            if srcp != dstp:
                shutil.copyfile(srcp, dstp)
            saved.append({"file": f"original/{stored}", "name": o["name"]})
        return final_names, saved

    def _cleanup(self, *_args) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)
