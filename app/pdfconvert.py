"""PDF → PNG 转换：用 pypdfium2（宽松许可、轻量、无需外部依赖）逐页渲染。

- 仅在上传 PDF 的电脑需要本组件；产线电脑只看图片。
- pypdfium2 为可选依赖：未安装时给出明确指引，不影响软件其它功能。
- 渲染按目标宽度等比缩放（PDF 页面单位为 pt，1pt=1/72 英寸）。
- 与 PPT 转换共用 ConversionError 类型；在后台线程中执行，不阻塞界面。
"""
from __future__ import annotations

from pathlib import Path

from .converter import ConversionError


def _ensure_pypdfium2():
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        raise ConversionError(
            "PDF 转换组件（pypdfium2）未安装。\n"
            "请在工程师电脑上执行：pip install pypdfium2\n"
            "或改用“添加图片”导入已转好的图片。")


def _page_width_pt(page) -> float:
    try:
        w, _h = page.get_size()
        return float(w)
    except Exception:
        try:
            return float(page.get_width())
        except Exception:
            return 0.0


def convert_pdf(pdf_path: Path, out_dir: Path, width: int = 1440,
                progress=None, cancel_flag=None) -> list[Path]:
    """把 PDF 每页渲染为 PNG，返回按页序排列的文件列表。

    progress(i, n)      每渲染完一页回调
    cancel_flag()       返回 True 时停止剩余页（已渲染的页保留）
    """
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    if not pdf_path.exists():
        raise ConversionError(f"文件不存在：{pdf_path}")
    _ensure_pypdfium2()
    out_dir.mkdir(parents=True, exist_ok=True)

    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
    except Exception as e:
        raise ConversionError(f"无法打开 PDF（文件可能损坏或加密）：{e}")

    exported: list[Path] = []
    try:
        total = len(pdf)
        if total == 0:
            raise ConversionError("该 PDF 没有任何页面（0 页）。")
        for i in range(total):
            if cancel_flag is not None and cancel_flag():
                break
            page = pdf[i]
            try:
                w_pt = _page_width_pt(page)
                scale = max(0.1, width / w_pt) if w_pt > 0 else 2.0
                bitmap = page.render(scale=scale)
                pil = bitmap.to_pil()
                fp = out_dir / f"{i + 1:04d}.png"
                pil.save(str(fp))
            except ConversionError:
                raise
            except Exception as e:
                raise ConversionError(f"第 {i + 1} 页渲染失败：{e}")
            if not (fp.exists() and fp.stat().st_size > 0):
                raise ConversionError(f"第 {i + 1} 页渲染失败（未生成文件）")
            exported.append(fp)
            if progress is not None:
                progress(i + 1, total)
        return exported
    finally:
        try:
            pdf.close()
        except Exception:
            pass
