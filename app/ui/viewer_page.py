"""SOP 查看器：翻页浏览图片（含 PPT 转出的图片）。

操作：
- 鼠标滚轮：以光标为锚点直接放大/缩小（缩放过程用快速插值保证流畅，
  停止滚动约 0.2 秒后自动换成精细平滑渲染）；
- 左键按住拖拽：平移画面；
- ←/→、PgUp/PgDn：翻页；Esc：返回；Ctrl+0 / "适应窗口"：复位。

内存策略：同一时间只解码**当前一页**并保留一份缩放后的 QPixmap，
翻页/关闭时旧图立即释放，不看整本、不占整本内存。
"""
from __future__ import annotations

import os

from PySide6.QtCore import QPoint, QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QImageReader, QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from app.store import Sop, Store
from .common import elide, warn


class ViewerPage(QWidget):
    back_requested = Signal()

    ZOOM_MIN, ZOOM_MAX = 0.25, 8.0
    WHEEL_STEP = 1.15          # 每格滚轮的缩放系数
    SMOOTH_DELAY_MS = 220      # 停止缩放后换精细渲染的延时

    def __init__(self, store: Store, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self._sop: Sop | None = None
        self._idx = 0
        self._img = None            # 当前页原图（QImage），缩放时不再重复读盘
        self._fit = True            # 适应窗口模式
        self._zoom = 1.0            # 相对适应尺寸的倍率（非适应模式时有效）
        self._dragging = False
        self._drag_gp = QPoint()
        self._drag_h = 0
        self._drag_v = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 16)
        root.setSpacing(8)

        # ---- 顶栏 ----
        top = QHBoxLayout()
        self.back_btn = QPushButton("← 返回")
        self.back_btn.clicked.connect(self.back_requested.emit)
        self.name_label = QLabel("")
        self.name_label.setObjectName("Big")
        self.code_label = QLabel("")
        self.code_label.setObjectName("Muted")
        top.addWidget(self.back_btn)
        top.addSpacing(6)
        top.addWidget(self.name_label)
        top.addSpacing(6)
        top.addWidget(self.code_label)
        top.addStretch(1)

        self.ext_btn = QPushButton("打开原文件")
        self.ext_btn.setToolTip("用系统默认程序（PowerPoint/WPS）打开保留的 PPT 原文件")
        self.ext_btn.clicked.connect(self._open_original)
        self.page_label = QLabel("")
        self.page_label.setObjectName("PageBadge")
        self.prev_btn = QPushButton("◀ 上一页")
        self.next_btn = QPushButton("下一页 ▶")
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn.clicked.connect(self.next_page)
        self.zoom_out_btn = QPushButton("－")
        self.zoom_in_btn = QPushButton("＋")
        self.fit_btn = QPushButton("适应窗口")
        self.zoom_out_btn.clicked.connect(lambda: self._zoom_step(1 / 1.25))
        self.zoom_in_btn.clicked.connect(lambda: self._zoom_step(1.25))
        self.fit_btn.clicked.connect(self._fit_window)
        for w in (self.page_label, self.prev_btn, self.next_btn, self.zoom_out_btn,
                  self.zoom_in_btn, self.fit_btn, self.ext_btn):
            top.addWidget(w)
        root.addLayout(top)

        # ---- 解决方式横幅 ----
        self.solution_label = QLabel("")
        self.solution_label.setObjectName("SolutionBanner")
        self.solution_label.setWordWrap(True)
        self.solution_label.setVisible(False)
        root.addWidget(self.solution_label)

        # ---- 画布 ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignCenter)
        self.canvas.setObjectName("Muted")
        self.canvas.setText("在“快速查找”或“SOP 库”中打开一个 SOP 即可在此查看\n"
                            "滚轮缩放 · 按住左键拖动平移 · ←/→ 翻页")
        self.scroll.setWidget(self.canvas)
        root.addWidget(self.scroll, 1)

        # 缩放停止后换精细渲染的定时器
        self._smooth_timer = QTimer(self)
        self._smooth_timer.setSingleShot(True)
        self._smooth_timer.setInterval(self.SMOOTH_DELAY_MS)
        self._smooth_timer.timeout.connect(lambda: self._render(fast=False))

        # 拖拽平移
        self.scroll.viewport().installEventFilter(self)

        # 快捷键
        for seq, fn in (
            (QKeySequence(Qt.Key_Left), self.prev_page),
            (QKeySequence(Qt.Key_PageUp), self.prev_page),
            (QKeySequence(Qt.Key_Right), self.next_page),
            (QKeySequence(Qt.Key_PageDown), self.next_page),
            (QKeySequence(Qt.Key_Escape), self.back_requested.emit),
            (QKeySequence("Ctrl+0"), self._fit_window),
        ):
            sc = QShortcut(seq, self)
            sc.activated.connect(fn)

    # ---------- 打开/关闭 ----------
    def clear(self) -> None:
        """清空查看器（切换数据目录时使用）。"""
        self._sop = None
        self._idx = 0
        self._img = None
        self.canvas.setPixmap(QPixmap())
        self.canvas.setText("在“快速查找”或“SOP 库”中打开一个 SOP 即可在此查看")
        self.name_label.setText("")
        self.code_label.setText("")
        self.solution_label.setVisible(False)
        self.ext_btn.setVisible(False)
        self.page_label.setText("")
        self._set_buttons()

    def set_sop(self, sop: Sop) -> None:
        self._sop = sop
        self._idx = 0
        self.name_label.setText(elide(sop.name, 30))
        self.code_label.setText("报警代码：" + "、".join(sop.alarm_codes) if sop.alarm_codes else "")
        if sop.solution:
            self.solution_label.setText("💡 解决方式：" + sop.solution)
            self.solution_label.setVisible(True)
        else:
            self.solution_label.setVisible(False)
        self.ext_btn.setVisible(bool(sop.originals))
        self._load_page()

    # ---------- 翻页 ----------
    def prev_page(self) -> None:
        self._goto(self._idx - 1)

    def next_page(self) -> None:
        self._goto(self._idx + 1)

    def _goto(self, idx: int) -> None:
        if not self._sop or not self._sop.pages:
            return
        idx = max(0, min(idx, len(self._sop.pages) - 1))
        if idx == self._idx and self._img is not None:
            return
        self._idx = idx
        self._load_page()

    # ---------- 渲染 ----------
    def _load_page(self) -> None:
        if not self._sop:
            self.page_label.setText("")
            self._set_buttons()
            return
        n = len(self._sop.pages)
        if n == 0:
            self._img = None
            self.canvas.setPixmap(QPixmap())
            self.canvas.setText("该 SOP 暂无页面内容\n（只有“解决方式”文字说明）")
            self.page_label.setText("第 0 / 0 页")
            self._set_buttons()
            return
        self.page_label.setText(f"第 {self._idx + 1} / {n} 页")
        path = self.store.page_path(self._sop, self._idx)
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        img = reader.read()
        if img.isNull():
            self._img = None
            self.canvas.setPixmap(QPixmap())
            self.canvas.setText(f"图片加载失败：\n{path.name}")
        else:
            # 超大图先降采样到 4K 宽以内，避免弱配电脑解码/缩放卡顿
            if img.width() > 4096:
                img = img.scaledToWidth(4096, Qt.SmoothTransformation)
            self._img = img
            self._fit = True
            self._zoom = 1.0
            self._render(fast=False)
        self._set_buttons()

    def _set_buttons(self) -> None:
        n = len(self._sop.pages) if self._sop else 0
        self.prev_btn.setEnabled(self._sop is not None and self._idx > 0)
        self.next_btn.setEnabled(self._sop is not None and self._idx < n - 1)
        has_img = self._img is not None
        for w in (self.zoom_in_btn, self.zoom_out_btn, self.fit_btn):
            w.setEnabled(has_img)

    def _fit_scale(self) -> float:
        if self._img is None:
            return 1.0
        avail = self.scroll.viewport().size() * 0.96
        iw, ih = max(1, self._img.width()), max(1, self._img.height())
        return min(avail.width() / iw, avail.height() / ih)

    def _render(self, fast: bool = False) -> None:
        """按当前模式渲染。fast=True 用最近邻插值（缩放过程中跟手），否则平滑。"""
        if self._img is None:
            return
        scale = self._fit_scale() if self._fit else self._fit_scale() * self._zoom
        target = self._img.size() * scale
        mode = Qt.FastTransformation if fast else Qt.SmoothTransformation
        pm = QPixmap.fromImage(self._img).scaled(target, Qt.KeepAspectRatio, mode)
        self.canvas.setPixmap(pm)
        self.canvas.setText("")

    # ---------- 缩放 ----------
    def _zoom_step(self, factor: float) -> None:
        self._zoom_at(factor, anchor_viewport=None)

    def _zoom_at(self, factor: float, anchor_viewport: QPoint | None) -> None:
        """以视口内 anchor_viewpoint 点（None=中心）为锚缩放 factor 倍。"""
        if self._img is None:
            return
        if self._fit and factor < 1.0:
            return   # 已是适应窗口，再缩小无意义
        vp = self.scroll.viewport()
        if anchor_viewport is None:
            anchor_viewport = QPoint(vp.width() // 2, vp.height() // 2)

        pm_old = self.canvas.pixmap()
        # 锚点对应的图像比例位置（0..1，可越界）
        if pm_old is not None and not pm_old.isNull():
            lp = self.canvas.mapFrom(self.scroll.viewport(), anchor_viewport)
            off_x = (self.canvas.width() - pm_old.width()) / 2.0
            off_y = (self.canvas.height() - pm_old.height()) / 2.0
            fx = (lp.x() - off_x) / max(1, pm_old.width())
            fy = (lp.y() - off_y) / max(1, pm_old.height())
        else:
            fx = fy = 0.5

        if self._fit:
            self._zoom = 1.0
            self._fit = False
        self._zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self._zoom * factor))
        self._render(fast=True)
        self._smooth_timer.start()

        # 滚动条锚定：让刚才那个图像点继续停留在光标下
        pm_new = self.canvas.pixmap()
        if pm_new is not None and not pm_new.isNull():
            off_x = (self.canvas.width() - pm_new.width()) / 2.0
            off_y = (self.canvas.height() - pm_new.height()) / 2.0
            want_x = int(fx * pm_new.width() + off_x - anchor_viewport.x())
            want_y = int(fy * pm_new.height() + off_y - anchor_viewport.y())
            self.scroll.horizontalScrollBar().setValue(want_x)
            self.scroll.verticalScrollBar().setValue(want_y)

    def _fit_window(self) -> None:
        self._fit = True
        self._zoom = 1.0
        self._smooth_timer.stop()
        self._render(fast=False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit:
            self._render(fast=False)

    # ---------- 滚轮缩放 / 拖拽平移（在 viewport 事件过滤器里拦截，避免被滚动条吞掉） ----------
    def eventFilter(self, obj, ev) -> bool:
        if obj is self.scroll.viewport():
            t = ev.type()
            if t == QEvent.Wheel and self._img is not None:
                delta = ev.angleDelta().y()
                if delta:
                    factor = self.WHEEL_STEP if delta > 0 else 1 / self.WHEEL_STEP
                    self._zoom_at(factor, anchor_viewport=ev.position().toPoint())
                    return True   # 消费掉，不让 QScrollArea 滚动
                return True
            if t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
                self._dragging = True
                self._drag_gp = ev.globalPosition().toPoint()
                self._drag_h = self.scroll.horizontalScrollBar().value()
                self._drag_v = self.scroll.verticalScrollBar().value()
                self.scroll.viewport().setCursor(Qt.ClosedHandCursor)
            elif t == QEvent.MouseMove and self._dragging:
                d = ev.globalPosition().toPoint() - self._drag_gp
                self.scroll.horizontalScrollBar().setValue(self._drag_h - d.x())
                self.scroll.verticalScrollBar().setValue(self._drag_v - d.y())
                return True
            elif t == QEvent.MouseButtonRelease and ev.button() == Qt.LeftButton and self._dragging:
                self._dragging = False
                self.scroll.viewport().unsetCursor()
        return super().eventFilter(obj, ev)

    # ---------- 原文件 ----------
    def _open_original(self) -> None:
        if not (self._sop and self._sop.originals):
            return
        rel = self._sop.originals[-1]["file"]
        path = self.store.media_dir(self._sop.id) / rel
        try:
            os.startfile(str(path))   # Windows：调用系统默认程序
        except Exception as e:
            warn(self, "打开失败", f"无法打开原文件：\n{path}\n\n{e}")
