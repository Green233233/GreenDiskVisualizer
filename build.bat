@echo off
chcp 65001 >nul 2>nul
rem ============================================================
rem  Green 磁盘空间可视化工具 - 一键打包脚本
rem  将 Python 源码打包为独立 .exe，无需安装 Python 即可运行
rem ============================================================
cd /d "%~dp0"

echo.
echo  ========================================
echo   Green Disk Visualizer - Build Tool
echo  ========================================
echo.

rem ── 检测 Python ──────────────────────────────────────────
set PYTHON=
where python >nul 2>nul
if %errorlevel%==0 (
    set PYTHON=python
    goto :found_python
)
where py >nul 2>nul
if %errorlevel%==0 (
    set PYTHON=py
    goto :found_python
)
echo  [ERROR] 未找到 Python，请先安装 Python 3.8 或更高版本。
echo          下载地址: https://www.python.org/downloads/
pause
exit /b 1

:found_python
echo  [INFO] 使用 Python: %PYTHON%
%PYTHON% --version
echo.

rem ── 安装 PyInstaller ────────────────────────────────────
echo  [1/3] 正在检查并安装 PyInstaller...
%PYTHON% -m pip install pyinstaller --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo  [ERROR] PyInstaller 安装失败，请检查网络连接和 pip 配置。
    pause
    exit /b 1
)
echo        PyInstaller 已就绪。
echo.

rem ── 清理旧构建 ──────────────────────────────────────────
echo  [2/3] 正在清理旧构建文件...
if exist build rmdir /s /q build >nul 2>nul
if exist dist  rmdir /s /q dist  >nul 2>nul
if exist GreenDiskVisualizer.spec del /f /q GreenDiskVisualizer.spec >nul 2>nul
echo        清理完成。
echo.

rem ── 执行打包 ────────────────────────────────────────────
echo  [3/3] 正在打包为独立可执行文件（可能需要 1-2 分钟）...
echo.
%PYTHON% -m PyInstaller ^
    --onefile ^
    --noconsole ^
    --name "GreenDiskVisualizer" ^
    --clean ^
    main.py

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] 打包失败，请检查上方错误信息。
    pause
    exit /b 1
)

echo.
echo  ========================================
echo   打包完成！
echo  ========================================
echo.
echo  可执行文件位置:
echo    dist\GreenDiskVisualizer.exe
echo.
echo  该文件可在任何 Windows 7+ 电脑上直接运行，
echo  无需安装 Python 或任何其他软件。
echo.
pause
