"""主窗口：左侧导航 + 四个页面（快速查找 / SOP库 / 反馈记录 / SOP查看）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QDialog, QFrame, QHBoxLayout,
                               QLabel, QMainWindow, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from app.config import APP_TITLE, APP_VERSION, Config
from app.security import PasswordGate
from app.store import Store
from .feedback_page import FeedbackPage
from .library_page import LibraryPage
from .search_page import SearchPage
from .searchlog_page import SearchLogPage
from .settings_dialog import SettingsDialog
from .viewer_page import ViewerPage


class MainWindow(QMainWindow):
    def __init__(self, data_dir_override: Path | None = None,
                 cfg: Config | None = None, parent=None):
        super().__init__(parent)
        self.cfg = cfg or Config()
        data_dir = Path(data_dir_override) if data_dir_override else self.cfg.resolve_data_dir()
        self.store = Store(data_dir)
        self.pwd_gate = PasswordGate(data_dir)
        self._library_unlocked = False   # 离开 SOP 库页面即重新上锁

        self.setWindowTitle(APP_TITLE)
        from app.icons import make_icon
        self.setWindowIcon(make_icon())
        self.setMinimumSize(960, 620)
        self.resize(1120, 740)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---- 左侧导航 ----
        nav = QFrame()
        nav.setFixedWidth(192)
        nav.setStyleSheet("QFrame { background: #e9edf4; border-right: 1px solid #d9e0ea; }")
        nav_lay = QVBoxLayout(nav)
        nav_lay.setContentsMargins(12, 12, 12, 12)
        nav_lay.setSpacing(6)

        brand = QLabel("📘 Quicksearch")
        brand.setObjectName("Brand")
        nav_lay.addWidget(brand)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for text, page_idx in (("🔍  快速查找", 0), ("📚  SOP 库", 1),
                               ("📝  反馈记录", 2), ("🕘  搜索记录", 3)):
            btn = QPushButton(text)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            self.nav_group.addButton(btn)
            self.nav_buttons.append(btn)
            nav_lay.addWidget(btn)
        self.nav_buttons[0].setChecked(True)
        nav_lay.addStretch(1)
        self.settings_btn = QPushButton("⚙  设置")
        self.settings_btn.setObjectName("NavButton")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.clicked.connect(self._open_settings)
        nav_lay.addWidget(self.settings_btn)
        lay.addWidget(nav)

        # ---- 分隔线 ----
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setStyleSheet("color: #d9e0ea;")
        lay.addWidget(line)

        # ---- 页面 ----
        self.stack = QStackedWidget()
        self.search_page = SearchPage(self.store)
        self.library_page = LibraryPage(self.store, self.cfg)
        self.feedback_page = FeedbackPage(self.store)
        self.searchlog_page = SearchLogPage(self.store)
        self.viewer_page = ViewerPage(self.store)
        for p in (self.search_page, self.library_page, self.feedback_page,
                  self.searchlog_page, self.viewer_page):
            self.stack.addWidget(p)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # ---- 信号 ----
        self.search_page.open_sop.connect(self.open_sop)
        self.library_page.open_sop.connect(self.open_sop)
        self.viewer_page.back_requested.connect(self._back_from_viewer)
        for i, btn in enumerate(self.nav_buttons):
            btn.clicked.connect(lambda _=False, idx=i: self.show_page(idx))

        sc = QShortcut(QKeySequence("Ctrl+F"), self)
        sc.activated.connect(self._focus_search)

        self._prev_page_index = 0
        self._update_statusbar()

        # 右下角署名
        self.author_label = QLabel("Author: Morris Hou")
        self.author_label.setStyleSheet(
            "color:#9aa7ba; font-size:12px; padding:0 10px 2px 0; background:transparent;")
        self.statusBar().addPermanentWidget(self.author_label)

    # ---------- 页面切换 ----------
    def _reload_store(self) -> None:
        """切页/打开SOP前从共享盘重读数据，另一台电脑的更新无需重启即可见。
        共享盘暂时不可达时继续用内存数据，不打断操作。"""
        try:
            self.store.reload()
        except OSError:
            pass

    def _enter_library_with_password(self, password: str) -> bool:
        """校验 SOP 库密码，正确则解锁本次进入。"""
        if self.pwd_gate.verify(password):
            self._library_unlocked = True
            return True
        return False

    def _ask_library_password(self) -> bool:
        """弹出密码对话框；无界面场景（自测/截图）直接视为取消。"""
        if not self.isVisible():
            return False
        from .password_dialog import PasswordDialog
        dlg = PasswordDialog(self.pwd_gate, self)
        return dlg.exec() == QDialog.Accepted

    def _sync_nav_selection(self) -> None:
        """导航按钮选中状态与当前实际页面保持一致（密码取消时回退）。"""
        idx = self.stack.currentIndex()
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == idx)

    def show_page(self, index: int) -> None:
        """index: 0查找 1库 2反馈 3搜索记录。SOP 库需密码解锁，离开即重新上锁。"""
        if index == 1 and not self._library_unlocked:
            if not self._ask_library_password():
                self._sync_nav_selection()
                return
            self._library_unlocked = True
        else:
            if index != 1:
                self._library_unlocked = False
        self._reload_store()
        if self.stack.currentWidget() is self.viewer_page:
            self._prev_page_index = index
        else:
            self._prev_page_index = self.nav_index()
        self.stack.setCurrentIndex(index)
        widget = self.stack.widget(index)
        if hasattr(widget, "refresh"):
            widget.refresh()

    def nav_index(self) -> int:
        w = self.stack.currentWidget()
        return self.stack.indexOf(w) if w is not self.viewer_page else self._prev_page_index

    def _back_from_viewer(self) -> None:
        idx = self._prev_page_index if 0 <= self._prev_page_index <= 3 else 0
        self._reload_store()
        self.stack.setCurrentIndex(idx)
        widget = self.stack.widget(idx)
        if hasattr(widget, "refresh"):
            widget.refresh()

    def open_sop(self, sop_id: str) -> None:
        self._reload_store()
        sop = self.store.get_sop(sop_id)
        if sop is None:
            from .common import warn
            warn(self, "提示", "该 SOP 不存在（可能已被删除），请刷新。")
            return
        if self.stack.currentWidget() is not self.viewer_page:
            self._prev_page_index = max(0, self.stack.currentIndex())
        self.viewer_page.set_sop(sop)
        self.stack.setCurrentWidget(self.viewer_page)
        for b in self.nav_buttons:
            b.setChecked(False)

    def _focus_search(self) -> None:
        self.show_page(0)

    # ---------- 设置 ----------
    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.pwd_gate, self.cfg, self.store, self)
        dlg.exec()
        if dlg.data_dir_changed:
            self.apply_data_dir(Path(self.cfg.resolve_data_dir()))

    def apply_data_dir(self, new_dir: Path) -> None:
        """切换数据目录（共享部署时使用），所有页面重新加载数据。
        密码跟随数据目录，切换后重新上锁。"""
        self.store = Store(new_dir)
        self.pwd_gate = PasswordGate(new_dir)
        self._library_unlocked = False
        self.search_page.set_store(self.store)
        self.library_page.set_store(self.store)
        self.feedback_page.set_store(self.store)
        self.searchlog_page.set_store(self.store)
        self.viewer_page.store = self.store
        self.viewer_page.clear()
        self._update_statusbar()
        self.show_page(0)

    def _update_statusbar(self) -> None:
        sb = self.statusBar()
        sb.setStyleSheet("color:#68758a; font-size:12px;")
        dir_text = str(self.store.data_dir)
        if len(dir_text) > 72:
            dir_text = dir_text[:24] + "…" + dir_text[-45:]
        sb.showMessage(f"数据目录：{dir_text}      Quicksearch v{APP_VERSION}")

    # ---------- 单实例唤醒 ----------
    def activate(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.show_page(0)
