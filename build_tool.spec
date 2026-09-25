# -*- mode: python ; coding: utf-8 -*-
# 独立高清修复工具打包：python -m PyInstaller --noconfirm --clean build_tool.spec
# 产出：dist/SOP高清修复工具.exe（仅工程师电脑需要，含 OpenCV + 超分模型）

a = Analysis(
    ['enhance_tool.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/models/FSRCNN_x2.pb', 'models'),   # 开源超分模型（Saafke/FSRCNN_Tensorflow）
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
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
    name='SOP高清修复工具',
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
