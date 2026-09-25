"""PPT → PNG 转换：调用本机 PowerPoint 或 WPS 的 COM 接口，把每一页导出为 PNG。

设计要点：
- 仅在上传 PPT 的电脑（工程师电脑）需要装 Office/WPS；产线电脑只看图片，零依赖。
- 使用晚期绑定（Dispatch），不生成 gen_py 缓存，打包成 exe 后也能正常工作。
- 如果电脑上同时开着用户的 PowerPoint，我们只关闭自己打开的演示文稿，
  绝不退出用户正在使用的程序实例。
- 转换在后台线程中执行（线程内 CoInitialize），不阻塞界面。
"""
from __future__ import annotations

from pathlib import Path

# 依次尝试的程序 ID：微软 PowerPoint →金山 WPS 演示（不同版本 ProgID）
PPT_PROGIDS = (
    "PowerPoint.Application",
    "KWPP.Application",
    "KWPP.Application.1",
    "WPP.Application",
)


class ConversionError(Exception):
    """带用户可读信息的转换失败。"""


def _find_app():
    """返回 (app, progid)。找不到可用组件时抛 ConversionError。"""
    try:
        import pythoncom  # noqa: F401
        import win32com.client
    except ImportError:
        raise ConversionError("转换组件缺失（pywin32 未正确打包），请重新打包软件。")
    last_err: Exception | None = None
    for progid in PPT_PROGIDS:
        try:
            app = win32com.client.Dispatch(progid)
            _ = app.Presentations.Count  # 探活
            return app, progid
        except Exception as e:  # 未安装该组件
            last_err = e
    raise ConversionError(
        "本机未检测到 PowerPoint 或 WPS，无法自动转换 PPT。\n"
        "请先安装 Office/WPS，或改用“添加图片”直接导入图片文件。"
    )


def convert_ppt(ppt_path: Path, out_dir: Path, width: int = 1440,
                progress=None, cancel_flag=None) -> list[Path]:
    """把 PPT 每页导出为 PNG，返回按页序排列的文件列表。

    progress(i, n)      每转完一页回调（在调用线程中）
    cancel_flag()       返回 True 时停止剩余页（已转出的页保留）
    """
    ppt_path = Path(ppt_path)
    out_dir = Path(out_dir)
    if not ppt_path.exists():
        raise ConversionError(f"文件不存在：{ppt_path}")
    out_dir.mkdir(parents=True, exist_ok=True)

    import pythoncom

    pythoncom.CoInitialize()
    app = None
    pres = None
    opened_here = False
    had_others = False
    try:
        app, _progid = _find_app()
        try:
            had_others = app.Presentations.Count > 0
        except Exception:
            had_others = False

        # Open(FileName, ReadOnly, Untitled, WithWindow)
        pres = app.Presentations.Open(str(ppt_path), True, False, False)
        opened_here = True

        try:
            sw = float(pres.PageSetup.SlideWidth)
            sh = float(pres.PageSetup.SlideHeight)
        except Exception:
            sw, sh = 960.0, 720.0
        height = max(1, round(width * sh / max(sw, 1.0)))

        total = int(pres.Slides.Count)
        exported: list[Path] = []
        for i in range(1, total + 1):
            if cancel_flag is not None and cancel_flag():
                break
            fp = out_dir / f"{i:04d}.png"
            try:
                pres.Slides(i).Export(str(fp), "PNG", int(width), int(height))
            except Exception as e:
                raise ConversionError(f"第 {i} 页导出失败：{e}")
            if not (fp.exists() and fp.stat().st_size > 0):
                raise ConversionError(f"第 {i} 页导出失败（未生成文件）")
            exported.append(fp)
            if progress is not None:
                progress(i, total)
        return exported
    finally:
        try:
            if opened_here and pres is not None:
                pres.Close()
                if not had_others:
                    try:
                        if app.Presentations.Count == 0:
                            app.Quit()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
