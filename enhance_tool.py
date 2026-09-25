"""Quicksearch SOP 高清修复工具（独立小工具，只在工程师电脑上使用）。

与主程序分开打包：产线电脑只装主程序 Quicksearch.exe（不含 OpenCV，轻量）；
需要修复图片清晰度时，用本工具打开 SOP 库，选中 SOP 一键超分。

用法：
    SOP高清修复工具.exe                     打开界面
    SOP高清修复工具.exe --data-dir X        指定数据目录
    SOP高清修复工具.exe --selftest          自检（模型加载 + 小图超分）
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _parse_args(argv: list[str]) -> dict:
    args = {"selftest": False, "smoke": False, "data_dir": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--selftest":
            args["selftest"] = True
        elif a == "--smoke":
            args["smoke"] = True
        elif a == "--data-dir" and i + 1 < len(argv):
            args["data_dir"] = argv[i + 1]
            i += 1
        i += 1
    return args


def selftest() -> int:
    print("高清修复工具自检")
    try:
        import cv2  # noqa: F401
    except ImportError as e:
        print(f"  [FAIL] OpenCV 未打包: {e}")
        return 1
    print("  [PASS] OpenCV 导入")
    import numpy as np
    from app.config import model_file
    from app.enhance import MODEL_NAME, _imread, _imwrite, enhance_image
    mp = model_file(MODEL_NAME)
    if not mp.exists():
        print(f"  [FAIL] 超分模型缺失: {mp}")
        return 1
    print(f"  [PASS] 模型存在: {mp.name}")

    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="qs_tool_"))
    try:
        src = tmp / "测试页.png"
        img = np.full((160, 240, 3), 255, np.uint8)
        cv2.putText(img, "E4303", (30, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 2)
        _imwrite(src, img)
        dst = tmp / "输出.png"
        enhance_image(src, dst)
        out = _imread(dst)
        assert out.shape[0] == 320 and out.shape[1] == 480, f"超分尺寸异常: {out.shape}"
        print("  [PASS] 端到端超分 (240x160 → 480x320)")
        return 0
    except Exception as e:
        print(f"  [FAIL] 超分失败: {e}")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _resolve_data_dir() -> Path:
    override = (os.environ.get("QUICKSEARCH_DATA_DIR") or "").strip()
    if override:
        return Path(override)
    exe_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parent
    cand = exe_dir / "Data"
    if cand.exists():
        return cand
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Quicksearch" / "Data"


def run_gui(smoke: bool = False) -> int:
    from PySide6.QtCore import Qt, QThread, Signal
    from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel,
                                   QLineEdit, QListWidget, QListWidgetItem,
                                   QMainWindow, QProgressBar, QPushButton,
                                   QVBoxLayout, QWidget)

    from app.config import APP_TITLE
    from app.enhance import enhance_available, enhance_sop_pages
    from app.icons import make_icon
    from app.store import Store
    from app.ui.common import confirm, info, warn
    from app.ui.theme import STYLE

    class EnhanceWorker(QThread):
        done = Signal(int, int, list)
        prog = Signal(int, int)

        def __init__(self, pages, parent=None):
            super().__init__(parent)
            self.pages = pages
            self._cancel = False

        def cancel(self):
            self._cancel = True

        def run(self):
            done, skipped, errors = enhance_sop_pages(
                self.pages,
                progress=lambda i, n: self.prog.emit(i, n),
                cancel_flag=lambda: self._cancel)
            self.done.emit(done, skipped, errors)

    class ToolWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Quicksearch — SOP 高清修复工具")
            self.setWindowIcon(make_icon())
            self.setMinimumSize(640, 560)
            self.store: Store | None = None
            self._worker: EnhanceWorker | None = None

            central = QWidget()
            root = QVBoxLayout(central)
            root.setContentsMargins(20, 16, 20, 16)
            root.setSpacing(10)

            tip = QLabel("把 SOP 库里模糊的页面图片用 AI 超分放大 2 倍并锐化（本机离线，约 1 秒/页）。\n"
                         "产线电脑不需要装本工具；修复是替换原图的一次性操作，建议先备份数据。")
            tip.setObjectName("Muted")
            tip.setWordWrap(True)
            root.addWidget(tip)

            row = QHBoxLayout()
            row.addWidget(QLabel("数据目录："))
            self.dir_edit = QLineEdit()
            self.dir_edit.setReadOnly(True)
            row.addWidget(self.dir_edit, 1)
            browse = QPushButton("更改…")
            browse.clicked.connect(self._browse)
            reload_btn = QPushButton("⟳ 刷新")
            reload_btn.clicked.connect(self._reload)
            row.addWidget(browse)
            row.addWidget(reload_btn)
            root.addLayout(row)

            root.addWidget(QLabel("选择要修复的 SOP："))
            self.list = QListWidget()
            root.addWidget(self.list, 1)

            self.start_btn = QPushButton("✨ 开始修复选中 SOP")
            self.start_btn.setObjectName("Primary")
            self.start_btn.clicked.connect(self._start)
            root.addWidget(self.start_btn)

            self.bar = QProgressBar()
            self.bar.setVisible(False)
            root.addWidget(self.bar)
            self.status = QLabel("")
            self.status.setObjectName("Muted")
            root.addWidget(self.status)

            self.setCentralWidget(central)
            self._set_dir(_resolve_data_dir())

        def _set_dir(self, d: Path) -> None:
            os.environ["QUICKSEARCH_DATA_DIR"] = str(d)
            self.dir_edit.setText(str(d))
            self._reload()

        def _browse(self) -> None:
            d = QFileDialog.getExistingDirectory(self, "选择 Quicksearch 数据目录",
                                                 self.dir_edit.text())
            if d:
                self._set_dir(Path(d))

        def _reload(self) -> None:
            d = Path(self.dir_edit.text())
            try:
                self.store = Store(d)
            except OSError as e:
                warn(self, "错误", f"无法读取数据目录：\n{e}")
                return
            self.list.clear()
            for sop in sorted(self.store.sops, key=lambda s: s.name):
                it = QListWidgetItem(f"{sop.name}　（{len(sop.pages)} 页）")
                it.setData(Qt.UserRole, sop.id)
                self.list.addItem(it)
            self.status.setText(f"共 {len(self.store.sops)} 个 SOP。"
                                if self.store.sops else "该目录下还没有 SOP。")

        def _start(self) -> None:
            if self._worker is not None and self._worker.isRunning():
                info(self, "提示", "正在修复中，请稍候。")
                return
            it = self.list.currentItem()
            if it is None:
                info(self, "提示", "请先在列表中选择一个 SOP。")
                return
            sop = self.store.get_sop(it.data(Qt.UserRole))
            if not sop or not sop.pages:
                info(self, "提示", "该 SOP 没有页面图片。")
                return
            if not enhance_available():
                warn(self, "高清修复不可用", "OpenCV 或超分模型缺失，请使用完整打包的版本。")
                return
            if not confirm(self, "高清修复",
                           f"将对「{sop.name}」的 {len(sop.pages)} 页图片执行 AI 超分（放大2倍+锐化）：\n\n"
                           "· 一次性替换原图，建议先备份 Data 文件夹\n"
                           "· 处理期间请勿关闭本工具\n\n继续吗？"):
                return
            pages = [self.store.page_path(sop, i) for i in range(len(sop.pages))]
            self._worker = EnhanceWorker(pages, self)
            self.bar.setRange(0, len(pages))
            self.bar.setValue(0)
            self.bar.setVisible(True)
            self.start_btn.setEnabled(False)

            def on_prog(i, n):
                self.bar.setValue(i)
                self.status.setText(f"正在修复… 第 {i}/{n} 页")

            def on_done(done, skipped, errors):
                msg = f"✔ 修复完成：成功 {done} 页"
                if skipped:
                    msg += f"，跳过 {skipped} 页"
                if errors:
                    msg += f"，失败 {len(errors)} 页"
                self.status.setText(msg)
                info(self, "完成", msg + ("\n\n" + "；".join(errors[:3]) if errors else ""))

            def on_cleanup():
                self.bar.setVisible(False)
                self.start_btn.setEnabled(True)
                self._worker = None

            self._worker.prog.connect(on_prog)
            self._worker.done.connect(on_done)
            self._worker.finished.connect(on_cleanup)
            self._worker.start()

    app = QApplication(sys.argv)
    app.setApplicationName("QuicksearchEnhance")
    app.setStyleSheet(STYLE)
    win = ToolWindow()
    win.show()

    if smoke:
        from PySide6.QtCore import QTimer
        result = {"ok": win.isVisible() and win.list.count() >= 0}

        def _check():
            result["ok"] = win.isVisible()

        QTimer.singleShot(300, _check)
        QTimer.singleShot(1500, app.quit)
        app.exec()
        print("SMOKE OK" if result["ok"] else "SMOKE FAIL")
        return 0 if result["ok"] else 1

    return app.exec()


def main() -> int:
    args = _parse_args(sys.argv[1:])
    if args["data_dir"]:
        os.environ["QUICKSEARCH_DATA_DIR"] = args["data_dir"]
    if args["selftest"]:
        return selftest()
    return run_gui(smoke=args["smoke"])


if __name__ == "__main__":
    sys.exit(main())
