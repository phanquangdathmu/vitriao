@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ===== BUILD VITRIAO (Windows) =====

REM --- tim Python ---
set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo [LOI] Chua cai Python. Tai o https://www.python.org/downloads/
  echo        Khi cai nho TICK o "Add python.exe to PATH", roi chay lai file nay.
  pause & exit /b 1
)
echo Dung Python: %PY%

REM --- appconfig.py: nhung URL server + khoa cong khai vao app ---
if exist "app\appconfig.py" goto HAVECONF
echo.
set /p ACTURL=Dan URL activate.php cua server (vd https://domain/activate/activate.php):
> app\appconfig.py echo ACTIVATE_URL = "%ACTURL%"
>> app\appconfig.py echo PUBLIC_KEY_HEX = "7c3460a4a812ad3a0197a9e50889da7e6054e4990ebb003873edc3c88deb5123"
echo Da tao app\appconfig.py
:HAVECONF

REM --- cai thu vien ---
echo.
echo === Cai thu vien ===
%PY% -m pip install --upgrade pip
%PY% -m pip install -r app\requirements.txt pyinstaller
if errorlevel 1 ( echo [LOI] Cai thu vien that bai. & pause & exit /b 1 )

REM --- tai wintun.dll (amd64) neu chua co ---
if exist "build\wintun.dll" goto HAVEWINTUN
echo.
echo === Tai wintun.dll ===
powershell -NoProfile -Command "Invoke-WebRequest https://www.wintun.net/builds/wintun-0.14.1.zip -OutFile wintun.zip; Expand-Archive wintun.zip -DestinationPath wintun_tmp -Force; Copy-Item wintun_tmp\wintun\bin\amd64\wintun.dll build\wintun.dll -Force"
if not exist "build\wintun.dll" ( echo [LOI] Khong tai duoc wintun.dll. Kiem tra mang. & pause & exit /b 1 )
:HAVEWINTUN

REM --- dong goi ---
echo.
echo === Dong goi (PyInstaller) ===
%PY% -m PyInstaller build\vitriao.spec --noconfirm
if errorlevel 1 ( echo [LOI] Build that bai. Gui log cho nguoi ho tro. & pause & exit /b 1 )

REM --- gom ra dist\pkg de chep ra USB ---
if not exist dist\pkg mkdir dist\pkg
if not exist dist\pkg\Driver mkdir dist\pkg\Driver
copy /y dist\VitriAo.exe dist\pkg\ >nul
copy /y build\wintun.dll dist\pkg\ >nul
copy /y docs\HUONG-DAN.txt dist\pkg\ >nul 2>nul

echo.
echo ============================================================
echo  XONG! File chay: %cd%\dist\pkg\VitriAo.exe
echo  Nho bo AppleMobileDeviceSupport64.msi vao: dist\pkg\Driver\
echo ============================================================
pause
