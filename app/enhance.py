"""SOP 图片高清修复（本地离线，不上传任何数据）。

算法：GitHub 开源项目 Saafke/FSRCNN_Tensorflow 的 FSRCNN x2 超分模型
（38KB 小模型，专为 CPU 实时设计），经 OpenCV dnn_superres 推理后
再做一次轻量锐化，明显提升文字/线条类 SOP 页面的清晰度。

性能与设计：
- cv2 只在本模块内懒加载，产线电脑查看 SOP 的路径完全不碰它；
- 修复是工程师端的**一次性**操作（按 SOP 逐页处理），后台线程执行，
  1440×1080 一页约 1 秒（办公级 CPU 实测），带进度与取消；
- cv2.imread/imwrite 在 Windows 上不支持中文路径，统一用
  imdecode/imencode + numpy 中转。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

MODEL_NAME = "FSRCNN_x2.pb"
SR_MODEL_KEY = "fsrcnn"
SR_SCALE = 2

# 可处理的静态图片后缀（gif 动图跳过）
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


class EnhanceError(Exception):
    """带用户可读信息的高清修复失败。"""


def model_path() -> Path:
    from .config import model_file
    return model_file(MODEL_NAME)


def _model_for_cv() -> Path:
    """cv2 的 dnn 在 Windows 上打不开非 ASCII 路径的模型文件，
    遇到中文安装路径时把模型缓存一份到临时目录（ASCII 路径）再加载。"""
    mp = model_path()
    try:
        str(mp).encode("ascii")
        return mp
    except UnicodeEncodeError:
        pass
    import shutil
    import tempfile
    cache = Path(tempfile.gettempdir()) / "Quicksearch_sr" / MODEL_NAME
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        if not cache.exists() or cache.stat().st_size != mp.stat().st_size:
            shutil.copyfile(mp, cache)
        return cache
    except OSError:
        return mp   # 缓存失败就按原路径尝试，报错交给上层提示


def enhance_available() -> bool:
    try:
        import cv2  # noqa: F401
    except Exception:
        return False
    return model_path().exists()


def _imread(path: Path) -> "np.ndarray":
    data = np.fromfile(str(path), dtype=np.uint8)   # 中文路径安全
    img = cv2_imdecode(data)
    if img is None:
        raise EnhanceError(f"无法读取图片：{path.name}")
    return img


def cv2_imdecode(data):
    import cv2
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _imwrite(path: Path, img) -> None:
    import cv2
    ext = path.suffix.lower() or ".png"
    ok, buf = cv2.imencode(ext, img)
    if not ok:
        raise EnhanceError(f"编码图片失败：{path.name}")
    buf.tofile(str(path))   # 中文路径安全


def enhance_image(src: Path, dst: Path) -> None:
    """把一张图超分 2 倍 + 轻锐化后写到 dst。"""
    try:
        import cv2
    except Exception:
        raise EnhanceError("高清修复组件（OpenCV）未安装。")
    mp = model_path()
    if not mp.exists():
        raise EnhanceError(f"超分模型缺失：{mp.name}")

    img = _imread(src)
    h, w = img.shape[:2]
    if h * w > 6000 * 6000:
        raise EnhanceError(f"图片过大跳过：{src.name}")

    sr = cv2.dnn_superres.DnnSuperResImpl_create()
    sr.readModel(str(_model_for_cv()))
    sr.setModel(SR_MODEL_KEY, SR_SCALE)
    up = sr.upsample(img)

    # 轻量锐化：补偿超分的轻微平滑，让文字边缘更挺
    blur = cv2.GaussianBlur(up, (0, 0), 1.0)
    sharp = cv2.addWeighted(up, 1.3, blur, -0.3, 0)
    _imwrite(dst, sharp)


def enhance_sop_pages(page_paths: list[Path], progress=None,
                      cancel_flag=None) -> tuple[int, int, list[str]]:
    """逐页修复。返回 (成功数, 跳过数, 错误列表)。

    先写临时文件再原子替换，中途失败/取消不会损坏原图。
    progress(i, n) 每完成一页回调；cancel_flag() 返回 True 停止剩余页。
    """
    done = skipped = 0
    errors: list[str] = []
    total = len(page_paths)
    for i, p in enumerate(page_paths, 1):
        if cancel_flag is not None and cancel_flag():
            break
        if p.suffix.lower() not in SUPPORTED_EXTS or not p.exists():
            skipped += 1
        else:
            tmp = p.with_name(p.stem + ".enhance_tmp" + p.suffix)
            try:
                enhance_image(p, tmp)
                tmp.replace(p)
                done += 1
            except Exception as e:
                errors.append(f"{p.name}: {e}")
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
        if progress is not None:
            progress(i, total)
    return done, skipped, errors
