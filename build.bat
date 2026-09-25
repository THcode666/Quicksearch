@echo off
rem Quicksearch 一键打包：生成 dist\Quicksearch.exe（主程序）+ dist\SOP高清修复工具.exe
cd /d "%~dp0"

echo [1/4] 生成图标...
python tools\make_icon.py
if errorlevel 1 (
    echo 图标生成失败
    exit /b 1
)

echo [2/4] 检查超分模型（首次会自动下载，约38KB）...
python tools\download_model.py
if errorlevel 1 (
    echo 模型下载失败（高清修复工具打包需要它；不影响主程序）
    exit /b 1
)

echo [3/4] 打包主程序 Quicksearch.exe ...
python -m PyInstaller --noconfirm --clean build.spec
if errorlevel 1 (
    echo 主程序打包失败
    exit /b 1
)

echo [4/4] 打包高清修复工具 ...
python -m PyInstaller --noconfirm build_tool.spec
if errorlevel 1 (
    echo 高清修复工具打包失败
    exit /b 1
)

echo.
echo 完成：
echo   %~dp0dist\Quicksearch.exe        （产线电脑用）
echo   %~dp0dist\SOP高清修复工具.exe   （工程师电脑用，可选）
