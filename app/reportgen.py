"""烽火台异常报告生成器：根据汇报内容与截图自动生成单文件 HTML 报告。

- 截图以 base64 内嵌，报告是**单个文件**，浏览器直接打开、可直接打印成 PDF、
  微信/邮件发出去对方不需要任何附加文件。
- 离线生成，无任何外部依赖。
"""
from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path

from .beacons import Beacon


def _img_tag(path: Path, index: int) -> str:
    """把一张截图转成内嵌 base64 的 <img>；读取失败时给占位说明。"""
    try:
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        ext = path.suffix.lower().lstrip(".") or "png"
        mime = "jpeg" if ext in ("jpg", "jpeg") else ("gif" if ext == "gif" else "png")
        return (f'<div class="shot"><div class="shot-title">截图 {index}</div>'
                f'<img src="data:image/{mime};base64,{b64}" alt="截图 {index}"></div>')
    except Exception:
        return f'<div class="shot missing">截图 {index} 读取失败</div>'


def build_report_html(beacon: Beacon, shot_paths: list[Path]) -> str:
    """根据汇报内容生成完整 HTML 文本。"""
    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    def esc(s: str) -> str:
        return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))

    rows = [
        ("日期", beacon.date or "—"),
        ("机台", beacon.machine or "—"),
        ("Recipe", beacon.recipe or "—"),
        ("测试OD", beacon.test_od or "—"),
        ("针卡", beacon.probe_card or "—"),
        ("针卡长度", beacon.probe_card_len or "—"),
    ]
    info_rows = "".join(
        f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in rows)

    desc = esc(beacon.description).replace("\n", "<br>") if beacon.description else "（未填写）"
    shots_html = "".join(
        _img_tag(p, i) for i, p in enumerate(shot_paths, 1)) or '<p class="none">未附截图</p>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>异常汇报 {esc(beacon.date)} {esc(beacon.machine)}</title>
<style>
  body {{ font-family: "Microsoft YaHei", "微软雅黑", sans-serif; color: #1f2733;
         margin: 0; background: #f2f4f8; }}
  .page {{ max-width: 900px; margin: 24px auto; background: #fff;
          border: 1px solid #d9e0ea; border-radius: 10px; padding: 32px 40px; }}
  .brand {{ color: #68758a; font-size: 12px; margin-bottom: 4px; }}
  h1 {{ font-size: 26px; margin: 4px 0 2px; color: #17335f; }}
  .meta {{ color: #68758a; font-size: 13px; margin-bottom: 18px; }}
  h2 {{ font-size: 17px; color: #17335f; border-left: 4px solid #2f6fed;
       padding-left: 10px; margin: 26px 0 10px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 15px; }}
  th, td {{ border: 1px solid #d9e0ea; padding: 8px 12px; text-align: left; }}
  th {{ background: #f2f6fd; color: #274b8f; width: 130px; white-space: nowrap; }}
  .desc {{ font-size: 15px; line-height: 1.7; background: #f7f9fc;
          border: 1px solid #e3eaf3; border-radius: 8px; padding: 12px 16px; }}
  .shot {{ margin: 14px 0; }}
  .shot-title {{ color: #68758a; font-size: 13px; margin-bottom: 4px; }}
  img {{ max-width: 100%; border: 1px solid #d9e0ea; border-radius: 6px; }}
  .none {{ color: #9aa7ba; }}
  .footer {{ margin-top: 28px; color: #9aa7ba; font-size: 12px;
            border-top: 1px dashed #d9e0ea; padding-top: 10px; }}
  @media print {{ body {{ background: #fff; }} .page {{ border: none; margin: 0; }} }}
</style>
</head>
<body>
<div class="page">
  <div class="brand">Quicksearch · 烽火台</div>
  <h1>线上异常汇报</h1>
  <div class="meta">编号：{esc(beacon.id)}　|　汇报生成时间：{gen_time}</div>

  <h2>基本信息</h2>
  <table>{info_rows}</table>

  <h2>问题描述 / 现象</h2>
  <div class="desc">{desc}</div>

  <h2>异常截图（{len(shot_paths)} 张）</h2>
  {shots_html}

  <div class="footer">本报告由 Quicksearch 烽火台自动生成 · 生成时间 {gen_time} · Author: Morris Hou</div>
</div>
</body>
</html>"""


def generate_report(beacon: Beacon, shot_paths: list[Path], out_html: Path) -> Path:
    """生成报告文件并返回路径（覆盖写）。"""
    out_html = Path(out_html)
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(build_report_html(beacon, shot_paths), encoding="utf-8")
    return out_html
