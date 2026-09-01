@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
pushd "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 tools\build_site_data.py
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python tools\build_site_data.py
    ) else (
        echo Python 3 was not found.
        echo Install Python 3 and run this file again.
        pause
        exit /b 1
    )
)

if errorlevel 1 (
    echo.
    echo Site data update failed.
    echo Send the error text or a screenshot to ChatGPT.
) else (
    echo.
    echo Site data files are ready.
    echo Commit the changed files in GitHub Desktop and Push origin.
)

echo.
pause
popd
endlocal
