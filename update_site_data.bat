@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
pushd "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 tools\merge_local_archives.py
    if errorlevel 1 goto :failed
    py -3 tools\build_site_data_incremental.py
    if errorlevel 1 goto :failed
    py -3 tools\build_mode_data.py
    if errorlevel 1 goto :failed
    py -3 tools\enrich_timeline_incremental.py
    if errorlevel 1 goto :failed
    py -3 tools\add_item_names_ko.py
    if errorlevel 1 goto :failed
    py -3 tools\build_item_economy.py
    if errorlevel 1 goto :failed
    py -3 tools\build_team_context_incremental.py
    if errorlevel 1 goto :failed
    py -3 tools\build_stats.py
    if errorlevel 1 goto :failed
    py -3 tools\build_item_stats.py
    if errorlevel 1 goto :failed
    py -3 tools\build_player_stats.py
    if errorlevel 1 goto :failed
    py -3 tools\build_search_index.py
    if errorlevel 1 goto :failed
    py -3 tools\build_mode_stats.py
    if errorlevel 1 goto :failed
    py -3 tools\build_kennen_skill_order.py
    if errorlevel 1 goto :failed
    py -3 tools\validate_generated_data.py
    if errorlevel 1 goto :failed
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python tools\merge_local_archives.py
        if errorlevel 1 goto :failed
        python tools\build_site_data_incremental.py
        if errorlevel 1 goto :failed
        python tools\build_mode_data.py
        if errorlevel 1 goto :failed
        python tools\enrich_timeline_incremental.py
        if errorlevel 1 goto :failed
        python tools\add_item_names_ko.py
        if errorlevel 1 goto :failed
        python tools\build_item_economy.py
        if errorlevel 1 goto :failed
        python tools\build_team_context_incremental.py
        if errorlevel 1 goto :failed
        python tools\build_stats.py
        if errorlevel 1 goto :failed
        python tools\build_item_stats.py
        if errorlevel 1 goto :failed
        python tools\build_player_stats.py
        if errorlevel 1 goto :failed
        python tools\build_search_index.py
        if errorlevel 1 goto :failed
        python tools\build_mode_stats.py
        if errorlevel 1 goto :failed
        python tools\build_kennen_skill_order.py
        if errorlevel 1 goto :failed
        python tools\validate_generated_data.py
        if errorlevel 1 goto :failed
    ) else (
        echo Python 3 was not found.
        echo Install Python 3 and run this file again.
        pause
        exit /b 1
    )
)

echo.
echo Incremental update complete. Unchanged match details, timelines, and team-context files were reused; only new or changed raw matches were processed heavily.
echo Mode classification: data\modes.json
echo Mode-aware AI stats: data\stats\modes.json
echo Validation report: data\validation.json
echo Commit all changed files in GitHub Desktop and Push origin.
goto :done

:failed
echo.
echo Site data update failed or validation found a blocking inconsistency.
echo Check data\validation.json if it exists, then send the error text or a screenshot to ChatGPT.

:done
echo.
pause
popd
endlocal
