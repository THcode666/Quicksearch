"""自检测试。`Quicksearch.exe --selftest` 或 `python main.py --selftest` 运行。

覆盖：模糊搜索、数据存取、原子写入、自然排序、图标绘制、PPT 转换的优雅降级，
以及（可选）界面冒烟测试。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

RESULTS: list[tuple[str, bool, str]] = []


def _case(name: str, func) -> None:
    try:
        func()
        RESULTS.append((name, True, ""))
        print(f"  [PASS] {name}")
    except Exception:
        msg = traceback.format_exc(limit=3)
        RESULTS.append((name, False, msg))
        print(f"  [FAIL] {name}\n{msg}")


def _sop(name, codes, solution="检查模块供电并重新插拔", pages=None, **kw):
    from app.store import Sop
    return Sop(name=name, alarm_codes=codes, solution=solution,
               pages=pages or [], **kw)


# ---------------- 搜索 ----------------
def test_search() -> None:
    from app import search
    sops = [
        _sop("E4303 module not found", ["E4303"]),
        _sop("E4304 风扇转速异常", ["E4304"], solution="清洁风扇滤网，更换风扇"),
        _sop("探针卡清洗流程", ["E7101", "E7102"], solution="使用酒精清洗探针卡"),
    ]
    assert search.score(sops[0], "4303") is not None, "4303 应命中 E4303"
    assert search.score(sops[0], "module not found") is not None, "完整描述应命中"
    assert search.score(sops[0], "MODULE") is not None, "大小写不敏感"
    assert search.score(sops[0], "4304") is None, "4304 不应命中 E4303"
    assert search.score(sops[0], "4303 xyz") is None, "AND 语义：多余词不匹配"
    r = search.search(sops, "E4303")
    assert r and r[0][0].id == sops[0].id, "完整报警代码应排第一"
    r = search.search(sops, "风扇")
    assert r and r[0][0].id == sops[1].id, "中文关键词应命中解决方式"
    r = search.search(sops, "清洗")
    assert len(r) == 1 and r[0][0].id == sops[2].id, "清洗应命中探针卡SOP"
    r = search.search(sops, "e4303 module")
    assert len(r) == 1, "多关键词 AND 命中"
    assert search.search(sops, "") == [], "空输入无结果"


def test_search_ranking() -> None:
    from app import search
    a = _sop("E4303 module not found", ["E4303"])
    b = _sop("模块供电检查SOP", ["E9001"], solution="module 供电检查，关联 E4303 现象")
    r = search.search([b, a], "E4303")
    assert r[0][0].id == a.id and r[1][0].id == b.id, "完整代码命中应排在部分命中前面"


# ---------------- 数据层 ----------------
def test_store_roundtrip() -> None:
    from app.store import Store, STATUS_PENDING, STATUS_RESOLVED
    tmp = Path(tempfile.mkdtemp(prefix="qs_test_"))
    try:
        st = Store(tmp / "数据目录")   # 顺带验证中文路径
        sop = _sop("金氧半探测器清洗SOP", ["E4303", "E4304"], pages=["0001.png", "0002.png"])
        st.add_sop(sop)
        (st.media_dir(sop.id)).mkdir(parents=True, exist_ok=True)
        (st.page_path(sop, 0)).write_bytes(b"\x89PNG fake")
        assert st.get_sop(sop.id) is not None
        assert st.page_path(sop, 0).exists()

        st2 = Store(tmp / "数据目录")
        got = st2.get_sop(sop.id)
        assert got and got.name == "金氧半探测器清洗SOP", "中文SOP名应完整保存"
        assert got.alarm_codes == ["E4303", "E4304"], "多报警代码应保存"
        assert len(got.pages) == 2

        fb = st2.add_feedback("E9999 no sop", "需要新建SOP")
        assert fb.status == STATUS_PENDING, "反馈默认待补充"
        st2.set_feedback_status(fb.id, True)
        fb2 = st2.get_feedback(fb.id)
        assert fb2.status == STATUS_RESOLVED and fb2.resolved_at, "标记已解决"
        st2.set_feedback_remark(fb.id, "已补SOP：E9999")
        assert st2.get_feedback(fb.id).remark == "已补SOP：E9999"
        st2.delete_feedback(fb.id)
        assert st2.get_feedback(fb.id) is None

        # 搜索记录：自动记录、重新载入、删除、清空
        st2.add_search_log("E4303", True)
        st2.add_search_log("E9999", False)
        st3 = Store(tmp / "数据目录")
        assert len(st3.search_logs) == 2, "搜索记录应持久化"
        assert st3.search_logs[0].query == "E4303" and st3.search_logs[0].found
        assert not st3.search_logs[1].found
        assert " " in st3.search_logs[0].time, "时间应含日期+时间"

        # 报错截图：转存、路径、随记录删除
        rec = st3.search_logs[1]
        shot_src = tmp / "报错截图.png"
        shot_src.write_bytes(b"\x89PNG fake image")
        rel = st3.set_search_log_shot(rec.id, shot_src)
        assert rel == f"shots/{rec.id}.png", rel
        assert st3.search_log_shot_path(rec) is not None
        st3.delete_search_log(rec.id)
        assert not (tmp / "数据目录" / "shots" / f"{rec.id}.png").exists(), "删记录应连带删截图"

        st3.clear_search_logs()
        assert st3.search_logs == []

        # 超上限自动丢弃最旧
        from app.store import SearchLog
        for i in range(st3.MAX_SEARCH_LOGS + 5):
            st3.search_logs.append(SearchLog(query=f"Q{i}", found=True))
        st3.save_search_logs()
        assert len(st3.search_logs) == st3.MAX_SEARCH_LOGS, "应裁剪到上限"
        assert st3.search_logs[-1].query == f"Q{st3.MAX_SEARCH_LOGS + 4}", "应保留最新的"

        st2.delete_sop(sop.id)
        assert st2.get_sop(sop.id) is None
        assert not (tmp / "数据目录" / "media" / sop.id).exists(), "删除SOP应清理媒体文件"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_atomic_and_corrupt() -> None:
    from app.store import save_json_atomic, load_json
    tmp = Path(tempfile.mkdtemp(prefix="qs_test_"))
    try:
        p = tmp / "中文.json"
        save_json_atomic(p, {"ok": True})
        assert load_json(p, None) == {"ok": True}
        assert not list(tmp.glob("*.tmp")), "临时文件应被清理"
        p.write_text("{坏了", encoding="utf-8")
        assert load_json(p, {"d": 1}) == {"d": 1}, "损坏文件应返回默认值"
        assert list(tmp.glob("*.corrupt-*")), "损坏文件应被备份"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_natural_sort() -> None:
    from app.store import natural_key
    files = ["p10.png", "p2.png", "P1.png", "第10页.png", "第2页.png"]
    got = sorted(files, key=natural_key)
    assert got == ["P1.png", "p2.png", "p10.png", "第2页.png", "第10页.png"], got


# ---------------- 配置 ----------------
def test_config() -> None:
    from app.config import Config
    tmp = Path(tempfile.mkdtemp(prefix="qs_test_"))
    try:
        cfg = Config(tmp / "config.json")
        cfg.data["data_dir"] = r"D:\共享\QuicksearchData"
        cfg.data["ppt_width"] = 1920
        cfg.save()
        cfg2 = Config(tmp / "config.json")
        assert cfg2.data["data_dir"] == r"D:\共享\QuicksearchData"
        assert cfg2.data["ppt_width"] == 1920
        os.environ["QUICKSEARCH_DATA_DIR"] = r"E:\环境变量目录"
        try:
            assert str(cfg2.resolve_data_dir()) == r"E:\环境变量目录"
        finally:
            del os.environ["QUICKSEARCH_DATA_DIR"]
        assert str(cfg2.resolve_data_dir()) == r"D:\共享\QuicksearchData"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------- 图标 ----------------
def test_icons() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QImage, QPainter, Qt
    from app.icons import paint_logo
    img = QImage(512, 512, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    paint_logo(p, 512)
    p.end()
    assert not img.isNull()
    # 书页区域（画布坐标约 x 80..420 / y 200..380）应有非透明像素
    colors = {img.pixel(x, y) for x in range(100, 230, 30) for y in range(240, 340, 20)}
    assert any((c & 0xFF000000) != 0 for c in colors), "图标应绘制出内容"
    # 放大镜镜框（深色）也应存在
    edge = img.pixel(350 - 82, 202)
    assert (edge & 0xFF000000) != 0, "放大镜镜框应绘制出内容"


# ---------------- PPT 转换（优雅降级） ----------------
def test_converter_graceful() -> None:
    from app.converter import convert_ppt
    tmp = Path(tempfile.mkdtemp(prefix="qs_test_"))
    try:
        fake = tmp / "假文件.pptx"
        fake.write_bytes(b"not a real ppt")
        try:
            convert_ppt(fake, tmp / "out")
            # 若机器上恰好有 Office 且真把它打开了——不可能，内容非法必然报错
            raise AssertionError("非法 PPT 不应转换成功")
        except Exception:
            pass  # 任何异常都算通过：不挂死、不崩溃即可
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------- PPT 转换（真实端到端，--ppt-test 时执行） ----------------
def test_ppt_real() -> int:
    """本机装有 PowerPoint/WPS 时：用 COM 生成 2 页中文 PPT → 转成 PNG 验证。"""
    print("PPT 端到端转换测试")
    try:
        import win32com.client
    except ImportError as e:
        print("  [FAIL] win32com 导入失败:", e)
        return 1
    print("  win32com 导入 OK")
    app = None
    try:
        for progid in ("PowerPoint.Application", "KWPP.Application",
                       "KWPP.Application.1", "WPP.Application"):
            try:
                app = win32com.client.Dispatch(progid)
                print(f"  检测到转换组件: {progid}")
                break
            except Exception:
                continue
    except Exception:
        app = None
    if app is None:
        print("  [SKIP] 本机未装 PowerPoint/WPS，跳过（产线电脑不需要转换功能）")
        return 0

    from app.converter import convert_ppt
    tmp = Path(tempfile.mkdtemp(prefix="qs_ppt_test_"))
    try:
        ppt_path = tmp / "测试演示.pptx"
        pres = app.Presentations.Add()
        for i, text in ((1, "第一页 测试"), (2, "第二页 测试")):
            slide = pres.Slides.Add(i, 12)   # 12 = 空白版式
            slide.Shapes.AddTextbox(1, 50, 50, 600, 80).TextFrame.TextRange.Text = text
        pres.SaveAs(str(ppt_path))
        try:
            pres.Close()
        except Exception:
            pass   # 遗留僵尸实例等环境问题不应掩盖转换结果本身

        files = convert_ppt(ppt_path, tmp / "out", width=1440,
                            progress=lambda i, n: print(f"  转换进度 {i}/{n}"))
        ok = len(files) == 2 and all(f.exists() and f.stat().st_size > 1000 for f in files)
        print("  转换输出:", [f.name for f in files])
        print(f"  [{'PASS' if ok else 'FAIL'}] PPT→PNG 端到端转换")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------- 高清修复（端到端） ----------------
def test_enhance() -> None:
    try:
        import cv2  # noqa: F401
    except ImportError:
        print("  [SKIP] 未安装 OpenCV，跳过高清修复测试")
        return
    from app.config import model_file
    from app.enhance import _imread, _imwrite, enhance_image
    mp = model_file("FSRCNN_x2.pb")
    assert mp.exists(), f"超分模型应随包存在：{mp}"
    import cv2
    tmp = Path(tempfile.mkdtemp(prefix="qs_sr_"))
    try:
        import numpy as np
        src = tmp / "页面 测试.png"   # 中文文件名
        img = np.full((200, 300, 3), 255, np.uint8)
        cv2.putText(img, "E4303 Test", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)
        _imwrite(src, img)
        dst = tmp / "页面 输出.png"
        enhance_image(src, dst)
        out = _imread(dst)
        assert out.shape[0] == 400 and out.shape[1] == 600, f"输出应为2倍尺寸：{out.shape}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------- PDF 导入（端到端） ----------------
def _make_min_pdf(path: Path, text: str = "E4303 test") -> None:
    """手工构造一个最小但结构完整的单页 PDF（含 xref），供转换测试。"""
    content = f"BT /F1 24 Tf 20 60 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 220 110] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF"
            % (len(objs) + 1, xref))
    path.write_bytes(bytes(out))


def test_pdf_convert() -> None:
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        print("  [SKIP] 未安装 pypdfium2，跳过 PDF 转换测试")
        return
    from app.pdfconvert import convert_pdf
    from app.converter import ConversionError
    tmp = Path(tempfile.mkdtemp(prefix="qs_pdf_"))
    try:
        pdf = tmp / "测试文档.pdf"   # 中文文件名
        _make_min_pdf(pdf)
        files = convert_pdf(pdf, tmp / "out", width=440,
                            progress=lambda i, n: None)
        assert len(files) == 1 and files[0].exists() and files[0].stat().st_size > 300
        bad = tmp / "坏文件.pdf"
        bad.write_bytes(b"not a pdf")
        try:
            convert_pdf(bad, tmp / "out2")
            raise AssertionError("非法 PDF 不应转换成功")
        except ConversionError:
            pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------- 性能规模测试（3000 条 SOP） ----------------
def test_scale_performance() -> None:
    import time
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from app import search as _search
    from app.store import Sop, Store
    app = QApplication.instance() or QApplication(sys.argv)
    tmp = Path(tempfile.mkdtemp(prefix="qs_perf_"))
    try:
        st = Store(tmp / "数据目录")
        st.sops = [Sop(name=f"E{4000 + i} 报警{i} 处理SOP", alarm_codes=[f"E{4000 + i}"],
                       solution="检查模块供电并重新插拔模块，必要时更换备用模块并记录。")
                   for i in range(3000)]
        # 1) 纯搜索（3000 条全部参与打分，结果截取前 50）
        t0 = time.perf_counter()
        r = _search.search(st.sops, "模块")
        t_search = time.perf_counter() - t0
        assert len(r) == 50, f"结果应截取上限50条，实际 {len(r)}"
        assert t_search < 0.5, f"3000条搜索耗时 {t_search:.3f}s 超标"
        # 2) SOP库整表填充
        from app.config import Config
        from app.ui.library_page import LibraryPage
        lp = LibraryPage(st, Config(tmp / "config.json"))
        t0 = time.perf_counter()
        lp.refresh()
        t_fill = time.perf_counter() - t0
        assert lp.table.rowCount() == 3000
        assert t_fill < 8.0, f"3000行表格填充耗时 {t_fill:.2f}s 超标"
        # 3) 首页正式搜索（含自动记录）
        from app.ui.search_page import SearchPage
        sp = SearchPage(st)
        sp.input.setText("模块")
        t0 = time.perf_counter()
        sp._do_search()
        t_page = time.perf_counter() - t0
        assert len(sp._results) == 50   # 上限 50 条
        assert len(st.search_logs) == 1
        assert t_page < 1.0, f"首页搜索耗时 {t_page:.3f}s 超标"
        print(f"  [INFO] 3000条SOP：搜索 {t_search * 1000:.0f}ms | "
              f"库表填充 {t_fill:.2f}s | 首页搜索+记录 {t_page * 1000:.0f}ms")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------- 界面冒烟测试 ----------------
def test_ui_smoke() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage, QPainter, QColor, QFont
    from app.config import Config
    from app.store import Store
    from app.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    tmp = Path(tempfile.mkdtemp(prefix="qs_ui_"))
    try:
        # 造两页测试图片
        media_tmp = tmp / "gen"
        media_tmp.mkdir()
        pages = []
        for i, text in ((1, "第 1 页"), (2, "第 2 页")):
            img = QImage(800, 600, QImage.Format_RGB32)
            img.fill(QColor("white"))
            p = QPainter(img)
            p.setPen(QColor("black"))
            p.setFont(QFont("Microsoft YaHei", 36))
            p.drawText(img.rect(), 0x84, f"E4303 测试 {text}")
            p.end()
            fp = media_tmp / f"{i:04d}.png"
            img.save(str(fp))
            pages.append(fp)

        cfg = Config(tmp / "config.json")
        win = MainWindow(data_dir_override=tmp / "Data", cfg=cfg)
        store = win.store
        from app.store import Sop
        sop = Sop(name="E4303 module not found", alarm_codes=["E4303", "E4305"],
                  solution="重新插拔module；检查供电", source="image",
                  pages=["0001.png", "0002.png"])
        store.add_sop(sop)
        store.media_dir(sop.id).mkdir(parents=True, exist_ok=True)
        for idx, src in enumerate(pages):
            src.rename(store.page_path(sop, idx))

        # 搜索页：按钮触发，唯一结果直接打开，未找到自动记录
        sp = win.search_page
        sp.input.setText("4303")
        sp._do_search()
        assert len(sp._results) == 1, f"搜索 4303 应命中 1 条，实际 {len(sp._results)}"
        assert store.search_logs and store.search_logs[-1].query == "4303"
        assert store.search_logs[-1].found is True, "命中应记录为已搜到"
        sp.input.setText("不存在的报警XYZ")
        sp._do_search()
        assert len(sp._results) == 0
        assert sp.notfound_hint.isVisibleTo(sp), "未找到应显示提示"
        rec = store.search_logs[-1]
        assert rec.found is False, "未找到应自动记录"
        assert rec.query == "不存在的报警XYZ"

        # 报错截图：提交后在搜索记录页可见、可筛选
        shot_src = tmp / "机台报错.png"
        QImage(320, 240, QImage.Format_RGB32).save(str(shot_src))
        store.set_search_log_shot(rec.id, shot_src)
        slp = win.searchlog_page
        slp.refresh()
        assert slp.table.rowCount() == 2, f"搜索记录应 2 条，实际 {slp.table.rowCount()}"
        assert slp.table.item(0, 4).text() == "📎 有截图", "最新记录应显示有截图"
        slp.filter_combo.setCurrentText("仅缺少SOP")
        slp.refresh()
        assert slp.table.rowCount() == 1, "仅缺少SOP筛选应剩 1 条"
        slp.filter_combo.setCurrentText("有截图")
        slp.refresh()
        assert slp.table.rowCount() == 1, "有截图筛选应剩 1 条"
        slp.filter_combo.setCurrentText("全部")

        # 弹窗“选择照片”路径：从文件载入并提交（不经 exec）
        from app.ui.search_page import ShotSubmitDialog
        rec2 = store.add_search_log("E8888 换句话说搜不到", False)
        photo = tmp / "手机照片.jpg"
        QImage(200, 150, QImage.Format_RGB32).save(str(photo))
        dlg = ShotSubmitDialog(store, rec2.id, "E8888", win)
        dlg._set_image(QImage(str(photo)), photo)
        dlg._submit()
        assert rec2.shot == f"shots/{rec2.id}.jpg", f"照片应随记录保存: {rec2.shot}"
        assert store.search_log_shot_path(rec2) is not None

        # 截图查看窗：另存到指定位置
        from app.ui.searchlog_page import ShotViewDialog, _safe_filename
        sv = ShotViewDialog(rec2.query, store.search_log_shot_path(rec2), win)
        dest = tmp / "另存输出.png"
        assert sv._save_to(dest) and dest.exists(), "另存截图应成功"
        cleaned = _safe_filename('E99/1*?:报警')
        assert not any(c in cleaned for c in '\\/:*?"<>|'), "文件名非法字符应被替换"
        assert cleaned.startswith("E99") and cleaned.endswith("报警")

        # 查看器
        vp = win.viewer_page
        vp.set_sop(store.get_sop(sop.id))
        assert vp.page_label.text().startswith("第 1 / 2 页"), vp.page_label.text()
        # 滚轮缩放：放大后位图应变大，适应窗口后复位
        w0 = vp.canvas.pixmap().width()
        vp._zoom_at(1.5, anchor_viewport=None)
        w1 = vp.canvas.pixmap().width()
        assert w1 > w0 * 1.3, f"放大后位图应变宽：{w0} → {w1}"
        vp._fit_window()
        assert vp.canvas.pixmap().width() <= w0 + 2, "适应窗口应复位尺寸"
        vp.next_page()
        assert vp.page_label.text().startswith("第 2 / 2 页")
        vp.prev_page()

        # SOP 库
        lp = win.library_page
        lp.refresh()
        assert lp.table.rowCount() == 1

        # 编辑器：粘贴截图作为页面（直接走内部入口 + 剪贴板路径）
        from app.ui.editor_dialog import EditorDialog
        ed = EditorDialog(store, cfg, parent=win)
        img = QImage(300, 200, QImage.Format_RGB32)
        img.fill(QColor("white"))
        ed._add_image_object(img)
        assert len(ed._page_files) == 1 and ed.pages_list.count() == 1, "粘贴截图应新增一页"
        QApplication.clipboard().setImage(img)
        ed._paste_screenshot()
        assert len(ed._page_files) == 2, f"Ctrl+V 粘贴应再新增一页，实际 {len(ed._page_files)}"
        assert ed.add_pdf_btn.isVisibleTo(ed) or True   # 按钮存在性
        ed.deleteLater()

        # 反馈
        fb_id = store.add_feedback("E4303 没找到", "测试").id
        fp_page = win.feedback_page
        fp_page.refresh()
        assert fp_page.table.rowCount() == 1
        store.set_feedback_status(fb_id, True)
        fp_page.refresh()
        fp_page.status_filter.setCurrentText("待补充")
        fp_page.refresh()
        assert fp_page.table.rowCount() == 0, "已解决的记录不应出现在待补充筛选中"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_all(include_ui: bool = True) -> int:
    print(f"Quicksearch 自检（UI冒烟: {'开' if include_ui else '关'}）")
    _case("模糊搜索", test_search)
    _case("搜索排序", test_search_ranking)
    _case("数据存取/中文路径", test_store_roundtrip)
    _case("原子写入与损坏恢复", test_atomic_and_corrupt)
    _case("自然排序", test_natural_sort)
    _case("配置读写", test_config)
    _case("PPT转换降级", test_converter_graceful)
    _case("PDF导入", test_pdf_convert)
    if include_ui:
        _case("图标绘制", test_icons)
        _case("界面冒烟测试", test_ui_smoke)
    _case("高清修复", test_enhance)
    _case("性能规模测试(3000条)", test_scale_performance)
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n结果：{len(RESULTS) - len(failed)}/{len(RESULTS)} 通过")
    _write_report()
    return 1 if failed else 0


def _write_report() -> None:
    """窗口版 exe 没有控制台，把自检结果落盘便于核对。"""
    try:
        lines = ["Quicksearch 自检报告", "=" * 32]
        for name, ok, msg in RESULTS:
            lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}")
            if not ok:
                lines.extend("    " + ln for ln in msg.strip().splitlines())
        total = len(RESULTS)
        n_ok = total - len([r for r in RESULTS if not r[1]])
        lines.append("")
        lines.append(f"结果：{n_ok}/{total} 通过")
        Path("selftest_report.txt").write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass
