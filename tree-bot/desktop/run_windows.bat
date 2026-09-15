@echo off
chcp 65001 >nul
title 🌳 بات قطع درخت
color 0E
cd /d "%~dp0"

echo.
echo ============================================================
echo    🌳 بات قطع درخت — هر ۵ ثانیه
echo ============================================================
echo.
echo   کلیدها:  F8 = توقف/ادامه   |   F9 = خروج
echo   توقف اضطراری: ماوس رو ببر گوشه‌ی بالا-چپ صفحه
echo.

if not exist "tree.png" goto nopick

echo   قالبِ درخت پیدا شد: tree.png
echo.
choice /C 12 /N /M "  کلید ۱ = شروع با همین قالب   |   کلید ۲ = انتخاب درخت جدید با ماوس  "
if errorlevel 2 goto pick
if errorlevel 1 goto run

:nopick
echo   قالب درختی ذخیره نشده — اول با ماوس دور یه درخت مستطیل بکش.
echo.

:pick
echo   تا ۳ ثانیه دیگه پنجره‌ی بازی رو بیار جلو...
python tree_auto_clicker.py --pick --interval 5
goto end

:run
echo.
echo   تا ۳ ثانیه دیگه پنجره‌ی بازی رو بیار جلو...
python tree_auto_clicker.py --interval 5
goto end

:end
echo.
echo ============================================================
echo   تمام شد. برای تست بدون کلیک می‌تونی این رو بزنی:
echo       python tree_auto_clicker.py --dry-run --once
echo ============================================================
pause
