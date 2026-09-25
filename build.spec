# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：python -m PyInstaller --noconfirm --clean build.spec
# 产出：dist/Quicksearch.exe（单文件，免安装，无外部依赖）

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'win32com.client',
        'pythoncom',
        'pywintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'cv2',
        'pytest',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.Qt3DCore',
        'PySide6.QtMultimedia',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Quicksearch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets\\icon.ico',
    version='assets\\version_info.txt',
)
