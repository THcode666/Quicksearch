"""Quicksearch 程序入口。

用法：
    Quicksearch.exe                 正常启动
    Quicksearch.exe --selftest      运行自检测试（不打开界面）
    Quicksearch.exe --ppt-test      PPT→图片 端到端转换测试
    Quicksearch.exe --smoke         启动界面 2 秒后自动退出（部署验证用）
    Quicksearch.exe --data-dir X    指定数据目录（也可用环境变量 QUICKSEARCH_DATA_DIR）
    Quicksearch.exe --version       显示版本号
"""
from __future__ import annotations

import os
import sys


def _parse_args(argv: list[str]) -> dict:
    args = {"selftest": False, "smoke": False, "version": False,
            "ppt_test": False, "data_dir": None}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--selftest":
            args["selftest"] = True
        elif a == "--smoke":
            args["smoke"] = True
        elif a == "--version":
            args["version"] = True
        elif a == "--ppt-test":
            args["ppt_test"] = True
        elif a == "--data-dir" and i + 1 < len(argv):
            args["data_dir"] = argv[i + 1]
            i += 1
        i += 1
    return args


def main() -> int:
    args = _parse_args(sys.argv[1:])
    if args["data_dir"]:
        os.environ["QUICKSEARCH_DATA_DIR"] = args["data_dir"]

    if args["version"]:
        from app.config import APP_VERSION
        print(f"Quicksearch v{APP_VERSION}")
        return 0

    if args["ppt_test"]:
        from app.selftest import test_ppt_real
        return test_ppt_real()

    if args["selftest"]:
        from app.selftest import run_all
        return run_all(include_ui=True)

    # ---- GUI ----
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from app.config import APP_TITLE
    from app.ui.main_window import MainWindow
    from app.ui.theme import STYLE

    app = QApplication(sys.argv)
    app.setApplicationName("Quicksearch")
    app.setApplicationDisplayName(APP_TITLE)
    app.setStyleSheet(STYLE)

    # 单实例：重复启动时唤醒已有窗口
    from app.instance import SingleInstance

    try:
        import getpass
        user = getpass.getuser()
    except Exception:
        user = "default"
    instance = SingleInstance(f"Quicksearch_{user}")

    window = MainWindow()
    from app.icons import make_icon
    app.setWindowIcon(make_icon())

    def _activate() -> None:
        window.activate()

    if not instance.try_acquire(_activate):
        window.deleteLater()
        return 0   # 已有实例在运行，唤醒消息已发出

    window.show()
    window.show_page(0)

    if args["smoke"]:
        result = {"ok": True}

        def _check() -> None:
            result["ok"] = window.isVisible()

        QTimer.singleShot(300, _check)
        QTimer.singleShot(2000, app.quit)
        app.exec()
        instance.shutdown()
        print("SMOKE OK" if result["ok"] else "SMOKE FAIL: window not visible")
        return 0 if result["ok"] else 1

    app.exec()
    instance.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
