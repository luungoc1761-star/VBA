@echo off
chcp 65001 >nul
title [1] CHAY LOC DU LIEU ISCALA BATCH
cls
echo =====================================================================
echo   DANG CHAY MODULE LOC DU LIEU CAN TRU TON KHO (PYTHON PORTABLE)
echo =====================================================================
echo.

if exist ".\python_portable\python.exe" (
    ".\python_portable\python.exe" batch_data_processor.py "Stock Balance With Batch.xlsx"
) else (
    python batch_data_processor.py "Stock Balance With Batch.xlsx"
)

echo.
echo =====================================================================
echo   HOAN TAT! AN PHIM BAT KY DE DONG CUA SO NAY.
echo =====================================================================
pause >nul
