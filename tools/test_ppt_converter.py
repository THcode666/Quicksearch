"""检测 PowerPoint/WPS COM 可用性，并做一次 PPT→PNG 端到端转换测试。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    try:
        import win32com.client
    except ImportError as e:
        print("win32com 导入失败:", e)
        return 1
    print("win32com 导入 OK")

    app = None
    used = ""
    for progid in ("PowerPoint.Application", "KWPP.Application",
                   "KWPP.Application.1", "WPP.Application"):
        try:
            app = win32com.client.Dispatch(progid)
            n = app.Presentations.Count
            used = progid
            print(f"检测到转换组件: {progid} (当前打开演示文稿数={n})")
            break
        except Exception as e:
            print(f"不可用 {progid}: {repr(e)[:90]}")
    if app is None:
        print("结论：本机未安装 PowerPoint/WPS，转换测试跳过（软件会走“保留原文件”兜底逻辑）")
        return 0

    # 端到端：用 COM 新建一个 2 页 PPT → 用软件的 convert_ppt 转成 PNG
    from app.converter import convert_ppt

    tmp = Path(__import__("tempfile").mkdtemp(prefix="qs_ppt_test_"))
    ppt_path = tmp / "测试演示.pptx"
    try:
        pres = app.Presentations.Add()
        slide1 = pres.Slides.Add(1, 12)   # 12 = ppLayoutBlank
        slide1.Shapes.AddTextbox(1, 50, 50, 600, 80).TextFrame.TextRange.Text = "第一页 测试"
        slide2 = pres.Slides.Add(2, 12)
        slide2.Shapes.AddTextbox(1, 50, 50, 600, 80).TextFrame.TextRange.Text = "第二页 测试"
        pres.SaveAs(str(ppt_path))
        pres.Close()
        print("已生成测试 PPT:", ppt_path)

        out = tmp / "out"
        files = convert_ppt(ppt_path, out, width=1440,
                            progress=lambda i, n: print(f"  转换进度 {i}/{n}"))
        ok = len(files) == 2 and all(f.exists() and f.stat().st_size > 1000 for f in files)
        sizes = [f.stat().st_size for f in files]
        print("转换结果:", [f.name for f in files], "大小:", sizes)
        print("端到端转换测试:", "通过" if ok else "失败")
        return 0 if ok else 1
    except Exception as e:
        import traceback
        traceback.print_exc()
        return 1
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
