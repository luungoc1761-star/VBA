@echo off
chcp 65001 >nul
title [2] MO GIAO DIEN ISCALA AUTO-TYPER
cls
echo =====================================================================
echo   DANG KHOI DONG GIAO DIEN ISCALA AUTO-TYPER CONTROL PANEL...
echo =====================================================================
echo.

if exist ".\python_portable\python.exe" (
    start "" ".\python_portable\python.exe" auto_typer_gui.py
) else (
    start "" python auto_typer_gui.py
)

exit
