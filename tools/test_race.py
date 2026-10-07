"""隔离运行 _wait_convert 竞态测试（诊断用）。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import shutil

from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtWidgets import QApplication

from app.config import Config
from app.store import Store
from app.ui.editor_dialog import EditorDialog


class FakeWorker(QThread):
    done = Signal(list, bool)
    failed = Signal(str)
    prog = Signal(int, int)

    def __init__(self):
        super().__init__()
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        for i in range(1, 4):
            self.prog.emit(i, 3)
            QThread.msleep(30)
        self.done.emit(["p1.png", "p2.png", "p3.png"], False)


def main() -> int:
    app = QApplication(sys.argv)
    tmp = Path(tempfile.mkdtemp(prefix="qs_race_"))
    try:
        store = Store(tmp / "Data")
        ed = EditorDialog(store, Config(tmp / "config.json"), parent=None)
        print("编辑器创建 OK", flush=True)

        def run_test():
            fw = FakeWorker()
            print("开始 _wait_convert…", flush=True)
            files, canceled, err = ed._wait_convert(fw, "竞态测试")
            print(f"结果 files={files} canceled={canceled} err={err!r}", flush=True)
            ok = files == ["p1.png", "p2.png", "p3.png"] and not err
            print("PASS" if ok else "FAIL", flush=True)
            app.exit(0 if ok else 1)

        QTimer.singleShot(100, run_test)
        code = app.exec()
        print(f"app 退出 code={code}", flush=True)
        return code
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
