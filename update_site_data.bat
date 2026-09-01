@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
pushd "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 tools\build_site_data.py
    if errorlevel 1 goto :failed
    py -3 tools\enrich_full_events.py
    if errorlevel 1 goto :failed
    py -3 tools\enrich_early_laning.py
    if errorlevel 1 goto :failed
    py -3 tools\add_movement_snapshots.py
    if errorlevel 1 goto :failed
    py -3 tools\add_item_names_ko.py
    if errorlevel 1 goto :failed
    py -3 tools\build_team_context.py
    if errorlevel 1 goto :failed
    py -3 tools\build_stats.py
    if errorlevel 1 goto :failed
    py -3 tools\build_player_stats.py
    if errorlevel 1 goto :failed
    py -3 tools\build_search_index.py
    if errorlevel 1 goto :failed
    py -3 tools\build_kennen_skill_order.py
    if errorlevel 1 goto :failed
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python tools\build_site_data.py
        if errorlevel 1 goto :failed
        python tools\enrich_full_events.py
        if errorlevel 1 goto :failed
        python tools\enrich_early_laning.py
        if errorlevel 1 goto :failed
        python tools\add_movement_snapshots.py
        if errorlevel 1 goto :failed
        python tools\add_item_names_ko.py
        if errorlevel 1 goto :failed
        python tools\build_team_context.py
        if errorlevel 1 goto :failed
        python tools\build_stats.py
        if errorlevel 1 goto :failed
        python tools\build_player_stats.py
        if errorlevel 1 goto :failed
        python tools\build_search_index.py
        if errorlevel 1 goto :failed
        python tools\build_kennen_skill_order.py
        if errorlevel 1 goto :failed
    ) else (
        echo Python 3 was not found.
        echo Install Python 3 and run this file again.
        pause
        exit /b 1
    )
)

echo.
echo Split site data, full participant/event data, dense early-laning snapshots, all-position movement snapshots, Korean item names, team context, generic stats, detailed duo/player stats, tiny AI search routes, and Kennen skill-order stats are ready.
echo Commit all changed files in GitHub Desktop and Push origin.
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
