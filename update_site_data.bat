@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
pushd "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 tools\build_site_data.py
    if errorlevel 1 goto :failed
    py -3 tools\build_ai_indexes.py
    if errorlevel 1 goto :failed
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python tools\build_site_data.py
        if errorlevel 1 goto :failed
        python tools\build_ai_indexes.py
        if errorlevel 1 goto :failed
    ) else (
        echo Python 3 was not found.
        echo Install Python 3 and run this file again.
        pause
        exit /b 1
    )
)

echo.
echo Site data and AI indexes are ready.
echo Commit the changed files in GitHub Desktop and Push origin.
goto :done

:failed
echo.
echo Site data update failed.
echo Send the error text or a screenshot to ChatGPT.

:done
echo.
pause
popd
endlocal
