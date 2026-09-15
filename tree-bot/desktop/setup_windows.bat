@echo off
chcp 65001 >nul
title نصب پیش‌نیازهای بات قطع درخت
color 0A
echo.
echo ============================================================
echo    نصب پیش‌نیازهای بات قطع درخت (Tree Auto-Clicker)
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [X] پایتون پیدا نشد!
  echo.
  echo     ۱) از python.org/downloads پایتون رو نصب کن
  echo     ۲) موقع نصب تیک "Add python.exe to PATH" رو بزن
  echo     ۳) بعد دوباره همین فایل رو اجرا کن
  echo.
  pause
  exit /b 1
)

echo [OK] پایتون پیدا شد:
python --version
echo.

echo [..] نصب بسته‌های لازم (pyautogui, mss, opencv, pillow, pynput)
python -m pip install --upgrade pip
python -m pip install pyautogui mss opencv-python pillow pynput
if errorlevel 1 (
  echo.
  echo [X] نصب بعضی بسته‌ها شکست خورد. اینترنت/pip رو چک کن.
  pause
  exit /b 1
)

echo.
echo [OK] همه‌چیز آماده‌ست! حالا run_windows.bat رو اجرا کن.
echo.
pause
