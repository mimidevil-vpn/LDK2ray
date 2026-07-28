@echo off
REM ============================================================
REM   LDK2ray — сборка готового установщика (одной командой)
REM   1) собирает LDK2ray.exe (PyInstaller, Python 3.12)
REM   2) кладёт рядом ядро и geo-файлы
REM   3) ставит Inno Setup (если нет) и компилирует Setup.exe
REM   Результат: installer\Output\LDK2ray-Setup.exe
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0.."
echo(
echo ==== LDK2ray installer build ====
echo(

REM 1/5) Building LDK2ray.exe with Python 3.12...
echo [1/5] Building LDK2ray.exe with Python 3.12...
py -3.12 --version >nul 2>nul || ( echo [!] Python 3.12 not found. Run:  py install 3.12  & pause & exit /b 1 )
py -3.12 -m pip install --upgrade pip >nul
py -3.12 -m pip install -r requirements.txt pyinstaller
py -3.12 -m PyInstaller --noconfirm --onedir --windowed --noupx --name LDK2ray --icon "ui/app.ico" --collect-all webview --collect-all pystray --add-data "ui;ui" main.py
if not exist "dist\LDK2ray\LDK2ray.exe" ( echo [!] Build failed. & pause & exit /b 1 )

REM 2/5) Copy updated index.html (with subscription auth)
echo [2/5] Copying updated index.html...
if exist "dist\LDK2ray\index.html" (
    echo   index.html exists (PyInstaller may have copied it)
) else (
    echo   index.html not found, attempting to copy from ui\\index.html
    copy /y "ui\index.html" "dist\LDK2ray\" >nul
)

REM 3/5) Copy core runtime files
REM xray.exe + tun2socks.exe + wintun.dll needed for "Tunnel" mode
echo [3/5] Copying runtime files...
for %%F in (xray.exe tun2socks.exe geoip.dat geosite.dat wintun.dll) do (
    if exist "%%F" ( copy /y "%%F" "dist\LDK2ray\" >nul ) else ( echo   [warn] missing %%F )
)

REM 4/5) Locate Inno Setup compiler (ISCC)...
echo [4/5] Locating Inno Setup compiler (ISCC)...
set "ISCC="
for %%P in (iscc.exe) do if not defined ISCC set "ISCC=%%~$PATH:P"
REM %LOCALAPPDATA% тоже проверяем: winget ставит Inno Setup для пользователя,
REM и тогда в Program Files его нет.
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo   Inno Setup not found - installing via winget...
    winget install -e --id JRSoftware.InnoSetup --accept-package-agreements --accept-source-agreements --silent
    if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
    if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
)
if not defined ISCC (
    echo(
    echo [!] Inno Setup is unavailable. Use the no-dependency installer instead:
    echo     installer\LDK2ray-portable-setup.bat
    pause & exit /b 1
)

REM 5/5) Compile installer
echo [5/5] Compiling installer...
"%ISCC%" "installer\LDK2ray.iss"
if exist "installer\Output\LDK2ray-Setup.exe" (
    echo(
    echo  SUCCESS ^-^> installer\Output\LDK2ray-Setup.exe
) else (
    echo [!] Compilation failed - check messages above.
)
echo(
pause
