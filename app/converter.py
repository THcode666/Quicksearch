"""PPT → PNG 转换：调用本机 PowerPoint 或 WPS 的 COM 接口，把每一页导出为 PNG。

设计要点：
- 仅在上传 PPT 的电脑（工程师电脑）需要装 Office/WPS；产线电脑只看图片，零依赖。
- 使用晚期绑定（Dispatch），不生成 gen_py 缓存，打包成 exe 后也能正常工作。
- 依次尝试多个 ProgID；某个组件“能启动但打不开/0 页”时自动换下一个再试。
- 兼容“受保护的视图”：从网络/微信等途径下载的文件带锁定标记，直接 Open 会被拦截，
  自动改走 ProtectedViewWindows 兜底。
- 页数读取带短暂重试（部分版本异步加载，刚打开时 Count 可能为 0）。
- 如果电脑上同时开着用户的 PowerPoint，我们只关闭自己打开的演示文稿，
  绝不退出用户正在使用的程序实例。
- 转换在后台线程中执行（线程内 CoInitialize），不阻塞界面。
"""
from __future__ import annotations

import time
from pathlib import Path

# 依次尝试的程序 ID：微软 PowerPoint → 金山 WPS 演示（不同版本 ProgID）
PPT_PROGIDS = (
    "PowerPoint.Application",
    "KWPP.Application",
    "KWPP.Application.1",
    "WPP.Application",
)

SLIDE_COUNT_RETRIES = 8      # 页数读取重试次数（异步加载兼容）
SLIDE_COUNT_INTERVAL = 0.25  # 每次间隔秒数


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


def _read_slide_count(pres) -> int:
    """读页数；部分版本刚打开时异步加载为 0，短暂轮询等待。"""
    for i in range(SLIDE_COUNT_RETRIES):
        try:
            n = int(pres.Slides.Count)
        except Exception:
            n = 0
        if n > 0:
            return n
        time.sleep(SLIDE_COUNT_INTERVAL)
    return 0


def _open_presentation(app, ppt_path: Path):
    """打开演示文稿。受保护视图（文件被 Windows 锁定标记拦截）时走兜底通道。"""
    try:
        return app.Presentations.Open(str(ppt_path), True, False, False)
    except Exception as open_err:
        try:
            pv = app.ProtectedViewWindows.Open(str(ppt_path))
            return pv.Edit()
        except Exception:
            raise ConversionError(
                f"无法打开 PPT 文件：\n{ppt_path.name}\n\n{open_err}\n\n"
                "常见原因：文件来自网络/微信等，被“受保护的视图”拦截。\n"
                "处理：右键该文件 → 属性 → 勾选“解除锁定”后重试；"
                "或用 PowerPoint/WPS 打开后另存一份再导入。")


def _try_open_with(progid: str, ppt_path: Path):
    """用指定组件尝试打开并确认页数；返回 (app, pres, total) 或 (None, None, 原因)。"""
    import win32com.client
    app = win32com.client.Dispatch(progid)
    try:
        # ppAlertsNone：自动化期间禁止 PowerPoint 弹模态提示——
        # 否则打开损坏/受锁文件时的弹窗会永久阻塞后台转换线程
        app.DisplayAlerts = 1
    except Exception:
        pass   # WPS 等组件可能不支持该属性
    pres = _open_presentation(app, ppt_path)
    total = _read_slide_count(pres)
    if total > 0:
        return app, pres, total
    # 0 页：关掉这份，交给上层换下一个组件再试
    try:
        pres.Close()
    except Exception:
        pass
    return None, None, f"{progid} 打开后页数为 0"


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
    total = 0
    zero_page_notes: list[str] = []
    try:
        # 逐个组件尝试：能启动但打不开/0 页的，换下一个
        last_open_err: Exception | None = None
        for progid in PPT_PROGIDS:
            try:
                app, pres, total = _try_open_with(progid, ppt_path)
                break
            except ConversionError as e:
                zero_page_notes.append(str(e))
                last_open_err = e
                pres = None
                continue
            except Exception as e:
                last_open_err = e
                pres = None
                continue
        if app is None or pres is None:
            raise ConversionError(
                f"无法打开 PPT：{ppt_path.name}\n"
                f"{last_open_err}\n"
                "提示：若文件来自网络/聊天工具，请右键→属性→解除锁定后重试；"
                "也可用 PowerPoint/WPS 打开另存一份再导入。")

        try:
            had_others = app.Presentations.Count > 1
        except Exception:
            had_others = False
        opened_here = True

        try:
            sw = float(pres.PageSetup.SlideWidth)
            sh = float(pres.PageSetup.SlideHeight)
        except Exception:
            sw, sh = 960.0, 720.0
        height = max(1, round(width * sh / max(sw, 1.0)))

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
