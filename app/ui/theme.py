"""界面主题（QSS）。样式集中在这里，改配色/字号只动这个文件。"""

ACCENT = "#2f6fed"
ACCENT_DARK = "#1e56c8"
BG = "#f2f4f8"
CARD = "#ffffff"
TEXT = "#1f2733"
MUTED = "#68758a"
BORDER = "#d9e0ea"

STATUS_COLORS = {
    "pending": ("#fff4e5", "#b25e09"),
    "resolved": ("#e8f7ee", "#1e7f4f"),
}

STYLE = f"""
* {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "SimSun", sans-serif;
    color: {TEXT};
    font-size: 14px;
    outline: none;
}}
QMainWindow, QDialog {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QLabel#Title {{ font-size: 30px; font-weight: 700; }}
QLabel#Subtitle {{ color: {MUTED}; font-size: 14px; }}
QLabel#CardTitle {{ font-size: 16px; font-weight: 600; }}
QLabel#Muted {{ color: {MUTED}; }}
QLabel#Big {{ font-size: 18px; font-weight: 600; }}

/* ---- 搜索 ---- */
QLineEdit#SearchInput {{
    background: {CARD}; border: 2px solid #c9d6ee; border-radius: 14px;
    padding: 12px 16px; font-size: 19px; selection-background-color: {ACCENT};
}}
QLineEdit#SearchInput:focus {{ border-color: {ACCENT}; }}
QPushButton#SearchButton {{
    background: {ACCENT}; border: none; border-radius: 12px; color: white;
    font-size: 17px; font-weight: 600; padding: 10px 28px; min-height: 24px;
}}
QPushButton#SearchButton:hover {{ background: {ACCENT_DARK}; }}
QPushButton#SearchButton:pressed {{ background: #17439f; }}
QLabel#NotFoundHint {{
    background: #fff4e5; border: 1px solid #f0c36d; border-radius: 12px;
    padding: 14px 16px; color: #b25e09; font-size: 15px;
}}
QListWidget#ResultList {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px;
    outline: none;
}}
QListWidget#ResultList::item {{ padding: 9px 12px; border-bottom: 1px solid #eef1f6; }}
QListWidget#ResultList::item:last {{ border-bottom: none; }}
QListWidget#ResultList::item:hover {{ background: #f3f7ff; }}
QListWidget#ResultList::item:selected {{ background: #eaf1ff; }}
QLabel#ResultName {{ font-size: 16px; font-weight: 600; background: transparent; }}
QLabel#ResultSub {{ color: {MUTED}; font-size: 13px; background: transparent; }}

/* ---- 导航 ---- */
QPushButton#NavButton {{
    text-align: left; padding: 13px 16px; border: none; border-radius: 10px;
    background: transparent; color: #3c4a5f; font-size: 15px;
}}
QPushButton#NavButton:hover {{ background: #e8edf6; }}
QPushButton#NavButton:checked {{ background: {ACCENT}; color: white; font-weight: 600; }}
QLabel#Brand {{ font-size: 15px; font-weight: 700; padding: 14px 10px 6px 10px; }}

/* ---- 按钮 ---- */
QPushButton {{
    background: {CARD}; border: 1px solid #cdd6e4; border-radius: 8px;
    padding: 7px 14px;
}}
QPushButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:disabled {{ color: #9aa7ba; border-color: #e3e8f0; background: #f6f8fb; }}
QPushButton#Primary {{ background: {ACCENT}; border: none; color: white; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {ACCENT_DARK}; color: white; }}
QPushButton#Danger:hover {{ border-color: #e5484d; color: #e5484d; }}
QPushButton#Warn {{ border-color: #f0c36d; color: #b25e09; background: #fffaf0; }}
QPushButton#Warn:hover {{ border-color: #b25e09; color: #b25e09; background: #fff4e5; }}

/* ---- 输入 ---- */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {{
    background: {CARD}; border: 1px solid #cdd6e4; border-radius: 8px; padding: 6px 10px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: white; border: 1px solid {BORDER}; }}

/* ---- 表格 ---- */
QTableWidget {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px;
    gridline-color: #eef1f6; selection-background-color: #e3edff; selection-color: {TEXT};
    alternate-background-color: #fafbfd;
}}
QTableWidget::item {{ padding: 4px 6px; }}
QHeaderView::section {{
    background: #f7f9fc; border: none; border-bottom: 1px solid {BORDER};
    padding: 8px 6px; font-weight: 600; color: #42506a;
}}

/* ---- 滚动条 ---- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #c4cedd; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #c4cedd; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {ACCENT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- 其他 ---- */
QFrame#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel#Flash {{ color: #1e7f4f; font-weight: 600; }}
QLabel#SolutionBanner {{
    background: #eef4ff; border: 1px solid #c9d9f5; border-radius: 10px;
    padding: 10px 12px; color: #274b8f;
}}
QLabel#PageBadge {{
    background: #eef1f6; border-radius: 8px; padding: 4px 10px; color: #42506a; font-weight: 600;
}}
QProgressBar {{ border: none; background: #e6ebf3; border-radius: 5px; height: 10px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
"""
