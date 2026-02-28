@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

echo.
echo  =====================================================
echo   Green Disk Visualizer - Multi-Arch Build Tool
echo  =====================================================
echo.

rem Check Python Launcher
where py >nul 2>nul
if errorlevel 1 (
    echo  [ERROR] Python Launcher ^(py.exe^) not found.
    echo          Install Python from python.org and enable "py launcher".
    echo.
    pause
    exit /b 1
)

rem Read version from main.py (e.g. "Alpha v0.3.3" -> "Alpha_v0.3.3")
set "VER_FNAME=Alpha_v0.3.3"
for /f "tokens=2 delims=^" %%a in ('findstr /b "_VERSION" main.py 2^>nul') do set "VER=%%a"
if defined VER set "VER_FNAME=%VER: =_%"

rem Clean previous outputs
echo  [CLEAN] Removing previous build outputs...
if exist build rmdir /s /q build >nul 2>nul
if exist dist  rmdir /s /q dist  >nul 2>nul
for %%f in (*.spec) do del /f /q "%%f" >nul 2>nul
echo          Done.
echo.

rem 从 icon.png 生成 icon.ico（exe 图标 + 窗口图标）
set "ICON_ICO="
if exist "icon.png" (
    echo  [ICON] Generating icon.ico from icon.png...
    py -m pip install Pillow --quiet --disable-pip-version-check >nul 2>nul
    py build_icon_ico.py >nul 2>nul
    if exist "icon.ico" set "ICON_ICO=1" & echo          icon.ico created.
)

set BUILD_COUNT=0

rem Try all target architectures
call :try_build "amd64" "-3-64"
call :try_build "x86"   "-3-32"
call :try_build "arm64" "-3-arm64"

echo.
echo  =====================================================
if %BUILD_COUNT%==0 (
    echo   No architecture was successfully built.
    echo   Make sure at least one Python 3.8+ target is installed.
    echo  =====================================================
    pause
    exit /b 1
)

echo   Build completed. Successful targets: %BUILD_COUNT%
echo.
echo   Output folder: dist\
echo.
if exist "dist\GreenDiskVisualizer_%VER_FNAME%_amd64.exe" (
    echo     GreenDiskVisualizer_%VER_FNAME%_amd64.exe   ^(64-bit Intel/AMD^)
)
if exist "dist\GreenDiskVisualizer_%VER_FNAME%_x86.exe" (
    echo     GreenDiskVisualizer_%VER_FNAME%_x86.exe     ^(32-bit Intel/AMD^)
)
if exist "dist\GreenDiskVisualizer_%VER_FNAME%_arm64.exe" (
    echo     GreenDiskVisualizer_%VER_FNAME%_arm64.exe   ^(64-bit ARM^)
)
echo.
echo  =====================================================
echo.
pause
exit /b 0

:try_build
set "ARCH=%~1"
set "PY_FLAG=%~2"
set "EXPECTED_BITS="
if /I "%ARCH%"=="amd64" set "EXPECTED_BITS=64"
if /I "%ARCH%"=="x86" set "EXPECTED_BITS=32"
if /I "%ARCH%"=="arm64" set "EXPECTED_BITS=64"

echo  -----------------------------------------------------
echo  [%ARCH%] Checking Python %PY_FLAG% ...

set "PY_CHECK="
for /f "delims=" %%I in ('py %PY_FLAG% -c "import struct, platform; print('PY_OK ' + str(struct.calcsize('P')*8) + ' ' + platform.machine())" 2^>^&1') do (
    set "PY_CHECK=%%I"
)
echo "%PY_CHECK%" | findstr /c:"PY_OK " >nul
if errorlevel 1 (
    echo  [%ARCH%] Not installed, skipped.
    echo.
    goto :eof
)

if defined EXPECTED_BITS (
    echo "%PY_CHECK%" | findstr /c:"PY_OK %EXPECTED_BITS% " >nul
    if errorlevel 1 (
        echo  [%ARCH%] Found runtime does not match expected %EXPECTED_BITS%-bit, skipped.
        echo.
        goto :eof
    )
)

echo  [%ARCH%] Found and matched:
py %PY_FLAG% -c "import sys, struct, platform; print('         Python ' + sys.version); print('         ' + str(struct.calcsize('P')*8) + '-bit ' + platform.machine())"

echo  [%ARCH%] Installing/updating PyInstaller...
py %PY_FLAG% -m pip install pyinstaller --quiet --disable-pip-version-check >nul 2>nul
if errorlevel 1 (
    echo  [%ARCH%] Failed to install PyInstaller, skipped.
    echo.
    goto :eof
)

if exist "build_%ARCH%" rmdir /s /q "build_%ARCH%" >nul 2>nul

echo  [%ARCH%] Building executable ^(1-2 minutes^)...
set "BUILD_LOG=build_%ARCH%_log.txt"
set "ICON_ARGS="
if defined ICON_ICO if exist "icon.ico" (
    rem 使用相对路径，避免 PyInstaller 在 build_ARCH 下查找 icon
    set "ICON_ARGS=--icon=icon.ico --add-data ""icon.png;."" --add-data ""icon.ico;."""
)
rem specpath 放在项目根，使 datas 中的 icon.png 从项目根解析，避免在 build_ARCH 下找不到
py %PY_FLAG% -m PyInstaller ^
    --onefile ^
    --noconsole ^
    --hidden-import mft_scanner ^
    --name "GreenDiskVisualizer_%VER_FNAME%_%ARCH%" ^
    --distpath "dist" ^
    --workpath "build_%ARCH%" ^
    --specpath "." ^
    --clean ^
    %ICON_ARGS% ^
    main.py >"%BUILD_LOG%" 2>&1

if errorlevel 1 (
    echo  [%ARCH%] Build failed. Build log:
    echo  -----------------------------------------------------
    type "%BUILD_LOG%" 2>nul
    echo  -----------------------------------------------------
    if exist "%BUILD_LOG%" del /f /q "%BUILD_LOG%" 2>nul
    echo.
    goto :eof
)
if exist "%BUILD_LOG%" del /f /q "%BUILD_LOG%" 2>nul

echo  [%ARCH%] Build succeeded: dist\GreenDiskVisualizer_%VER_FNAME%_%ARCH%.exe
echo.

if exist "build_%ARCH%" rmdir /s /q "build_%ARCH%" >nul 2>nul
set /a BUILD_COUNT+=1
goto :eof
