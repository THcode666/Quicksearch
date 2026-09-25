"""生成界面预览截图（不弹出窗口）：tools/take_screens.py → shots/*.png

构造一套演示数据（含中文SOP、多报警代码、多页SOP、反馈记录），
依次抓取各页面。用于开发自检，不影响正式数据。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from app.config import Config
from app.store import Sop, Store


def make_page(path: Path, title: str, lines: list[str]) -> None:
    img = QImage(1600, 1000, QImage.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setPen(QColor("#24539f"))
    p.fillRect(0, 0, 1600, 130, QColor("#24539f"))
    p.setPen(QColor("white"))
    p.setFont(QFont("Microsoft YaHei", 34, QFont.Bold))
    p.drawText(img.rect().adjusted(50, 0, -50, -130), Qt.AlignVCenter, title)
    p.setPen(QColor("#223047"))
    p.setFont(QFont("Microsoft YaHei", 22))
    y = 220
    for ln in lines:
        p.drawText(90, y, ln)
        y += 78
    p.setPen(QColor("#9db2cf"))
    p.setFont(QFont("Microsoft YaHei", 14))
    p.drawText(90, 950, "Quicksearch 演示数据 · 仅供界面预览")
    p.end()
    img.save(str(path))


def build_demo(data_dir: Path) -> Store:
    st = Store(data_dir)
    demo = [
        ("E4303 module not found 处理流程", ["E4303"],
         "1. 重新插拔 module；\n2. 检查模块供电电压（DC24V）；\n3. 仍报警则更换备用模块并通知设备工程师。",
         ["步骤：确认报警信息", "步骤：重新插拔模块", "步骤：更换备用模块"]),
        ("E4304 风扇转速异常处理", ["E4304"],
         "清洁风扇滤网；转速仍低于阈值时更换风扇。",
         ["步骤：清洁滤网", "步骤：更换风扇"]),
        ("探针卡清洗保养SOP", ["E7101", "E7102"],
         "使用无水酒精清洗探针卡针尖，晾干后装机测试。",
         ["步骤：拆卸探针卡", "步骤：清洗与晾干"]),
        ("E4305 模块通信超时处理", ["E4305"],
         "检查通信线缆连接；重插中继板；仍超时更换通信模块。",
         ["步骤：检查线缆", "步骤：更换通信模块"]),
    ]
    for i, (name, codes, solution, page_titles) in enumerate(demo):
        sop = Sop(name=name, alarm_codes=codes, solution=solution,
                  pages=[f"{j:04d}.png" for j in range(1, len(page_titles) + 1)])
        st.add_sop(sop)
        mdir = st.media_dir(sop.id)
        mdir.mkdir(parents=True, exist_ok=True)
        for j, t in enumerate(page_titles, 1):
            make_page(mdir / f"{j:04d}.png", f"{name} · 第{j}页",
                      [f"{t}", "1. 按SOP步骤执行操作", "2. 完成后确认报警是否消除",
                       "3. 若未消除，升级处理并记录"])
    st.add_feedback("E9999 wafer map 读取失败", "机台AL-07，周六夜班出现，搜不到SOP")
    fb = st.add_feedback("E4304 风扇报警一直出现", "已按SOP处理，建议补充滤网型号")
    st.set_feedback_status(fb.id, True)
    st.set_feedback_remark(fb.id, "已在 E4304 SOP 中补充滤网型号信息。")
    st.add_search_log("E4303", True)
    st.add_search_log("430", True)
    st.add_search_log("E5201 chamber 门传感器异常", False)
    st.add_search_log("E4304", True)
    return st


def main() -> int:
    shots = ROOT / "shots"
    shots.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="qs_shots_"))
    app = QApplication(sys.argv)
    from app.ui.theme import STYLE
    app.setStyleSheet(STYLE)

    try:
        build_demo(tmp / "Data")
        cfg = Config(tmp / "config.json")
        from app.ui.main_window import MainWindow
        from app.ui.editor_dialog import EditorDialog
        from app.ui.settings_dialog import SettingsDialog

        win = MainWindow(data_dir_override=tmp / "Data", cfg=cfg)
        win.resize(1180, 760)

        def snap(name: str, w=None) -> None:
            target = w or win
            target.grab().save(str(shots / f"{name}.png"))
            print("截取", name)

        # 01 首页
        win.show_page(0)
        snap("01_首页_搜索")
        # 02 多结果列表（模糊搜索 430 命中 3 条）
        win.search_page.input.setText("430")
        win.search_page._do_search()
        snap("02_搜索结果列表")
        # 03 未找到提示
        win.search_page.input.setText("E5201 chamber 门传感器异常")
        win.search_page._do_search()
        snap("03_未找到提示")
        # 04 查看器
        sops = win.store.sops
        win.open_sop(sops[0].id)
        snap("04_SOP查看器")
        # 05 SOP库
        win.show_page(1)
        win.library_page.refresh()
        snap("05_SOP库")
        # 06 编辑器
        dlg = EditorDialog(win.store, cfg, sop=sops[0], parent=win)
        dlg.resize(860, 700)
        dlg.show()
        app.processEvents()
        snap("06_SOP编辑器", dlg)
        dlg.close()
        # 07 反馈
        win.show_page(2)
        win.feedback_page.refresh()
        snap("07_反馈记录")
        # 08 搜索记录
        win.show_page(3)
        win.searchlog_page.refresh()
        snap("08_搜索记录")
        # 09 设置
        sd = SettingsDialog(cfg, win.store, win)
        sd.resize(640, 480)
        sd.show()
        app.processEvents()
        snap("09_设置", sd)
        sd.close()
        print("完成 →", shots)
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
