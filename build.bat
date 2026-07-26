@echo off
echo ============================================
echo   Building LDK2ray.exe
echo ============================================
echo.

REM --- Python 3.12 is required (pywebview/pythonnet do not support 3.14 yet) ---
py -3.12 --version >nul 2>nul
if errorlevel 1 (
    echo [!] Python 3.12 is not installed.
    echo     Run this command once, then start build.bat again:
    echo.
    echo         py install 3.12
    echo.
    pause
    exit /b 1
)

echo [1/2] Installing dependencies with Python 3.12...
py -3.12 -m pip install --upgrade pip
py -3.12 -m pip install -r requirements.txt pyinstaller

echo.
echo [2/2] Building app (onedir - легче по памяти и быстрее старт)...
REM --noupx: сжатие UPX ломает библиотеки WebView2 и вызывает подозрения антивирусов
py -3.12 -m PyInstaller --noconfirm --onedir --windowed --noupx --name LDK2ray --icon "ui/app.ico" --collect-all webview --collect-all pystray --add-data "ui;ui" main.py

echo.
echo [extra] Copying core + geo files next to the app...
REM tun2socks.exe + wintun.dll нужны для режима "Туннель"
for %%F in (xray.exe tun2socks.exe geoip.dat geosite.dat wintun.dll) do (
    if exist "%%F" copy /y "%%F" "dist\LDK2ray\" >nul
)

if exist dist\LDK2ray\LDK2ray.exe (
    echo  SUCCESS: dist\LDK2ray\  is ready ^(run LDK2ray.exe inside^).
    if not exist dist\LDK2ray\xray.exe echo  Reminder: put xray.exe into dist\LDK2ray\ next to LDK2ray.exe.
    if not exist dist\LDK2ray\tun2socks.exe echo  Reminder: tun2socks.exe is missing - Tunnel mode will be unavailable.
) else (
    echo  [!] Build failed - check the messages above.
)
echo.
pause
