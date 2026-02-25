@echo off
chcp 65001 >nul 2>nul
rem ============================================================
rem  Green 磁盘空间可视化工具 - 多架构一键打包脚本
rem  自动检测已安装的 Python 架构 (x86/amd64/arm64)，
rem  为每个架构分别构建独立 .exe 可执行文件。
rem
rem  前提条件：
rem    - 安装 Windows Python Launcher (py.exe)
rem    - 安装目标架构的 Python 3.8+，例如：
rem        amd64 : python.org 下载 "Windows installer (64-bit)"
rem        x86   : python.org 下载 "Windows installer (32-bit)"
rem        arm64 : python.org 下载 "Windows installer (ARM64)"
rem ============================================================
cd /d "%~dp0"

echo.
echo  =====================================================
echo   Green Disk Visualizer - Multi-Arch Build Tool
echo  =====================================================
echo.

rem ── 检测 py launcher ────────────────────────────────────
where py >nul 2>nul
if %errorlevel% neq 0 (
    echo  [ERROR] 未找到 Python Launcher (py.exe)。
    echo          请从 python.org 安装 Python 时勾选 "py launcher"。
    echo.
    pause
    exit /b 1
)

rem ── 清理旧构建 ──────────────────────────────────────────
echo  [CLEAN] 正在清理旧构建文件...
if exist build rmdir /s /q build >nul 2>nul
if exist dist  rmdir /s /q dist  >nul 2>nul
for %%f in (*.spec) do del /f /q "%%f" >nul 2>nul
echo          清理完成。
echo.

set BUILD_COUNT=0
set BUILD_SUCCESS=

rem ── 依次尝试三种架构 ────────────────────────────────────
call :try_build "amd64" "-3-64"
call :try_build "x86"   "-3-32"
call :try_build "arm64" "-3-arm64"

rem ── 汇总结果 ────────────────────────────────────────────
echo.
echo  =====================================================
if %BUILD_COUNT%==0 (
    echo   未成功构建任何架构！
    echo   请确认已安装至少一个架构的 Python 3.8+。
    echo  =====================================================
    pause
    exit /b 1
)

echo   构建完成！成功构建 %BUILD_COUNT% 个架构：
echo.
echo   输出目录: dist\
echo.
if exist "dist\GreenDiskVisualizer_amd64.exe" (
    echo     GreenDiskVisualizer_amd64.exe   (64 位 Intel/AMD)
)
if exist "dist\GreenDiskVisualizer_x86.exe" (
    echo     GreenDiskVisualizer_x86.exe     (32 位 Intel/AMD)
)
if exist "dist\GreenDiskVisualizer_arm64.exe" (
    echo     GreenDiskVisualizer_arm64.exe   (64 位 ARM)
)
echo.
echo   以上文件可在对应架构的 Windows 7+ 电脑上直接运行，
echo   无需安装 Python 或任何其他软件。
echo  =====================================================
echo.
pause
exit /b 0


rem ============================================================
rem  子例程：尝试用指定架构的 Python 构建
rem  参数: %~1 = 架构名 (amd64/x86/arm64)
rem        %~2 = py launcher 参数 (-3-64/-3-32/-3-arm64)
rem ============================================================
:try_build
set ARCH=%~1
set PY_FLAG=%~2

echo  ──────────────────────────────────────────────────────
echo  [%ARCH%] 正在检测 Python %PY_FLAG% ...

rem 测试该架构的 Python 是否存在
py %PY_FLAG% -c "import sys; print(f'Python {sys.version}')" >nul 2>nul
if %errorlevel% neq 0 (
    echo  [%ARCH%] 未安装，跳过。
    echo.
    goto :eof
)

rem 显示检测到的版本信息
echo  [%ARCH%] 检测到:
py %PY_FLAG% -c "import sys, struct; print(f'         Python {sys.version}'); print(f'         {struct.calcsize(\"P\")*8}-bit')"

rem 安装 PyInstaller
echo  [%ARCH%] 正在安装 PyInstaller...
py %PY_FLAG% -m pip install pyinstaller --quiet --disable-pip-version-check >nul 2>nul
if %errorlevel% neq 0 (
    echo  [%ARCH%] PyInstaller 安装失败，跳过。
    echo.
    goto :eof
)

rem 清理该架构的临时文件
if exist "build_%ARCH%" rmdir /s /q "build_%ARCH%" >nul 2>nul

rem 执行打包
echo  [%ARCH%] 正在打包（可能需要 1-2 分钟）...
py %PY_FLAG% -m PyInstaller ^
    --onefile ^
    --noconsole ^
    --name "GreenDiskVisualizer_%ARCH%" ^
    --distpath "dist" ^
    --workpath "build_%ARCH%" ^
    --specpath "build_%ARCH%" ^
    --clean ^
    main.py >nul 2>&1

if %errorlevel% neq 0 (
    echo  [%ARCH%] 打包失败！
    echo.
    goto :eof
)

echo  [%ARCH%] 打包成功 -^> dist\GreenDiskVisualizer_%ARCH%.exe
echo.

rem 清理临时构建目录
if exist "build_%ARCH%" rmdir /s /q "build_%ARCH%" >nul 2>nul

set /a BUILD_COUNT+=1
goto :eof
